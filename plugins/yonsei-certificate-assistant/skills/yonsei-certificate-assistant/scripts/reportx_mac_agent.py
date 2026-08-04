#!/usr/bin/env python3
"""Loopback ReportX compatibility agent for Windows, macOS, and Linux.

The agent accepts the official ``dzreportx:`` handoff on 127.0.0.1, decodes
the ticket with a bundled clean-room decoder, and optionally obtains the exact
server response through a policy broker. Network access is off by default.
No bridge capture, cookie import, generated certificate, automatic printing,
or official-verification claim is part of the protocol worker.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any

FP3_RENDERER_DIR = (
    Path(__file__).resolve().parents[2]
    / "render-reportx-fp3-pdf"
    / "scripts"
)
if str(FP3_RENDERER_DIR) not in sys.path:
    sys.path.insert(0, str(FP3_RENDERER_DIR))

from fp3_pdf import FP3RenderError, TrueTypeFont, render_fp3_pdf
from reportx_protocol import (
    AcceptServerResponse,
    BrokerPolicy,
    BundledDecoderRegistry,
    Failed,
    NetworkResponse,
    ProtocolBroker,
    RequestAction,
    SessionContext,
    TicketEnvelope,
    Unsupported,
)
from reportx_document_v1 import ReportXDocumentError, decode_reportx_document
from reportx_protocol_v1 import (
    TicketDecodeError,
    build_document_number_action,
    build_print_completion_action,
    parse_document_number_response,
)
from reportx_runtime_profile import (
    DocumentNumberRequired,
    OfficialAssets,
    ReportXProfileError,
    build_runtime_bindings,
    has_runtime_placeholders,
    load_official_assets,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65432
DEFAULT_DIR = Path.home() / ".cache" / "yonsei-certificate-assistant"
USER_AGENT = "yonsei-reportx-local-agent/0.6"
MAX_REQUEST_BODY = 64 * 1024
MAX_RESPONSE_BODY = 32 * 1024 * 1024
MAX_PENDING_JOBS = 4
MAX_SUBMISSIONS_PER_MINUTE = 10
MAX_JOB_MANIFESTS = 200
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
PROTOCOL_ARM_TTL_SECONDS = 120
SEMANTIC_DUPLICATE_TTL_SECONDS = 120
REMOTE_HOSTS = frozenset(
    {
        "icert.yonsei.ac.kr",
        "uni.webminwon.com",
    }
)
ALLOWED_PROTOCOL_ORIGINS = frozenset({"https://icert.yonsei.ac.kr"})
TERMINAL_STATES = frozenset(
    {
        "decoded_network_disabled",
        "server_pdf_saved_unverified",
        "server_report_decoded_unrendered",
        "server_report_document_number_required",
        "server_report_fonts_required",
        "server_report_official_assets_required",
        "server_report_rendered_pdf_unverified",
        "server_report_saved_unrendered",
        "document_number_reservation_unknown",
        "unsupported_protocol",
        "decode_failed",
        "transport_failed",
        "protocol_failed",
        "duplicate_server_document",
        "server_document_reused_unverified",
    }
)
SAFE_REASON_CODES = frozenset(
    {
        "agent_restarted_during_job",
        "artifact_hash_mismatch",
        "completion_notification_failed",
        "completion_notification_unknown",
        "decode_failed",
        "document_number_already_reserved",
        "document_number_preflight_rejected",
        "document_number_preflight_render_rejected",
        "document_number_reservation_required",
        "document_number_reservation_unknown",
        "duplicate_server_document",
        "fp3_render_rejected",
        "fp3_structure_rejected",
        "invalid_ticket",
        "official_assets_required",
        "original_fonts_required",
        "output_quota_exceeded",
        "post_reservation_materialization_failed",
        "protocol_failed",
        "rendered_pdf_integrity_failed",
        "runtime_profile_rejected",
        "transport_failed",
        "unexpected_worker_error",
        "unsupported_logo_policy",
        "unsupported_protocol",
        "worker_cancelled",
        "worker_unavailable",
    }
)
YONSEI_TITLE_FONT_NAMES = (
    "YonseiB",
    "연세제목체",
    "연세제목",
)
YONSEI_BODY_FONT_NAMES = (
    "YonseiL",
    "연세본문체",
    "연세본문",
)
BUNDLED_FONT_SHA256 = {
    "YonseiB": "d38160cc6767e3f35f81b15c2fd9ca1c7fc11a20fcb9fa7f603c8c1b5d2f4d82",
    "YonseiL": "b85573c700a42b1045f4563bb9d08bb21d22b03403db922d41f26e4d5e55cbf9",
}


def build_yonsei_font_map(
    title_font: Path | None,
    body_font: Path | None,
) -> dict[str, Path]:
    """Validate the two redistribution-authorized Yonsei faces and map FP3 names."""

    if title_font is None and body_font is None:
        return {}
    if title_font is None or body_font is None:
        raise ValueError("both Yonsei title and body fonts are required")
    title = TrueTypeFont(title_font.expanduser().resolve())
    body = TrueTypeFont(body_font.expanduser().resolve())
    if title.postscript_name.casefold() != "yonseib":
        raise ValueError("title font must have PostScript name YonseiB")
    if body.postscript_name.casefold() != "yonseil":
        raise ValueError("body font must have PostScript name YonseiL")
    if title.sha256 != BUNDLED_FONT_SHA256["YonseiB"]:
        raise ValueError("YonseiB font hash is not the released authorized copy")
    if body.sha256 != BUNDLED_FONT_SHA256["YonseiL"]:
        raise ValueError("YonseiL font hash is not the released authorized copy")
    coverage_probe = "연세대학교 성적증명서 ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789"
    if not title.supports(coverage_probe) or not body.supports(coverage_probe):
        raise ValueError("Yonsei font lacks required Korean, Latin, or digit glyphs")
    mapping = {
        name.casefold(): title.path
        for name in YONSEI_TITLE_FONT_NAMES
    } | {
        name.casefold(): body.path
        for name in YONSEI_BODY_FONT_NAMES
    }
    mapping["*:bold"] = title.path
    mapping["*:regular"] = body.path
    mapping["*"] = body.path
    return mapping


def validate_rendered_font_set(
    font_files: tuple[tuple[str, str], ...],
    font_map: dict[str, Path],
) -> None:
    """Require every live PDF font to be one of the two authorized faces."""

    if not font_files:
        raise FP3RenderError("rendered certificate has no embedded font")
    allowed = {
        TrueTypeFont(path).sha256
        for path in set(font_map.values())
    }
    used = {digest for _, digest in font_files}
    if not used.issubset(allowed):
        raise FP3RenderError("rendered certificate contains an unexpected font")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def secure_mkdir(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir(parents=True, mode=0o700, exist_ok=False)
        info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"private path is not a directory: {path}")
    _private_chmod(path, 0o700)


def _private_chmod(path: Path, mode: int) -> None:
    """Apply POSIX privacy modes where the host supports them."""
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


def harden_private_tree(root: Path) -> None:
    """Repair permissions on the bounded cache tree without following symlinks."""

    directories = (
        root,
        root / "jobs",
        root / "output",
        root / "reservations",
    )
    for directory in directories:
        secure_mkdir(directory)
        for entry in directory.iterdir():
            info = entry.lstat()
            if stat.S_ISREG(info.st_mode):
                _private_chmod(entry, 0o600)


def _atomic_write(path: Path, data: bytes) -> None:
    secure_mkdir(path.parent)
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


def secure_write_text(path: Path, text: str) -> None:
    _atomic_write(path, text.encode("utf-8"))


def secure_write_bytes(path: Path, data: bytes) -> None:
    _atomic_write(path, bytes(data))


def html_message(body: str) -> bytes:
    return f"<HTML><BODY><B>{body}</B></BODY></HTML>".encode("utf-8")


def is_pdf_container(body: bytes) -> bool:
    """Recognize a bounded, internally referenced PDF container.

    This is deliberately only a container gate. It does not authenticate the
    issuer, contents, signatures, or acceptance as an official certificate.
    """

    if len(body) < 64 or not re.match(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n]", body):
        return False
    head = body[:4096].lower()
    if b"<html" in head or b"<!doctype" in head or b"<script" in head:
        return False
    stripped = body.rstrip(b"\t\n\f\r ")
    if not stripped.endswith(b"%%EOF"):
        return False
    eof_offset = len(stripped) - len(b"%%EOF")
    startxref_matches = list(
        re.finditer(rb"startxref[\x00\t\n\f\r ]+([0-9]+)", stripped[:eof_offset])
    )
    if not startxref_matches:
        return False
    xref_offset = int(startxref_matches[-1].group(1))
    if xref_offset <= 0 or xref_offset >= startxref_matches[-1].start():
        return False
    target = body[xref_offset : xref_offset + 64]
    if not (
        target.startswith(b"xref")
        or re.match(rb"[0-9]+[\x00\t\n\f\r ]+[0-9]+[\x00\t\n\f\r ]+obj\b", target)
    ):
        return False
    if b"/Root" not in body or b" obj" not in body or b"endobj" not in body:
        return False
    return True


# Backwards-compatible helper name. It means container structure only.
is_real_pdf = is_pdf_container


def list_cups_printers() -> list[str]:
    if not shutil.which("lpstat"):
        return []
    try:
        completed = subprocess.run(
            ["lpstat", "-a"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return [
        line.split(" ", 1)[0].strip()
        for line in completed.stdout.splitlines()
        if line.split(" ", 1)[0].strip()
    ]


def cups_print(pdf: Path, printer: str) -> tuple[bool, str]:
    if not shutil.which("lp"):
        return False, "lp_not_found"
    if printer not in list_cups_printers():
        return False, "printer_not_found"
    try:
        completed = subprocess.run(
            ["lp", "-d", printer, str(pdf)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "unknown_timeout_after_submit"
    except OSError:
        return False, "lp_start_failed"
    if completed.returncode != 0:
        return False, "unknown_nonzero_after_submit"
    return True, "submitted"


@dataclass
class Job:
    id: str
    created_at: str
    source: str
    param: str | None = field(default=None, repr=False)
    correlation_id: str | None = None
    finished_at: str | None = None
    status: str = "received"
    ticket_length: int | None = None
    ticket_sha256: str | None = None
    decoder_id: str | None = None
    decoder_version: str | None = None
    command: str | None = None
    request_host: str | None = None
    response_length: int | None = None
    response_sha256: str | None = None
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    artifact_kind: str | None = None
    rendered_pdf_path: str | None = None
    rendered_pdf_sha256: str | None = None
    rendered_page_count: int | None = None
    rendered_object_count: int | None = None
    rendered_replay_verified: bool = False
    rendered_fonts: tuple[tuple[str, str], ...] = ()
    bundle_primary_length: int | None = None
    bundle_primary_sha256: str | None = None
    bundle_additional_sha256: tuple[str, ...] = ()
    document_number_status: str = "not_requested"
    document_number_length: int | None = None
    document_number_response_status: int | None = None
    document_number_response_length: int | None = None
    document_number_response_shape: str | None = None
    completion_attempted: bool = False
    completion_notified: bool = False
    completion_status: str = "not_requested"
    completion_response_status: int | None = None
    verification: str = "not_performed"
    print_attempted: bool = False
    printed: bool = False
    print_status: str = "not_requested"
    reason_code: str | None = None
    duplicate_of_job_id: str | None = None
    messages: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.messages.append(f"[{stamp}] {message}")
        if len(self.messages) > 40:
            self.messages = self.messages[-30:]

    def manifest(self) -> dict[str, Any]:
        return {
            "schema": "yonsei-reportx-job/v1",
            "id": self.id,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "ticket": {
                "length": self.ticket_length,
                "sha256": self.ticket_sha256,
            },
            "decoder": {
                "id": self.decoder_id,
                "version": self.decoder_version,
            },
            "command": self.command,
            "request_host": self.request_host,
            "response": {
                "length": self.response_length,
                "sha256": self.response_sha256,
            },
            "artifact": {
                "path": self.artifact_path,
                "kind": self.artifact_kind,
                "sha256": self.artifact_sha256,
            },
            "rendered_pdf": {
                "path": self.rendered_pdf_path,
                "sha256": self.rendered_pdf_sha256,
                "page_count": self.rendered_page_count,
                "object_count": self.rendered_object_count,
                "deterministic_replay_verified": (
                    self.rendered_replay_verified
                ),
                "fonts": [
                    {"file": name, "sha256": digest}
                    for name, digest in self.rendered_fonts
                ],
                "status": (
                    "compatibility_unverified"
                    if self.rendered_pdf_path
                    else "not_available"
                ),
            },
            "reportx_container": {
                "primary_length": self.bundle_primary_length,
                "primary_sha256": self.bundle_primary_sha256,
                "additional_count": len(self.bundle_additional_sha256),
                "additional_sha256": list(self.bundle_additional_sha256),
                "components_persisted": False,
            },
            "document_number": {
                "status": self.document_number_status,
                "length": self.document_number_length,
                "response_status": self.document_number_response_status,
                "response_length": self.document_number_response_length,
                "response_shape": self.document_number_response_shape,
                "value_persisted": False,
                "completion_attempted": self.completion_attempted,
                "completion_notified": self.completion_notified,
                "completion_status": self.completion_status,
                "completion_response_status": self.completion_response_status,
            },
            "verification": self.verification,
            "print": {
                "attempted": self.print_attempted,
                "printed": self.printed,
                "status": self.print_status,
            },
            "reason_code": self.reason_code,
            "duplicate_of_job_id": self.duplicate_of_job_id,
            "messages": self.messages[-20:],
        }


def set_job_reason(job: Job, code: str | None) -> None:
    """Attach one controlled, non-sensitive reason suitable for public status."""

    if code is not None and code not in SAFE_REASON_CODES:
        code = "protocol_failed"
    job.reason_code = code


def job_is_settled(job: Job) -> bool:
    """Return whether callers can stop waiting for this job."""

    if job.status not in TERMINAL_STATES:
        return False
    return (
        job.document_number_status != "request_started_unknown"
        and job.completion_status != "request_started_unknown"
    )


def _manifest_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _manifest_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _manifest_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _manifest_bool(value: Any) -> bool:
    return value is True


def _restored_output_path(value: Any, output_dir: Path) -> str | None:
    """Accept only an existing regular file inside this cache's output dir."""

    raw = _manifest_str(value)
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser().resolve(strict=True)
        root = output_dir.resolve(strict=True)
        candidate.relative_to(root)
        if not stat.S_ISREG(candidate.lstat().st_mode):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return str(candidate)


