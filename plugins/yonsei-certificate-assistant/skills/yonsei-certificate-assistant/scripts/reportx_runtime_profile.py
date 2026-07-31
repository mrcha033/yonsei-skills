#!/usr/bin/env python3
"""Materialize ReportX runtime-only objects for the Yonsei print profile.

The FP3 response does not contain every byte that the Windows client prints.
REPORTX.exe injects a small ``원본`` bitmap into ``__LOGO1__`` and replaces
``__SERIAL__`` with the 16-character document number reserved immediately
before printing.  This module reproduces only those proven mutations.

No vendor image is distributed with the skill.  ``prepare_official_assets``
extracts the two pinned bitmaps from the exact official Yonsei installer and
stores them in the user's private cache after validating every outer and inner
hash.  Any version drift fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

FP3_RENDERER_DIR = (
    Path(__file__).resolve().parents[2]
    / "render-reportx-fp3-pdf"
    / "scripts"
)
if str(FP3_RENDERER_DIR) not in sys.path:
    sys.path.insert(0, str(FP3_RENDERER_DIR))

from fp3_pdf import FP3Model, parse_fp3


OFFICIAL_INSTALLER_URL = (
    "https://icert.yonsei.ac.kr/ys1.0/module/ICT_REPORTX_SETUP.exe"
)
OFFICIAL_INSTALLER_SHA256 = (
    "6c37e0bdaef63aba8377fd902a01c350adbc3f849fa0afe9a9cf222ea888f673"
)
OFFICIAL_INSTALLER_BYTES = 4_336_176
OFFICIAL_REPORTX_SHA256 = (
    "ceae3b3ca03656bf2b8bddde2abba7e4d016ad5a42dde3a9d332d29b56959cd5"
)
OFFICIAL_REPORTX_BYTES = 3_782_856
ASSET_SCHEMA = "yonsei-reportx-official-assets/v1"
ASSET_DIRNAME = "official-assets"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024

# Offsets are accepted only after the complete REPORTX.exe matches the pinned
# outer hash above.  Each extracted BMP is then independently validated.
_ASSET_LAYOUT = {
    "landscape": {
        "offset": 0x23627E,
        "length": 33_894,
        "width": 260,
        "height": 130,
        "sha256": (
            "70e13e549af365b0c0c7cd0556e7458bb4278c67a98d8fa7f2e68675dbbb3a50"
        ),
    },
    "portrait": {
        "offset": 0x22DBB8,
        "length": 34_414,
        "width": 130,
        "height": 260,
        "sha256": (
            "e53ebaa130b33cdec70d2a9ad10f13960e8f114af1512f16f61527b234a83c9d"
        ),
    },
}
_LOGO_NAME = re.compile(r"^__LOGO1__(?:PAGE(?:[123]__|[0-9]+))?$")
_SERIAL_NAME = re.compile(r"^__SERIAL__(?:PAGE(?:[123]__|[0-9]+))?$")
_SEAL_NAME = re.compile(r"^__SEAL[1-3]__(?:PAGE(?:[123]__|[0-9]+))?$")
_PLACEHOLDER_NUMBER = re.compile(r"(?<![0-9])[0-9]{10}(?![0-9])")
_DOCUMENT_NUMBER = re.compile(r"^[0-9A-Za-z]{16}$")


class ReportXProfileError(ValueError):
    """Raised when the live document cannot be materialized exactly."""


class DocumentNumberRequired(ReportXProfileError):
    """Raised when a serial placeholder requires one document reservation."""


@dataclass(frozen=True)
class OfficialAssets:
    landscape: bytes
    portrait: bytes


@dataclass(frozen=True)
class RuntimeBindings:
    pictures: dict[str, bytes]
    text: dict[str, str]
    official_empty_pictures: frozenset[str]
    profile_id: str = "yonsei-reportx-print-v1"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_regular(path: Path, *, maximum: int) -> bytes:
    try:
        info = path.lstat()
    except OSError as error:
        raise ReportXProfileError("official source is unavailable") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size <= 0
        or info.st_size > maximum
    ):
        raise ReportXProfileError("official source is outside file policy")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ReportXProfileError("official source cannot be read") from error
    if len(data) != info.st_size:
        raise ReportXProfileError("official source changed while reading")
    return data


def _validate_bmp(
    data: bytes,
    *,
    width: int,
    height: int,
    expected_sha256: str,
) -> bytes:
    if len(data) < 54 or data[:2] != b"BM":
        raise ReportXProfileError("official logo is not a Windows BMP")
    file_size = struct.unpack_from("<I", data, 2)[0]
    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    dib_size = struct.unpack_from("<I", data, 14)[0]
    actual_width, actual_height = struct.unpack_from("<ii", data, 18)
    planes, bits = struct.unpack_from("<HH", data, 26)
    compression = struct.unpack_from("<I", data, 30)[0]
    if (
        file_size != len(data)
        or pixel_offset < 54
        or pixel_offset >= len(data)
        or dib_size != 40
        or actual_width != width
        or actual_height != height
        or planes != 1
        or bits != 8
        or compression != 0
        or _sha256(data) != expected_sha256
    ):
        raise ReportXProfileError("official logo failed its pinned BMP contract")
    return data


def extract_official_assets(reportx_exe: bytes) -> OfficialAssets:
    """Extract the two runtime logo bitmaps from the pinned official PE."""

    if (
        len(reportx_exe) != OFFICIAL_REPORTX_BYTES
        or _sha256(reportx_exe) != OFFICIAL_REPORTX_SHA256
    ):
        raise ReportXProfileError("REPORTX.exe does not match the Yonsei release")
    values: dict[str, bytes] = {}
    for name, contract in _ASSET_LAYOUT.items():
        start = int(contract["offset"])
        end = start + int(contract["length"])
        raw = reportx_exe[start:end]
        if len(raw) != int(contract["length"]):
            raise ReportXProfileError("official logo offset exceeds REPORTX.exe")
        values[name] = _validate_bmp(
            raw,
            width=int(contract["width"]),
            height=int(contract["height"]),
            expected_sha256=str(contract["sha256"]),
        )
    return OfficialAssets(
        landscape=values["landscape"],
        portrait=values["portrait"],
    )


def _direct_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _download_installer() -> bytes:
    parsed = urllib.parse.urlsplit(OFFICIAL_INSTALLER_URL)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "icert.yonsei.ac.kr"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise AssertionError("official installer URL is outside policy")
    request = urllib.request.Request(
        OFFICIAL_INSTALLER_URL,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "yonsei-certificate-assistant/0.5",
        },
        method="GET",
    )
    try:
        with _direct_opener().open(request, timeout=30) as response:
            if response.status != 200:
                raise ReportXProfileError("official installer returned non-200")
            body = response.read(MAX_DOWNLOAD_BYTES + 1)
    except OSError as error:
        raise ReportXProfileError("official installer download failed") from error
    if (
        len(body) != OFFICIAL_INSTALLER_BYTES
        or _sha256(body) != OFFICIAL_INSTALLER_SHA256
    ):
        raise ReportXProfileError("official installer failed its pinned hash")
    return body


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _private_chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        _private_fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _private_chmod(path, 0o600)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _private_chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except (NotImplementedError, OSError):
        if os.name != "nt":
            raise


def _private_fchmod(fd: int, mode: int) -> None:
    operation = getattr(os, "fchmod", None)
    if operation is None:
        return
    try:
        operation(fd, mode)
    except (NotImplementedError, OSError):
        if os.name != "nt":
            raise


def _extract_reportx_with_inno(
    installer: bytes,
    *,
    temporary_root: Path,
) -> bytes:
    executable = shutil.which("innoextract")
    if not executable:
        raise ReportXProfileError(
            "innoextract is required to unpack the official installer"
        )
    installer_path = temporary_root / "ICT_REPORTX_SETUP.exe"
    output = temporary_root / "unpacked"
    output.mkdir(mode=0o700)
    _atomic_private_write(installer_path, installer)
    try:
        completed = subprocess.run(
            [
                executable,
                "-e",
                "-q",
                "-I",
                "app/REPORTX.exe",
                "-d",
                str(output),
                str(installer_path),
            ],
            check=False,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReportXProfileError("innoextract did not complete") from error
    if completed.returncode != 0:
        raise ReportXProfileError("innoextract rejected the official installer")
    candidates = (
        output / "app" / "REPORTX.exe",
        output / "REPORTX.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return _read_regular(
                candidate,
                maximum=OFFICIAL_REPORTX_BYTES,
            )
    raise ReportXProfileError("official installer did not contain REPORTX.exe")


def _installed_reportx_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    override = os.environ.get("YONSEI_REPORTX_EXE")
    if override:
        candidates.append(Path(override).expanduser())
    for variable in (
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "LOCALAPPDATA",
    ):
        value = os.environ.get(variable)
        if not value:
            continue
        root = Path(value)
        candidates.extend(
            (
                root / "REPORTX" / "REPORTX.exe",
                root / "ICT_REPORTX" / "REPORTX.exe",
                root / "DuzonBizon" / "REPORTX" / "REPORTX.exe",
            )
        )
    candidates.append(Path("C:/REPORTX/REPORTX.exe"))
    return tuple(dict.fromkeys(candidates))


def _verified_installed_reportx() -> bytes | None:
    for candidate in _installed_reportx_candidates():
        try:
            body = _read_regular(candidate, maximum=OFFICIAL_REPORTX_BYTES)
        except ReportXProfileError:
            continue
        if (
            len(body) == OFFICIAL_REPORTX_BYTES
            and _sha256(body) == OFFICIAL_REPORTX_SHA256
        ):
            return body
    return None


def _asset_dir(root: Path) -> Path:
    return root / ASSET_DIRNAME


def load_official_assets(root: Path) -> OfficialAssets:
    """Load and revalidate previously extracted private-cache assets."""

    directory = _asset_dir(root)
    landscape = _read_regular(
        directory / "ImgOnebon.bmp",
        maximum=int(_ASSET_LAYOUT["landscape"]["length"]),
    )
    portrait = _read_regular(
        directory / "ImgOnebon1.bmp",
        maximum=int(_ASSET_LAYOUT["portrait"]["length"]),
    )
    return OfficialAssets(
        landscape=_validate_bmp(
            landscape,
            width=int(_ASSET_LAYOUT["landscape"]["width"]),
            height=int(_ASSET_LAYOUT["landscape"]["height"]),
            expected_sha256=str(_ASSET_LAYOUT["landscape"]["sha256"]),
        ),
        portrait=_validate_bmp(
            portrait,
            width=int(_ASSET_LAYOUT["portrait"]["width"]),
            height=int(_ASSET_LAYOUT["portrait"]["height"]),
            expected_sha256=str(_ASSET_LAYOUT["portrait"]["sha256"]),
        ),
    )


def prepare_official_assets(
    root: Path,
    *,
    installer_path: Path | None = None,
    reportx_exe_path: Path | None = None,
) -> OfficialAssets:
    """Download/extract and cache assets from the exact Yonsei installer."""

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _private_chmod(root, 0o700)
    if installer_path is not None and reportx_exe_path is not None:
        raise ReportXProfileError(
            "choose either installer_path or reportx_exe_path"
        )
    reportx_exe: bytes | None = None
    if reportx_exe_path is not None:
        reportx_exe = _read_regular(
            reportx_exe_path,
            maximum=OFFICIAL_REPORTX_BYTES,
        )
    elif installer_path is None:
        reportx_exe = _verified_installed_reportx()
    if reportx_exe is None and installer_path is None:
        installer = _download_installer()
    elif reportx_exe is None:
        assert installer_path is not None
        installer = _read_regular(
            installer_path,
            maximum=MAX_DOWNLOAD_BYTES,
        )
        if (
            len(installer) != OFFICIAL_INSTALLER_BYTES
            or _sha256(installer) != OFFICIAL_INSTALLER_SHA256
        ):
            raise ReportXProfileError(
                "installer does not match the official Yonsei release"
            )
    if reportx_exe is None:
        with tempfile.TemporaryDirectory(
            prefix=".reportx-official-",
            dir=root,
        ) as temporary:
            temporary_root = Path(temporary)
            _private_chmod(temporary_root, 0o700)
            reportx_exe = _extract_reportx_with_inno(
                installer,
                temporary_root=temporary_root,
            )
    assets = extract_official_assets(reportx_exe)
    directory = _asset_dir(root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    _private_chmod(directory, 0o700)
    _atomic_private_write(directory / "ImgOnebon.bmp", assets.landscape)
    _atomic_private_write(directory / "ImgOnebon1.bmp", assets.portrait)
    manifest = {
        "schema": ASSET_SCHEMA,
        "source_url": OFFICIAL_INSTALLER_URL,
        "installer_sha256": OFFICIAL_INSTALLER_SHA256,
        "reportx_sha256": OFFICIAL_REPORTX_SHA256,
        "assets": {
            name: {
                "sha256": contract["sha256"],
                "width": contract["width"],
                "height": contract["height"],
            }
            for name, contract in _ASSET_LAYOUT.items()
        },
    }
    _atomic_private_write(
        directory / "source.json",
        json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"),
    )
    return load_official_assets(root)


def _special_objects(model: FP3Model):  # noqa: ANN202
    for page_number, page in enumerate(model.pages):
        for item in page.objects:
            yield page_number, page, item


def has_runtime_placeholders(fp3: bytes) -> bool:
    """Return whether an FP3 uses a proven ReportX runtime-only placeholder."""

    model = parse_fp3(fp3)
    return any(
        pattern.fullmatch(item.attrs.get("Name", ""))
        for _, _, item in _special_objects(model)
        for pattern in (_LOGO_NAME, _SERIAL_NAME, _SEAL_NAME)
    )


def build_runtime_bindings(
    fp3: bytes,
    assets: OfficialAssets,
    document_numbers: Sequence[str] = (),
    *,
    hide_logo: bool = False,
) -> RuntimeBindings:
    """Resolve runtime logo, serial, and proven-empty seal placeholders."""

    model = parse_fp3(fp3)
    logo_items = []
    serial_items = []
    empty_seals: set[str] = set()
    for page_number, page, item in _special_objects(model):
        name = item.attrs.get("Name", "")
        if _LOGO_NAME.fullmatch(name):
            if (
                item.class_name != "TfrxPictureView"
                or item.image_index != 0
                or not item.attrs.get("PrintOnly", "").lower()
                in {"1", "true", "yes", "on"}
                or item.width <= 0
                or item.height <= 0
            ):
                raise ReportXProfileError("runtime logo placeholder is invalid")
            logo_items.append(item)
        elif _SERIAL_NAME.fullmatch(name):
            if (
                item.class_name
                not in {"TfrxMemoView", "TfrxCustomMemoView", "TfrxDMPMemoView"}
                or not item.attrs.get("PrintOnly", "").lower()
                in {"1", "true", "yes", "on"}
                or len(_PLACEHOLDER_NUMBER.findall(item.text)) != 1
            ):
                raise ReportXProfileError("runtime serial placeholder is invalid")
            serial_items.append(item)
        elif _SEAL_NAME.fullmatch(name):
            same_page_mark = [
                candidate
                for candidate in page.objects
                if candidate.attrs.get("Name") == "__MARK__"
            ]
            tag_str = item.attrs.get("TagStr", "")
            if (
                item.class_name != "TfrxPictureView"
                or item.image_index != 0
                or item.attrs.get("Tag") != "3"
                or not tag_str
                or len(same_page_mark) != 1
                or same_page_mark[0].image_index is None
                or same_page_mark[0].image_index <= 0
                or same_page_mark[0].attrs.get("TagStr", "") != tag_str
            ):
                raise ReportXProfileError(
                    "empty seal placeholder lacks its source fingerprint"
                )
            empty_seals.add(name)

    if not logo_items:
        raise ReportXProfileError("prepared report has no runtime logo placeholder")
    if serial_items and not document_numbers:
        raise DocumentNumberRequired(
            "prepared report requires a document-number reservation"
        )
    if document_numbers and len(document_numbers) != 1:
        raise ReportXProfileError(
            "this renderer supports one reserved document number per PDF"
        )
    if any(_DOCUMENT_NUMBER.fullmatch(value) is None for value in document_numbers):
        raise ReportXProfileError("document number is outside the 16-char contract")

    pictures = (
        {}
        if hide_logo
        else {
            item.attrs["Name"]: (
                assets.landscape if item.width > item.height else assets.portrait
            )
            for item in logo_items
        }
    )
    text: dict[str, str] = {}
    if document_numbers:
        value = document_numbers[0]
        formatted = "-".join(value[offset : offset + 4] for offset in range(0, 16, 4))
        for item in serial_items:
            text[item.attrs["Name"]] = _PLACEHOLDER_NUMBER.sub(
                formatted,
                item.text,
                count=1,
            )
    return RuntimeBindings(
        pictures=pictures,
        text=text,
        official_empty_pictures=frozenset(
            empty_seals
            | (
                {item.attrs["Name"] for item in logo_items}
                if hide_logo
                else set()
            )
        ),
    )