def restore_job_manifest(payload: Any, output_dir: Path) -> Job | None:
    """Restore the bounded public/private state needed after an agent restart."""

    value = _manifest_dict(payload)
    if value.get("schema") != "yonsei-reportx-job/v1":
        return None
    job_id = _manifest_str(value.get("id"))
    created_at = _manifest_str(value.get("created_at"))
    source = _manifest_str(value.get("source"))
    if (
        not job_id
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", job_id)
        or not created_at
        or not source
    ):
        return None

    ticket = _manifest_dict(value.get("ticket"))
    decoder = _manifest_dict(value.get("decoder"))
    response = _manifest_dict(value.get("response"))
    artifact = _manifest_dict(value.get("artifact"))
    rendered = _manifest_dict(value.get("rendered_pdf"))
    container = _manifest_dict(value.get("reportx_container"))
    document_number = _manifest_dict(value.get("document_number"))
    print_state = _manifest_dict(value.get("print"))
    fonts: list[tuple[str, str]] = []
    raw_fonts = rendered.get("fonts")
    if isinstance(raw_fonts, list):
        for item in raw_fonts[:20]:
            font = _manifest_dict(item)
            name = _manifest_str(font.get("file"))
            digest = _manifest_str(font.get("sha256"))
            if name and digest and re.fullmatch(r"[0-9a-f]{64}", digest):
                fonts.append((Path(name).name, digest))
    raw_additional = container.get("additional_sha256")
    additional = tuple(
        item
        for item in (raw_additional if isinstance(raw_additional, list) else [])[:64]
        if isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item)
    )
    raw_messages = value.get("messages")
    messages = [
        item[:500]
        for item in (raw_messages if isinstance(raw_messages, list) else [])[-20:]
        if isinstance(item, str)
    ]
    job = Job(
        id=job_id,
        created_at=created_at,
        source=source,
        correlation_id=_manifest_str(value.get("correlation_id")),
        finished_at=_manifest_str(value.get("finished_at")),
        status=_manifest_str(value.get("status")) or "protocol_failed",
        ticket_length=_manifest_int(ticket.get("length")),
        ticket_sha256=_manifest_str(ticket.get("sha256")),
        decoder_id=_manifest_str(decoder.get("id")),
        decoder_version=_manifest_str(decoder.get("version")),
        command=_manifest_str(value.get("command")),
        request_host=_manifest_str(value.get("request_host")),
        response_length=_manifest_int(response.get("length")),
        response_sha256=_manifest_str(response.get("sha256")),
        artifact_path=_restored_output_path(artifact.get("path"), output_dir),
        artifact_sha256=_manifest_str(artifact.get("sha256")),
        artifact_kind=_manifest_str(artifact.get("kind")),
        rendered_pdf_path=_restored_output_path(rendered.get("path"), output_dir),
        rendered_pdf_sha256=_manifest_str(rendered.get("sha256")),
        rendered_page_count=_manifest_int(rendered.get("page_count")),
        rendered_object_count=_manifest_int(rendered.get("object_count")),
        rendered_replay_verified=_manifest_bool(
            rendered.get("deterministic_replay_verified")
        ),
        rendered_fonts=tuple(fonts),
        bundle_primary_length=_manifest_int(container.get("primary_length")),
        bundle_primary_sha256=_manifest_str(container.get("primary_sha256")),
        bundle_additional_sha256=additional,
        document_number_status=(
            _manifest_str(document_number.get("status")) or "not_requested"
        ),
        document_number_length=_manifest_int(document_number.get("length")),
        document_number_response_status=_manifest_int(
            document_number.get("response_status")
        ),
        document_number_response_length=_manifest_int(
            document_number.get("response_length")
        ),
        document_number_response_shape=_manifest_str(
            document_number.get("response_shape")
        ),
        completion_attempted=_manifest_bool(
            document_number.get("completion_attempted")
        ),
        completion_notified=_manifest_bool(
            document_number.get("completion_notified")
        ),
        completion_status=(
            _manifest_str(document_number.get("completion_status"))
            or "not_requested"
        ),
        completion_response_status=_manifest_int(
            document_number.get("completion_response_status")
        ),
        verification=_manifest_str(value.get("verification")) or "not_performed",
        print_attempted=_manifest_bool(print_state.get("attempted")),
        printed=_manifest_bool(print_state.get("printed")),
        print_status=_manifest_str(print_state.get("status")) or "not_requested",
        reason_code=_manifest_str(value.get("reason_code")),
        duplicate_of_job_id=_manifest_str(value.get("duplicate_of_job_id")),
        messages=messages,
    )
    set_job_reason(job, job.reason_code)
    return job


class AgentState:
    def __init__(
        self,
        root: Path,
        *,
        allow_fetch: bool,
        allow_document_reservation: bool = False,
        allow_completion_notification: bool = False,
        token: str,
        font_map: dict[str, Path] | None = None,
        require_original_fonts: bool = False,
    ) -> None:
        self.root = root
        self.allow_fetch = allow_fetch
        self.allow_document_reservation = allow_document_reservation
        self.allow_completion_notification = allow_completion_notification
        self.token = token
        self.font_map = dict(font_map or {})
        self.require_original_fonts = require_original_fonts
        self.jobs_dir = root / "jobs"
        self.out_dir = root / "output"
        self.reservations_dir = root / "reservations"
        harden_private_tree(root)
        try:
            self.official_assets: OfficialAssets | None = load_official_assets(root)
        except ReportXProfileError:
            self.official_assets = None
        try:
            mapped_font_hashes = {
                TrueTypeFont(path).sha256
                for path in set(self.font_map.values())
            }
        except (OSError, TypeError, ValueError):
            mapped_font_hashes = set()
        self.font_hashes_verified = (
            mapped_font_hashes == set(BUNDLED_FONT_SHA256.values())
        )
        self.lock = threading.RLock()
        self.jobs: dict[str, Job] = {}
        self.job_events: dict[str, threading.Event] = {}
        self.events: list[str] = []
        self.pending_jobs = 0
        self.active_tickets: dict[str, str] = {}
        self.response_claims: dict[str, str] = {}
        self.submission_times: deque[float] = deque()
        self.protocol_arm_deadline = 0.0
        self.protocol_arm_id: str | None = None
        self.worker_futures: dict[
            str, concurrent.futures.Future[None]
        ] = {}
        self._load_prior_jobs()
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="reportx-worker",
        )

    @staticmethod
    def _job_holds_response_claim(job: Job) -> bool:
        return bool(
            job.document_number_status
            not in {
                "not_requested",
                "explicit_opt_in_required",
                "preflight_rejected",
            }
            and not job.completion_notified
        )

    def _completed_job_is_recent(self, job: Job) -> bool:
        if not job_is_settled(job):
            return False
        if job.status == "server_pdf_saved_unverified":
            raw_path = job.artifact_path
            expected_digest = job.artifact_sha256
        elif job.status == "server_report_rendered_pdf_unverified":
            raw_path = job.rendered_pdf_path
            expected_digest = job.rendered_pdf_sha256
        else:
            return False
        if not raw_path or not expected_digest:
            return False
        try:
            path = Path(raw_path).resolve(strict=True)
            path.relative_to(self.out_dir.resolve(strict=True))
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_size > MAX_RESPONSE_BODY
            ):
                return False
            body = path.read_bytes()
        except (OSError, RuntimeError, ValueError):
            return False
        if sha256_bytes(body) != expected_digest or not is_pdf_container(body):
            return False
        stamp = job.finished_at or job.created_at
        try:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(stamp)
            ).total_seconds()
        except (TypeError, ValueError):
            return False
        return 0 <= age <= SEMANTIC_DUPLICATE_TTL_SECONDS

    def _load_prior_jobs(self) -> None:
        """Reload bounded manifests and settle work interrupted by a restart."""

        try:
            manifests = sorted(
                self.jobs_dir.glob("*.json"),
                key=lambda path: path.name,
            )[-MAX_JOB_MANIFESTS:]
        except OSError:
            return
        for path in manifests:
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            job = restore_job_manifest(payload, self.out_dir)
            if job is None or path.stem != job.id:
                continue
            if job.document_number_status == "request_started_unknown":
                job.status = "document_number_reservation_unknown"
                job.document_number_status = "unknown_after_agent_restart"
                set_job_reason(job, "document_number_reservation_unknown")
                job.note("agent restarted during document-number reservation")
            elif job.completion_status == "request_started_unknown":
                job.completion_status = "unknown_after_agent_restart"
                set_job_reason(job, "completion_notification_unknown")
                job.note("agent restarted during print-completion notification")
            elif job.status not in TERMINAL_STATES:
                job.status = "protocol_failed"
                set_job_reason(job, "agent_restarted_during_job")
                job.note("agent restarted before the worker settled")
            self.jobs[job.id] = job
            event = self.job_events.setdefault(job.id, threading.Event())
            if job_is_settled(job):
                event.set()
            if (
                job.response_sha256
                and self._job_holds_response_claim(job)
            ):
                self.response_claims.setdefault(job.response_sha256, job.id)
            # Persist only the explicit interrupted-state transition; otherwise
            # loaded manifests remain byte-for-byte historical state.
            if job.reason_code in {
                "agent_restarted_during_job",
                "document_number_reservation_unknown",
                "completion_notification_unknown",
            } and payload.get("reason_code") != job.reason_code:
                self.save_job(job)

    def claim_server_response(self, job: Job) -> tuple[bool, str | None]:
        """Claim one semantic server document before any mutable reservation."""

        digest = job.response_sha256
        if not digest or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return False, None
        with self.lock:
            existing_id = self.response_claims.get(digest)
            if existing_id and existing_id != job.id:
                return False, existing_id
            semantic_guard = self.reservations_dir / f"response-{digest}.json"
            if semantic_guard.exists():
                try:
                    guarded = json.loads(
                        semantic_guard.read_text(encoding="utf-8")
                    )
                    guard_value = _manifest_dict(guarded)
                    guarded_id = _manifest_str(guard_value.get("job_id"))
                    guard_status = _manifest_str(guard_value.get("status"))
                    updated_at = _manifest_str(guard_value.get("updated_at"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    return False, None
                expired_completed_guard = False
                if guard_status == "completion_notified" and updated_at:
                    try:
                        guard_age = (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(updated_at)
                        ).total_seconds()
                        expired_completed_guard = (
                            guard_age > SEMANTIC_DUPLICATE_TTL_SECONDS
                        )
                    except (TypeError, ValueError):
                        expired_completed_guard = False
                if (
                    expired_completed_guard
                    or guard_status == "prepared_not_requested"
                ):
                    try:
                        semantic_guard.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        return False, guarded_id
                else:
                    return False, guarded_id
            for existing in reversed(tuple(self.jobs.values())):
                if (
                    existing.id != job.id
                    and existing.response_sha256 == digest
                    and self._completed_job_is_recent(existing)
                ):
                    return False, existing.id
            self.response_claims[digest] = job.id
        return True, None

    def reuse_completed_response(self, job: Job, existing_id: str | None) -> bool:
        """Point a coalesced job at an identical durable recent PDF."""

        if not existing_id:
            return False
        with self.lock:
            existing = self.jobs.get(existing_id)
            if existing is None or not self._completed_job_is_recent(existing):
                return False
            job.artifact_path = existing.artifact_path
            job.artifact_sha256 = existing.artifact_sha256
            job.artifact_kind = existing.artifact_kind
            job.rendered_pdf_path = existing.rendered_pdf_path
            job.rendered_pdf_sha256 = existing.rendered_pdf_sha256
            job.rendered_page_count = existing.rendered_page_count
            job.rendered_object_count = existing.rendered_object_count
            job.rendered_replay_verified = existing.rendered_replay_verified
            job.rendered_fonts = existing.rendered_fonts
            job.document_number_status = existing.document_number_status
            job.document_number_length = existing.document_number_length
            job.completion_attempted = existing.completion_attempted
            job.completion_notified = existing.completion_notified
            job.completion_status = existing.completion_status
            job.completion_response_status = (
                existing.completion_response_status
            )
            return True

    def observe_future(
        self,
        job: Job,
        future: concurrent.futures.Future[None],
    ) -> None:
        with self.lock:
            self.worker_futures[job.id] = future

        def worker_done(done: concurrent.futures.Future[None]) -> None:
            try:
                done.result()
            except concurrent.futures.CancelledError:
                if not job_is_settled(job):
                    _finish_failure(
                        job,
                        self,
                        "protocol_failed",
                        "worker_cancelled",
                    )
            except Exception:
                if not job_is_settled(job):
                    _finish_failure(
                        job,
                        self,
                        "protocol_failed",
                        "unexpected_worker_error",
                    )
            finally:
                with self.lock:
                    self.worker_futures.pop(job.id, None)

        future.add_done_callback(worker_done)

    def wait_for_job(self, job_id: str, timeout: float) -> Job | None:
        with self.lock:
            job = self.jobs.get(job_id)
            event = self.job_events.get(job_id)
        if job is None:
            return None
        if event is not None and not job_is_settled(job):
            event.wait(max(0.0, min(timeout, 30.0)))
        with self.lock:
            return self.jobs.get(job_id)

    def readiness(self) -> dict[str, bool]:
        assets_ready = self.official_assets is not None
        fonts_ready = self.font_hashes_verified
        return {
            "official_runtime_assets_verified": assets_ready,
            "bundled_font_hashes_verified": fonts_ready,
            "live_issue_ready": bool(
                self.allow_fetch
                and self.allow_document_reservation
                and self.allow_completion_notification
                and assets_ready
                and fonts_ready
            ),
        }

    def begin_document_reservation(self, job: Job) -> bool:
        """Persist a no-retry reservation guard before the mutating GET."""

        if not job.ticket_sha256:
            return False
        semantic_path: Path | None = None
        if job.response_sha256:
            semantic_path = (
                self.reservations_dir
                / f"response-{job.response_sha256}.json"
            )
        path = self.reservations_dir / f"{job.ticket_sha256}.json"
        prepared_payload = json.dumps(
            {
                "schema": "yonsei-reportx-reservation-guard/v1",
                "job_id": job.id,
                "ticket_sha256": job.ticket_sha256,
                "response_sha256": job.response_sha256,
                "status": "prepared_not_requested",
                "prepared_at": utc_now(),
            },
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        created: list[Path] = []
        # Acquire the ticket guard first. If the semantic guard is already
        # owned, remove only this unsubmitted prepared guard: URLCheck has not
        # been called yet, so there is no ambiguous mutation to preserve.
        guard_paths = (path, semantic_path) if semantic_path is not None else (path,)
        with self.lock:
            for guard_path in guard_paths:
                assert guard_path is not None
                try:
                    existing_guard = json.loads(
                        guard_path.read_text(encoding="utf-8")
                    )
                    existing_status = _manifest_str(
                        _manifest_dict(existing_guard).get("status")
                    )
                except FileNotFoundError:
                    continue
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if existing_status == "prepared_not_requested":
                    try:
                        guard_path.unlink()
                    except FileNotFoundError:
                        pass
            for guard_path in guard_paths:
                assert guard_path is not None
                try:
                    fd = os.open(
                        guard_path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                except FileExistsError:
                    for prepared_path in reversed(created):
                        try:
                            prepared_path.unlink()
                        except FileNotFoundError:
                            pass
                    return False
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(prepared_payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                except Exception:
                    # A prepared guard may already be durable. It explicitly
                    # records that URLCheck was not called and is recoverable.
                    raise
                created.append(guard_path)

            started_payload = json.dumps(
                {
                    "schema": "yonsei-reportx-reservation-guard/v1",
                    "job_id": job.id,
                    "ticket_sha256": job.ticket_sha256,
                    "response_sha256": job.response_sha256,
                    "status": "started_unknown_until_response",
                    "started_at": utc_now(),
                },
                sort_keys=True,
                indent=2,
            )
            for guard_path in created:
                secure_write_text(guard_path, started_payload)
        return True

    def finish_document_reservation(self, job: Job, status: str) -> None:
        if not job.ticket_sha256:
            return
        path = self.reservations_dir / f"{job.ticket_sha256}.json"
        secure_write_text(
            path,
            json.dumps(
                {
                    "schema": "yonsei-reportx-reservation-guard/v1",
                    "job_id": job.id,
                    "ticket_sha256": job.ticket_sha256,
                    "response_sha256": job.response_sha256,
                    "status": status,
                    "updated_at": utc_now(),
                },
                sort_keys=True,
                indent=2,
            ),
        )
        if job.response_sha256:
            response_path = (
                self.reservations_dir
                / f"response-{job.response_sha256}.json"
            )
            secure_write_text(
                response_path,
                json.dumps(
                    {
                        "schema": "yonsei-reportx-reservation-guard/v1",
                        "job_id": job.id,
                        "ticket_sha256": job.ticket_sha256,
                        "response_sha256": job.response_sha256,
                        "status": status,
                        "updated_at": utc_now(),
                    },
                    sort_keys=True,
                    indent=2,
                ),
            )

    def log(self, message: str) -> None:
        line = f"{utc_now()} {message}"
        with self.lock:
            self.events.append(line)
            self.events = self.events[-250:]
        print(line, file=sys.stderr, flush=True)

    def save_job(self, job: Job) -> None:
        secure_write_text(
            self.jobs_dir / f"{job.id}.json",
            json.dumps(job.manifest(), ensure_ascii=False, indent=2),
        )
        with self.lock:
            event = self.job_events.setdefault(job.id, threading.Event())
            if job_is_settled(job):
                event.set()
            else:
                event.clear()

    def add_job(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.id] = job
            self.job_events.setdefault(job.id, threading.Event())
            if len(self.jobs) > 200:
                for old_id in list(self.jobs)[:50]:
                    self.jobs.pop(old_id, None)
        self.save_job(job)

    def _regular_file_count(self, path: Path) -> int:
        count = 0
        try:
            entries = path.iterdir()
        except OSError:
            return MAX_JOB_MANIFESTS
        for entry in entries:
            try:
                if stat.S_ISREG(entry.lstat().st_mode):
                    count += 1
            except OSError:
                return MAX_JOB_MANIFESTS
        return count

    def _regular_file_bytes(self, path: Path) -> int:
        total = 0
        try:
            entries = path.iterdir()
        except OSError:
            return MAX_OUTPUT_BYTES
        for entry in entries:
            try:
                info = entry.lstat()
            except OSError:
                return MAX_OUTPUT_BYTES
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
                if total >= MAX_OUTPUT_BYTES:
                    return total
        return total

    def admit_job(self, job: Job) -> tuple[str, str | None]:
        """Reserve one bounded worker slot without persisting the raw ticket."""

        if not job.ticket_sha256:
            return "invalid_ticket", None
        now = time.monotonic()
        with self.lock:
            while self.submission_times and now - self.submission_times[0] >= 60:
                self.submission_times.popleft()
            duplicate_id = self.active_tickets.get(job.ticket_sha256)
            if duplicate_id:
                return "duplicate_active", duplicate_id
            if self.pending_jobs >= MAX_PENDING_JOBS:
                return "busy", None
            if len(self.submission_times) >= MAX_SUBMISSIONS_PER_MINUTE:
                return "rate_limited", None
            if self._regular_file_count(self.jobs_dir) >= MAX_JOB_MANIFESTS:
                return "job_quota_exceeded", None
            reserved_output = (self.pending_jobs + 1) * MAX_RESPONSE_BODY
            if self._regular_file_bytes(self.out_dir) + reserved_output > MAX_OUTPUT_BYTES:
                return "output_quota_exceeded", None
            self.pending_jobs += 1
            self.submission_times.append(now)
            self.active_tickets[job.ticket_sha256] = job.id
            self.jobs[job.id] = job
            self.save_job(job)
        return "accepted", None

    def finish_job(self, job: Job) -> None:
        with self.lock:
            if job.finished_at is None:
                job.finished_at = utc_now()
            self.pending_jobs = max(0, self.pending_jobs - 1)
            if (
                job.ticket_sha256
                and self.active_tickets.get(job.ticket_sha256) == job.id
            ):
                self.active_tickets.pop(job.ticket_sha256, None)
            if (
                job.response_sha256
                and self.response_claims.get(job.response_sha256) == job.id
                and not self._job_holds_response_claim(job)
            ):
                self.response_claims.pop(job.response_sha256, None)
        self.save_job(job)

    def write_artifact(self, path: Path, data: bytes) -> bool:
        with self.lock:
            if self._regular_file_bytes(self.out_dir) + len(data) > MAX_OUTPUT_BYTES:
                return False
            secure_write_bytes(path, data)
        return True

    def arm_protocol_once(self) -> tuple[int, str]:
        """Authorize one originless official iframe handoff for a short window."""

        arm_id = secrets.token_hex(12)
        with self.lock:
            self.protocol_arm_deadline = (
                time.monotonic() + PROTOCOL_ARM_TTL_SECONDS
            )
            self.protocol_arm_id = arm_id
        return PROTOCOL_ARM_TTL_SECONDS, arm_id

    def consume_protocol_arm(self) -> str | None:
        with self.lock:
            armed = time.monotonic() <= self.protocol_arm_deadline
            arm_id = self.protocol_arm_id if armed else None
            self.protocol_arm_deadline = 0.0
            self.protocol_arm_id = None
            return arm_id

    def clear_protocol_arm(self) -> None:
        with self.lock:
            self.protocol_arm_deadline = 0.0
            self.protocol_arm_id = None

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


STATE: AgentState | None = None


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return redirect responses to the broker instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def build_transport_opener(
    cookie_jar: http.cookiejar.CookieJar | None = None,
) -> urllib.request.OpenerDirector:
    """Build a direct-only, in-memory transport session.

    ReportX performs URLFile and URLCheck through one WinINet session.  The
    Yonsei URLFile response can set a short-lived cookie that URLCheck needs.
    The jar is never serialized and remains scoped to one worker job.
    """

    handlers: list[Any] = [
        urllib.request.ProxyHandler({}),
        NoRedirectHandler(),
    ]
    if cookie_jar is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(cookie_jar))
    return urllib.request.build_opener(*handlers)


def _response_headers(message: Any) -> tuple[tuple[str, str], ...]:
    headers: list[tuple[str, str]] = []
    for name, value in message.items():
        if len(headers) >= 32:
            break
        if "\r" in value or "\n" in value:
            continue
        headers.append((str(name), str(value)))
    return tuple(headers)


def perform_request(
    action: RequestAction,
    *,
    opener: urllib.request.OpenerDirector | None = None,
    maximum_body_bytes: int = MAX_RESPONSE_BODY,
) -> NetworkResponse:
    """Perform one already-policy-validated action with redirects disabled."""

    if not 0 < maximum_body_bytes <= MAX_RESPONSE_BODY:
        raise ValueError("invalid_response_limit")
    headers = dict(action.headers)
    headers["User-Agent"] = USER_AGENT
    request = urllib.request.Request(
        action.url,
        data=action.body if action.method == "POST" else None,
        headers=headers,
        method=action.method,
    )
    if opener is None:
        opener = build_transport_opener()
    try:
        response = opener.open(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    try:
        length_header = response.headers.get("Content-Length")
        if length_header and int(length_header) > maximum_body_bytes:
            raise ValueError("response_too_large")
        body = response.read(maximum_body_bytes + 1)
        if len(body) > maximum_body_bytes:
            raise ValueError("response_too_large")
        return NetworkResponse.from_bytes(
            request_id=action.request_id,
            url=response.geturl(),
            status=int(response.status),
            headers=_response_headers(response.headers),
            body=body,
        )
    finally:
        response.close()


def local_ipv4_for(host: str) -> str:
    """Return the route-selected IPv4 without sending application data."""
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.settimeout(2)
        connection.connect((host, 443))
        value = str(connection.getsockname()[0])
    except OSError:
        value = "127.0.0.1"
    finally:
        connection.close()
    return value


def _finish_failure(job: Job, state: AgentState, status: str, code: str) -> None:
    job.status = status
    set_job_reason(job, code)
    job.note(job.reason_code or "protocol_failed")
    job.param = None
    state.save_job(job)
    state.log(f"job {job.id} -> {status} code={code}")


def _runtime_profile_required(data: bytes) -> bool | None:
    try:
        return has_runtime_placeholders(data)
    except (TypeError, FP3RenderError, ReportXProfileError):
        return None


def _render_fp3_pdf_replayed(
    primary: bytes,
    additional: tuple[bytes, ...],
    **kwargs: Any,
):  # noqa: ANN202
    """Render twice and fail if the compatibility artifact is not reproducible."""

    first = render_fp3_pdf(primary, additional, **kwargs)
    second = render_fp3_pdf(primary, additional, **kwargs)
    if first.pdf != second.pdf or first.manifest() != second.manifest():
        raise FP3RenderError("FP3 PDF replay is not deterministic")
    return first


def process_job(job: Job, state: AgentState) -> None:
    """Decode one SSO job and optionally run its brokered URLFile request."""

    job.status = "decoding"
    state.save_job(job)
    try:
        assert job.param is not None
        ticket = TicketEnvelope.parse(job.param)
    except (AssertionError, TypeError, ValueError):
        _finish_failure(job, state, "decode_failed", "decode_failed")
        return

    job.ticket_length = ticket.raw_length
    job.ticket_sha256 = ticket.raw_sha256
    context = SessionContext.from_mapping(
        "https://icert.yonsei.ac.kr",
        {},
    )
    opened = BundledDecoderRegistry().open(ticket, context)
    if isinstance(opened, Unsupported):
        _finish_failure(
            job,
            state,
            "unsupported_protocol",
            "unsupported_protocol",
        )
        return
    if isinstance(opened, Failed):
        _finish_failure(job, state, "decode_failed", "decode_failed")
        return

    job.decoder_id = str(getattr(opened, "decoder_id", "bundled"))
    job.decoder_version = str(getattr(opened, "decoder_version", "unknown"))
    parsed = getattr(opened, "parsed", None)
    if parsed is not None:
        job.command = str(parsed.command)
    broker = ProtocolBroker(
        opened,
        BrokerPolicy(
            allowed_hosts=REMOTE_HOSTS,
            max_response_body_bytes=MAX_RESPONSE_BODY,
            max_total_response_bytes=MAX_RESPONSE_BODY,
        ),
    )
    action = broker.start()
    if isinstance(action, Failed):
        _finish_failure(job, state, "protocol_failed", "protocol_failed")
        return
    if not isinstance(action, RequestAction):
        _finish_failure(job, state, "protocol_failed", "protocol_failed")
        return

    job.request_host = (urllib.parse.urlsplit(action.url).hostname or "").lower()
    job.param = None
    if not state.allow_fetch:
        job.status = "decoded_network_disabled"
        job.note("ticket decoded; network remains disabled")
        state.save_job(job)
        state.log(
            f"job {job.id} -> decoded_network_disabled "
            f"decoder={job.decoder_id} command={job.command}"
        )
        return

    job.status = "requesting"
    state.save_job(job)
    transport_opener = build_transport_opener(http.cookiejar.CookieJar())
    try:
        response = perform_request(action, opener=transport_opener)
    except (OSError, TimeoutError, urllib.error.URLError, ValueError):
        _finish_failure(job, state, "transport_failed", "transport_failed")
        return
    job.response_length = len(response.body)
    job.response_sha256 = response.body_sha256
    result = broker.receive(response)
    if not isinstance(result, AcceptServerResponse) or broker.accepted_artifact is None:
        _finish_failure(job, state, "protocol_failed", "protocol_failed")
        return

    artifact = broker.accepted_artifact
    claimed, existing_id = state.claim_server_response(job)
    if not claimed:
        job.duplicate_of_job_id = existing_id
        reused = state.reuse_completed_response(job, existing_id)
        if reused:
            job.status = "server_document_reused_unverified"
            set_job_reason(job, None)
        else:
            job.status = "duplicate_server_document"
            set_job_reason(job, "duplicate_server_document")
        job.note(
            "identical server document coalesced to a recent durable PDF"
            if reused
            else "identical server document is already active or reserved"
        )
        job.param = None
        state.save_job(job)
        state.log(
            f"job {job.id} -> {job.status}"
            + (f" existing={existing_id}" if existing_id else "")
        )
        return
    rendered_pdf: bytes | None = None
    reserved_document_number: str | None = None
    if is_pdf_container(artifact.body):
        suffix = ".pdf"
        job.artifact_kind = "server_pdf_unverified"
        job.status = "server_pdf_saved_unverified"
    else:
        suffix = ".reportx"
        min_no = parsed.get("MINNO") if parsed is not None else None
        try:
            if not min_no:
                raise ReportXDocumentError("MINNO unavailable")
            bundle = decode_reportx_document(artifact.body, min_no)
        except (TypeError, ReportXDocumentError):
            job.artifact_kind = "server_report_unrendered"
            job.status = "server_report_saved_unrendered"
            job.note("outer ReportX response container was not decoded")
        else:
            job.bundle_primary_length = len(bundle.primary)
            job.bundle_primary_sha256 = bundle.primary_sha256
            job.bundle_additional_sha256 = bundle.additional_sha256
            job.artifact_kind = "server_report_decoded_unrendered"
            runtime_profile_required = _runtime_profile_required(
                bundle.primary
            )
            if parsed is None:
                job.status = "server_report_decoded_unrendered"
                set_job_reason(job, "runtime_profile_rejected")
                job.note("decoded ReportX document lacks parsed ticket context")
            elif runtime_profile_required is None:
                job.status = "server_report_decoded_unrendered"
                set_job_reason(job, "fp3_structure_rejected")
                job.note("decoded ReportX FP3 failed structural inspection")
            elif state.require_original_fonts and not state.font_map:
                job.status = "server_report_fonts_required"
                set_job_reason(job, "original_fonts_required")
                job.note(
                    "official Yonsei title/body fonts are required before "
                    "rendering; no document number was reserved"
                )
            elif not runtime_profile_required:
                try:
                    rendered = _render_fp3_pdf_replayed(
                        bundle.primary,
                        bundle.additional,
                        font_map=state.font_map or None,
                    )
                    if state.require_original_fonts:
                        validate_rendered_font_set(
                            rendered.font_files,
                            state.font_map,
                        )
                except (TypeError, FP3RenderError) as error:
                    job.status = "server_report_decoded_unrendered"
                    set_job_reason(job, "fp3_render_rejected")
                    job.note(
                        "decoded ReportX outer container; FP3 renderer "
                        f"rejected it ({type(error).__name__})"
                    )
                else:
                    set_job_reason(job, None)
                    rendered_pdf = rendered.pdf
                    job.artifact_kind = "server_report_response"
                    job.status = "server_report_rendered_pdf_unverified"
                    job.rendered_pdf_sha256 = rendered.pdf_sha256
                    job.rendered_page_count = rendered.page_count
                    job.rendered_object_count = rendered.object_count
                    job.rendered_replay_verified = True
                    job.rendered_fonts = tuple(
                        (Path(path).name, digest)
                        for path, digest in rendered.font_files
                    )
                    job.note(
                        "rendered a prepared report with no runtime-only "
                        "ReportX placeholders"
                    )
            elif state.official_assets is None:
                job.status = "server_report_official_assets_required"
                set_job_reason(job, "official_assets_required")
                job.note(
                    "prepare the exact-hash official ReportX runtime assets "
                    "before rendering"
                )
            else:
                param_5 = parsed.get("Param_5")
                if param_5 not in {None, "", "0", "1"}:
                    job.status = "server_report_decoded_unrendered"
                    set_job_reason(job, "unsupported_logo_policy")
                    job.note("unsupported ReportX Param_5 logo policy")
                    bindings = None
                    needs_document_number = False
                else:
                    try:
                        bindings = build_runtime_bindings(
                            bundle.primary,
                            state.official_assets,
                            hide_logo=param_5 == "1",
                        )
                    except DocumentNumberRequired:
                        bindings = None
                        needs_document_number = True
                    except (TypeError, ReportXProfileError) as error:
                        bindings = None
                        needs_document_number = False
                        job.status = "server_report_decoded_unrendered"
                        set_job_reason(job, "runtime_profile_rejected")
                        job.note(
                            "ReportX runtime profile rejected the document "
                            f"({type(error).__name__})"
                        )
                    else:
                        needs_document_number = False

                if needs_document_number:
                    if not state.allow_document_reservation:
                        job.status = "server_report_document_number_required"
                        job.document_number_status = "explicit_opt_in_required"
                        set_job_reason(
                            job,
                            "document_number_reservation_required",
                        )
                        job.note(
                            "document serial requires one mutating URLCheck "
                            "reservation; no request was made"
                        )
                    else:
                        # Validate every local placeholder and official asset
                        # before crossing the one-shot reservation boundary.
                        try:
                            preflight_bindings = build_runtime_bindings(
                                bundle.primary,
                                state.official_assets,
                                ("0000000000000000",),
                                hide_logo=param_5 == "1",
                            )
                            preflight_rendered = _render_fp3_pdf_replayed(
                                bundle.primary,
                                bundle.additional,
                                font_map=state.font_map or None,
                                runtime_pictures=preflight_bindings.pictures,
                                runtime_text=preflight_bindings.text,
                                official_empty_pictures=(
                                    preflight_bindings.official_empty_pictures
                                ),
                            )
                            if state.require_original_fonts:
                                validate_rendered_font_set(
                                    preflight_rendered.font_files,
                                    state.font_map,
                                )
                            reservation_action = build_document_number_action(
                                parsed
                            )
                            if state.allow_completion_notification:
                                build_print_completion_action(
                                    parsed,
                                    document_number="0000000000000000",
                                    system_ip=local_ipv4_for(
                                        job.request_host
                                        or "icert.yonsei.ac.kr"
                                    ),
                                    printer_model="YonseiSkills PDF",
                                )
                        except FP3RenderError as error:
                            job.status = "server_report_decoded_unrendered"
                            job.document_number_status = "preflight_rejected"
                            set_job_reason(
                                job,
                                "document_number_preflight_render_rejected",
                            )
                            job.note(
                                "full deterministic render preflight rejected "
                                f"the job ({type(error).__name__})"
                            )
                        except (
                            TypeError,
                            ReportXProfileError,
                            TicketDecodeError,
                        ) as error:
                            job.status = "server_report_decoded_unrendered"
                            job.document_number_status = "preflight_rejected"
                            set_job_reason(
                                job,
                                "document_number_preflight_rejected",
                            )
                            job.note(
                                "document-number preflight rejected the job "
                                f"({type(error).__name__})"
                            )
                        else:
                            if not state.begin_document_reservation(job):
                                job.status = (
                                    "document_number_reservation_unknown"
                                )
                                job.document_number_status = (
                                    "blocked_by_existing_no_retry_guard"
                                )
                                set_job_reason(
                                    job,
                                    "document_number_already_reserved",
                                )
                                job.note(
                                    "reservation guard already exists; "
                                    "automatic retry refused"
                                )
                            else:
                                job.status = "reserving_document_number"
                                job.document_number_status = (
                                    "request_started_unknown"
                                )
                                state.save_job(job)
                                try:
                                    reservation_response = perform_request(
                                        reservation_action,
                                        opener=transport_opener,
                                        maximum_body_bytes=4096,
                                    )
                                    job.document_number_response_status = (
                                        reservation_response.status
                                    )
                                    job.document_number_response_length = len(
                                        reservation_response.body
                                    )
                                    response_body = (
                                        reservation_response.body
                                    )
                                    if response_body and not any(response_body):
                                        job.document_number_response_shape = (
                                            "all_nul"
                                        )
                                    elif (
                                        len(response_body) == 1000
                                        and not any(response_body[16:])
                                    ):
                                        job.document_number_response_shape = (
                                            "fixed_nul_padded"
                                        )
                                    elif b"\0" in response_body:
                                        job.document_number_response_shape = (
                                            "invalid_nul_padded"
                                        )
                                    elif b"<" in response_body:
                                        job.document_number_response_shape = (
                                            "markup"
                                        )
                                    elif (
                                        response_body.strip(b" \t\r\n")
                                        != response_body
                                    ):
                                        job.document_number_response_shape = (
                                            "ascii_whitespace_wrapped"
                                        )
                                    else:
                                        job.document_number_response_shape = (
                                            "opaque"
                                        )
                                    state.save_job(job)
                                    document_number = (
                                        parse_document_number_response(
                                            reservation_response
                                        )
                                    )
                                except (
                                    OSError,
                                    TimeoutError,
                                    urllib.error.URLError,
                                    ValueError,
                                ) as error:
                                    job.status = (
                                        "document_number_reservation_unknown"
                                    )
                                    job.document_number_status = (
                                        "unknown_after_request"
                                    )
                                    set_job_reason(
                                        job,
                                        "document_number_reservation_unknown",
                                    )
                                    state.finish_document_reservation(
                                        job,
                                        "unknown_after_request",
                                    )
                                    job.note(
                                        "URLCheck may have allocated a "
                                        "document number; retry refused "
                                        f"({type(error).__name__})"
                                    )
                                else:
                                    job.document_number_status = "reserved"
                                    set_job_reason(job, None)
                                    reserved_document_number = document_number
                                    job.document_number_length = len(
                                        document_number
                                    )
                                    state.finish_document_reservation(
                                        job,
                                        "reserved",
                                    )
                                    try:
                                        bindings = build_runtime_bindings(
                                            bundle.primary,
                                            state.official_assets,
                                            (document_number,),
                                            hide_logo=param_5 == "1",
                                        )
                                    except (
                                        TypeError,
                                        ReportXProfileError,
                                    ) as error:
                                        bindings = None
                                        job.status = (
                                            "server_report_decoded_unrendered"
                                        )
                                        set_job_reason(
                                            job,
                                            "post_reservation_materialization_failed",
                                        )
                                        job.note(
                                            "reserved document number but "
                                            "runtime materialization failed "
                                            f"({type(error).__name__})"
                                        )

                if bindings is not None:
                    try:
                        rendered = _render_fp3_pdf_replayed(
                            bundle.primary,
                            bundle.additional,
                            font_map=state.font_map or None,
                            runtime_pictures=bindings.pictures,
                            runtime_text=bindings.text,
                            official_empty_pictures=(
                                bindings.official_empty_pictures
                            ),
                        )
                        if state.require_original_fonts:
                            validate_rendered_font_set(
                                rendered.font_files,
                                state.font_map,
                            )
                    except (TypeError, FP3RenderError) as error:
                        job.status = "server_report_decoded_unrendered"
                        set_job_reason(job, "fp3_render_rejected")
                        job.note(
                            "decoded ReportX outer container; FP3 renderer "
                            f"rejected it ({type(error).__name__})"
                        )
                    else:
                        set_job_reason(job, None)
                        rendered_pdf = rendered.pdf
                        job.artifact_kind = "server_report_response"
                        job.status = "server_report_rendered_pdf_unverified"
                        job.rendered_pdf_sha256 = rendered.pdf_sha256
                        job.rendered_page_count = rendered.page_count
                        job.rendered_object_count = rendered.object_count
                        job.rendered_replay_verified = True
                        job.rendered_fonts = tuple(
                            (Path(path).name, digest)
                            for path, digest in rendered.font_files
                        )
                        job.note(
                            "rendered the decoded FP3 with the pinned runtime "
                            "logo and reserved verification number"
                        )
    destination = state.out_dir / f"{job.id}{suffix}"
    if not state.write_artifact(destination, artifact.body):
        _finish_failure(job, state, "protocol_failed", "output_quota_exceeded")
        return
    written_sha256 = sha256_bytes(destination.read_bytes())
    if written_sha256 != artifact.sha256:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        _finish_failure(job, state, "protocol_failed", "artifact_hash_mismatch")
        return
    job.artifact_path = str(destination)
    job.artifact_sha256 = written_sha256
    if rendered_pdf is not None:
        rendered_destination = state.out_dir / f"{job.id}.rendered.pdf"
        if not state.write_artifact(rendered_destination, rendered_pdf):
            _finish_failure(
                job,
                state,
                "protocol_failed",
                "rendered_pdf_output_quota_exceeded",
            )
            return
        rendered_written = rendered_destination.read_bytes()
        if (
            sha256_bytes(rendered_written) != job.rendered_pdf_sha256
            or not is_pdf_container(rendered_written)
        ):
            try:
                rendered_destination.unlink()
            except FileNotFoundError:
                pass
            _finish_failure(
                job,
                state,
                "protocol_failed",
                "rendered_pdf_integrity_failed",
            )
            return
        job.rendered_pdf_path = str(rendered_destination)
    if reserved_document_number is not None and job.rendered_pdf_path:
        if not state.allow_completion_notification:
            job.completion_status = "explicit_opt_in_required"
        else:
            assert parsed is not None
            completion_action = build_print_completion_action(
                parsed,
                document_number=reserved_document_number,
                system_ip=local_ipv4_for(
                    job.request_host or "icert.yonsei.ac.kr"
                ),
                printer_model="YonseiSkills PDF",
            )
            job.completion_attempted = True
            job.completion_status = "request_started_unknown"
            state.save_job(job)
            try:
                completion_response = perform_request(
                    completion_action,
                    opener=transport_opener,
                    maximum_body_bytes=4096,
                )
            except (
                OSError,
                TimeoutError,
                urllib.error.URLError,
                ValueError,
            ) as error:
                job.completion_status = "unknown_after_request"
                set_job_reason(job, "completion_notification_unknown")
                job.note(
                    "print completion may have reached the server; retry refused "
                    f"({type(error).__name__})"
                )
                state.finish_document_reservation(
                    job,
                    "completion_unknown_after_request",
                )
            else:
                job.completion_response_status = completion_response.status
                if 200 <= completion_response.status < 300:
                    job.completion_notified = True
                    job.completion_status = "notified"
                    set_job_reason(job, None)
                    job.note(
                        "official print completion endpoint acknowledged the "
                        "durably saved PDF"
                    )
                    state.finish_document_reservation(
                        job,
                        "completion_notified",
                    )
                else:
                    job.completion_status = "non_success_response"
                    set_job_reason(job, "completion_notification_failed")
                    job.note(
                        "print completion returned a non-success status; "
                        "retry refused"
                    )
                    state.finish_document_reservation(
                        job,
                        "completion_non_success",
                    )
    job.note(
        f"saved unchanged server response ({len(artifact.body)} bytes); "
        "official verification not performed"
    )
    state.save_job(job)
    state.log(
        f"job {job.id} -> {job.status} "
        f"bytes={job.response_length} sha256={job.response_sha256}"
    )


def _process_job_guarded(job: Job, state: AgentState) -> None:
    try:
        process_job(job, state)
    except Exception:
        _finish_failure(
            job,
            state,
            "protocol_failed",
            "unexpected_worker_error",
        )
    finally:
        state.finish_job(job)


def schedule_job(job: Job, state: AgentState) -> tuple[str, str | None]:
    admission, existing_id = state.admit_job(job)
    if admission != "accepted":
        return admission, existing_id
    try:
        future = state.executor.submit(_process_job_guarded, job, state)
    except RuntimeError:
        _finish_failure(
            job,
            state,
            "protocol_failed",
            "worker_unavailable",
        )
        state.finish_job(job)
        return "worker_unavailable", None
    state.observe_future(job, future)
    return "accepted", None


def public_job_view(job: Job) -> dict[str, Any]:
    manifest = job.manifest()
    manifest.pop("messages", None)
    manifest["ticket"].pop("sha256", None)
    manifest["response"].pop("sha256", None)
    manifest["reportx_container"].pop("primary_sha256", None)
    manifest["reportx_container"].pop("additional_sha256", None)
    artifact_path = manifest["artifact"].get("path")
    if artifact_path:
        manifest["artifact"]["path"] = Path(str(artifact_path)).name
    rendered_path = manifest["rendered_pdf"].get("path")
    if rendered_path:
        manifest["rendered_pdf"]["path"] = Path(str(rendered_path)).name
    return manifest


def submit_print_job(
    state: AgentState,
    *,
    job_id: str,
    printer: str,
    expected_sha256: str,
    confirmed: bool,
) -> tuple[int, dict[str, Any]]:
    """Reserve and submit one physical print attempt exactly once.

    A timeout or nonzero ``lp`` exit is an ambiguous external mutation:
    CUPS may already have accepted the job. Such outcomes remain non-retryable.
    """

    if not confirmed or not job_id or not printer or not expected_sha256:
        return 400, {"ok": False, "error": "explicit_confirmation_required"}
    if printer not in list_cups_printers():
        return 400, {"ok": False, "error": "printer_not_found"}

    with state.lock:
        job = state.jobs.get(job_id)
        if job is None:
            return 404, {"ok": False, "error": "job_not_found"}
        if (
            job.status == "server_pdf_saved_unverified"
            and job.artifact_kind == "server_pdf_unverified"
        ):
            printable_path = job.artifact_path
            printable_sha256 = job.artifact_sha256
        elif job.status == "server_report_rendered_pdf_unverified":
            printable_path = job.rendered_pdf_path
            printable_sha256 = job.rendered_pdf_sha256
        else:
            printable_path = None
            printable_sha256 = None
        if not printable_path or not printable_sha256:
            return 409, {"ok": False, "error": "printable_pdf_not_ready"}
        if job.print_attempted:
            return 409, {
                "ok": False,
                "error": "print_already_attempted",
                "status": job.print_status,
            }
        path_obj = Path(printable_path)
        try:
            body = path_obj.read_bytes()
        except OSError:
            return 409, {"ok": False, "error": "artifact_unavailable"}
        if (
            expected_sha256 != printable_sha256
            or sha256_bytes(body) != printable_sha256
            or not is_pdf_container(body)
        ):
            return 409, {"ok": False, "error": "artifact_digest_mismatch"}

        # This reservation is persisted before invoking CUPS. It closes the
        # concurrent double-submit window and survives an ambiguous lp result.
        job.print_attempted = True
        job.print_status = "submitting"
        job.note("explicit print attempt reserved")
        state.save_job(job)

    ok, result = cups_print(path_obj, printer)
    with state.lock:
        job.print_status = result
        job.printed = ok
        job.note(f"explicit print attempt result: {result}")
        state.save_job(job)
    return (200 if ok else 409), {"ok": ok, "status": result}


def write_token_file(root: Path, token: str) -> Path:
    path = root / "agent.token"
    secure_write_text(path, token + "\n")
    return path


def load_or_create_token(root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    path = root / "agent.token"
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("agent.token must be a regular file")
        _private_chmod(path, 0o600)
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    token = secrets.token_urlsafe(32)
    write_token_file(root, token)
    return token


def _token(handler: BaseHTTPRequestHandler) -> str | None:
    return handler.headers.get("X-Agent-Token")


def _token_ok(state: AgentState, supplied: str | None) -> bool:
    return bool(supplied and secrets.compare_digest(state.token, supplied))


def _host_ok(handler: BaseHTTPRequestHandler) -> bool:
    raw = handler.headers.get("Host", "")
    try:
        parsed = urllib.parse.urlsplit("//" + raw)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _protocol_origin_ok(handler: BaseHTTPRequestHandler) -> bool:
    origin = handler.headers.get("Origin")
    return not origin or origin in ALLOWED_PROTOCOL_ORIGINS


def _protocol_submission_authorized(
    handler: BaseHTTPRequestHandler,
    state: AgentState,
) -> tuple[bool, str | None]:
    """Authorize exact-origin requests or one explicitly armed originless handoff."""

    if state.allow_fetch:
        if not state.readiness()["live_issue_ready"]:
            return False, None
        arm_id = state.consume_protocol_arm()
        return arm_id is not None, arm_id

    origin = handler.headers.get("Origin")
    if origin:
        if origin not in ALLOWED_PROTOCOL_ORIGINS:
            return False, None
        return True, state.consume_protocol_arm()
    if _token_ok(state, _token(handler)):
        return True, state.consume_protocol_arm()
    arm_id = state.consume_protocol_arm()
    return arm_id is not None, arm_id


class LoopbackHTTPServer(ThreadingHTTPServer):
    """HTTP server that never performs a reverse-DNS lookup at startup."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class ReportXHandler(BaseHTTPRequestHandler):
    server_version = "YonseiReportXLocal/0.6"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Do not log self.path: /SSO contains the complete encrypted ticket.
        if STATE is not None:
            STATE.log(f"{self.command} request -> {args[1] if len(args) > 1 else '-'}")

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin in ALLOWED_PROTOCOL_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        *,
        protocol: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if protocol:
            self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _control_authorized(self) -> bool:
        assert STATE is not None
        # Browser pages never need the control plane. Refuse every Origin even
        # when it names icert; the token is for local CLI use only.
        return self.headers.get("Origin") is None and _token_ok(STATE, _token(self))

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not _host_ok(self) or not _protocol_origin_ok(self):
            self._send(403, html_message("DENIED"))
            return
        self._send(204, b"", protocol=True)

    def do_GET(self) -> None:  # noqa: N802
        assert STATE is not None
        if not _host_ok(self):
            self._send(421, html_message("MISDIRECTED"))
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        if path in {"/SSO_ETC", "/sso_etc"}:
            if not _protocol_origin_ok(self):
                self._send(403, html_message("ORIGIN DENIED"))
                return
            self._send(200, html_message("REPORTX MAC AGENT READY"), protocol=True)
            return

        if path in {"/SSO", "/sso"}:
            if not _protocol_origin_ok(self):
                self._send(403, html_message("ORIGIN DENIED"))
                return
            param = (query.get("PARAM") or query.get("param") or [""])[0]
            # application/x-www-form-urlencoded turns '+' into a space; the
            # official service explicitly restores it before launching ReportX.
            param = param.replace(" ", "+")
            if not param:
                self._send(401, html_message("PARAM REQUIRED"), protocol=True)
                return
            try:
                envelope = TicketEnvelope.parse(param)
            except (TypeError, ValueError):
                self._send(400, html_message("INVALID PARAM"), protocol=True)
                return
            authorized, correlation_id = _protocol_submission_authorized(
                self,
                STATE,
            )
            if not authorized:
                self._send(401, html_message("HANDOFF NOT ARMED"), protocol=True)
                return
            job = Job(
                new_job_id(),
                utc_now(),
                "sso",
                param=param,
                correlation_id=correlation_id,
                ticket_length=envelope.raw_length,
                ticket_sha256=envelope.raw_sha256,
            )
            job.note("authorized SSO ticket received")
            admission, existing_id = schedule_job(job, STATE)
            if admission == "duplicate_active" and existing_id:
                self._send(
                    202,
                    html_message(f"JOB {existing_id} ALREADY ACTIVE"),
                    protocol=True,
                )
                return
            if admission != "accepted":
                self._send(429, html_message(admission.upper()), protocol=True)
                return
            self._send(200, html_message(f"JOB {job.id} ACCEPTED"), protocol=True)
            return

        if path in {"/GETCRYPTARIA", "/getcryptaria"}:
            self._send(404, html_message("UNSUPPORTED"), protocol=True)
            return

        if path in {"/bridge.js", "/intercept", "/cookies"}:
            self._send(410, html_message("CAPTURE MODE REMOVED"))
            return

        if path.startswith("/jobs/"):
            if not self._control_authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            job_id = path.removeprefix("/jobs/")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", job_id):
                self._json(400, {"ok": False, "error": "invalid_job_id"})
                return
            raw_wait = (query.get("wait") or ["0"])[0]
            try:
                wait_seconds = max(0.0, min(float(raw_wait), 30.0))
            except ValueError:
                self._json(400, {"ok": False, "error": "invalid_wait"})
                return
            job = STATE.wait_for_job(job_id, wait_seconds)
            if job is None:
                self._json(404, {"ok": False, "error": "job_not_found"})
                return
            with STATE.lock:
                public = public_job_view(job)
                terminal = job_is_settled(job)
            self._json(
                200,
                {"ok": True, "terminal": terminal, "job": public},
            )
            return

        if path in {"/health", "/status", "/jobs", "/printers"}:
            if not self._control_authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            if path == "/health":
                self._json(
                    200,
                    {
                        "ok": True,
                        "agent": "reportx-local",
                        "protocol": "cleanroom-v1",
                        "readiness": STATE.readiness(),
                    },
                )
                return
            if path == "/printers":
                self._json(
                    200,
                    {"ok": True, "printers": list_cups_printers()},
                )
                return
            with STATE.lock:
                jobs = [public_job_view(job) for job in list(STATE.jobs.values())[-50:]]
            correlation_id = (query.get("correlation_id") or [""])[0]
            if correlation_id:
                if not re.fullmatch(r"[0-9a-f]{24}", correlation_id):
                    self._json(
                        400,
                        {"ok": False, "error": "invalid_correlation_id"},
                    )
                    return
                jobs = [
                    job
                    for job in jobs
                    if job.get("correlation_id") == correlation_id
                ]
            self._json(
                200,
                {
                    "ok": True,
                    "agent": "reportx-local",
                    "allow_fetch": STATE.allow_fetch,
                    "allow_document_reservation": (
                        STATE.allow_document_reservation
                    ),
                    "allow_completion_notification": (
                        STATE.allow_completion_notification
                    ),
                    "official_assets": (
                        "ready"
                        if STATE.official_assets is not None
                        else "not_prepared"
                    ),
                    "output_dir": STATE.out_dir.name,
                    "jobs": jobs,
                    "readiness": STATE.readiness(),
                },
            )
            return

        self._send(404, html_message("NOT FOUND"))

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return None
        if length <= 0 or length > MAX_REQUEST_BODY:
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def do_POST(self) -> None:  # noqa: N802
        assert STATE is not None
        if not _host_ok(self):
            self._send(421, html_message("MISDIRECTED"))
            return
        path = urllib.parse.urlsplit(self.path).path.rstrip("/") or "/"
        if path in {"/SSO", "/sso"}:
            self._send(405, html_message("USE GET"), protocol=True)
            return
        if path in {"/intercept", "/cookies", "/print"}:
            self._send(410, html_message("LEGACY CONTROL REMOVED"))
            return
        if path == "/arm":
            if not self._control_authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            readiness = STATE.readiness()
            if STATE.allow_fetch and not readiness["live_issue_ready"]:
                self._json(
                    409,
                    {
                        "ok": False,
                        "error": "live_issue_not_ready",
                        "readiness": readiness,
                    },
                )
                return
            ttl, arm_id = STATE.arm_protocol_once()
            self._json(
                200,
                {
                    "ok": True,
                    "armed": True,
                    "one_shot": True,
                    "ttl_seconds": ttl,
                    "arm_id": arm_id,
                },
            )
            return
        if path != "/print-job":
            self._send(404, html_message("NOT FOUND"))
            return
        if not self._control_authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        payload = self._read_json()
        if payload is None:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        status, result = submit_print_job(
            STATE,
            job_id=str(payload.get("job_id") or ""),
            printer=str(payload.get("printer") or ""),
            expected_sha256=str(payload.get("expected_sha256") or ""),
            confirmed=payload.get("confirm") is True,
        )
        self._json(status, result)


def serve(host: str, port: int, state: AgentState) -> None:
    global STATE
    STATE = state
    server = LoopbackHTTPServer((host, port), ReportXHandler)
    state.log(f"listening on http://{host}:{port}")
    state.log(f"network={'enabled' if state.allow_fetch else 'disabled'}")
    state.log(
        "document reservation="
        + (
            "explicitly enabled"
            if state.allow_document_reservation
            else "disabled"
        )
    )
    state.log(
        "print completion notification="
        + (
            "explicitly enabled"
            if state.allow_completion_notification
            else "disabled"
        )
    )
    state.log(
        "official assets="
        + ("ready" if state.official_assets is not None else "not prepared")
    )
    state.log(f"private state dir: {state.root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state.log("shutting down")
    finally:
        server.server_close()
        state.close()


def configure_utf8_stdio() -> None:
    """Keep Korean agent logs and diagnostics lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    if hasattr(os, "umask"):
        os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument(
        "--title-font",
        type=Path,
        help="Redistribution-authorized Yonsei title TrueType font.",
    )
    parser.add_argument(
        "--body-font",
        type=Path,
        help="Redistribution-authorized Yonsei body TrueType font.",
    )
    parser.add_argument(
        "--allow-fetch",
        action="store_true",
        help="Opt in to the decoded, allowlisted HTTPS URLFile request",
    )
    parser.add_argument(
        "--reserve-document-number",
        action="store_true",
        help=(
            "Explicitly permit one mutating URLCheck document-number "
            "reservation; a durable no-retry guard is written first"
        ),
    )
    parser.add_argument(
        "--notify-print-completion",
        action="store_true",
        help=(
            "After a verified durable PDF save, send the official one-shot "
            "print-completion GET; never retry an uncertain request"
        ),
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Control-plane token (default: load/create agent.token)",
    )
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing non-loopback --host.", file=sys.stderr)
        return 2
    if args.reserve_document_number and not args.allow_fetch:
        print(
            "--reserve-document-number requires --allow-fetch.",
            file=sys.stderr,
        )
        return 2
    if args.notify_print_completion and not args.reserve_document_number:
        print(
            "--notify-print-completion requires --reserve-document-number.",
            file=sys.stderr,
        )
        return 2
    if args.allow_fetch and (
        args.title_font is None or args.body_font is None
    ):
        print(
            "Original Yonsei title and body fonts are required before "
            "fetching and rendering a report.",
            file=sys.stderr,
        )
        return 2

    root = args.dir.expanduser()
    try:
        font_map = build_yonsei_font_map(
            args.title_font,
            args.body_font,
        )
        secure_mkdir(root)
        token = load_or_create_token(root, args.token)
        write_token_file(root, token)
        state = AgentState(
            root,
            allow_fetch=bool(args.allow_fetch),
            allow_document_reservation=bool(args.reserve_document_number),
            allow_completion_notification=bool(
                args.notify_print_completion
            ),
            token=token,
            font_map=font_map,
            require_original_fonts=bool(args.allow_fetch),
        )
    except (OSError, ValueError) as error:
        print(
            f"Cannot initialize private state: {type(error).__name__}",
            file=sys.stderr,
        )
        return 2

    socket_module = __import__("socket")
    probe = socket_module.socket()
    try:
        probe.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
        probe.bind((args.host, args.port))
    except OSError as error:
        print(
            f"Cannot bind {args.host}:{args.port}: {error}\n"
            "Stop any process already using the ReportX loopback port.",
            file=sys.stderr,
        )
        return 1
    finally:
        probe.close()

    serve(args.host, args.port, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
