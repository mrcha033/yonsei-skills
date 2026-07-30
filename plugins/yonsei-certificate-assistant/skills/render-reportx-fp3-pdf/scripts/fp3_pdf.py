#!/usr/bin/env python3
"""Render a bounded FastReport VCL prepared-report (FP3) XML stream to PDF.

This is a data-only compatibility renderer.  It never executes report scripts,
loads external resources, performs network requests, or talks to a printer.
The implementation intentionally supports the prepared-page subset observed in
FastReport VCL 4.x:

* ``preparedreport`` / ``previewpages`` / ``sourcepages`` / ``dictionary``;
* band instances and delta attributes (``l``, ``t``, ``w``, ``h``, ``u``);
* memo/text, line, shape, checkbox, and encoded picture objects;
* JPEG, bounded 8-bit PNG, and uncompressed 24/32-bit BMP sidecars;
* multipage PDF with embedded BMP-Unicode TrueType fonts when necessary.

Unknown drawable object classes, missing dictionary entries, unsupported image
encodings, restricted fonts, and unsafe XML fail closed.  A rendered PDF is a
compatibility artifact, not an assertion that a certificate is official.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import os
import re
import stat
import struct
import tempfile
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence
from xml.etree import ElementTree as ET


MAX_FP3_BYTES = 32 * 1024 * 1024
MAX_XML_ELEMENTS = 100_000
MAX_XML_DEPTH = 64
MAX_PAGES = 64
MAX_OBJECTS_PER_PAGE = 20_000
MAX_SIDECARS = 256
MAX_SIDECAR_BYTES = 64 * 1024 * 1024
MAX_TOTAL_SIDECAR_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_CLEAR_TEXT_CHARS = 1_000_000
PX_TO_PT = 72.0 / 96.0
MM_TO_PT = 72.0 / 25.4

_SAFE_ROOT = "preparedreport"
_BAND_TYPES = {
    "TfrxBand",
    "TfrxReportTitle",
    "TfrxReportSummary",
    "TfrxPageHeader",
    "TfrxPageFooter",
    "TfrxColumnHeader",
    "TfrxColumnFooter",
    "TfrxHeader",
    "TfrxFooter",
    "TfrxDataBand",
    "TfrxMasterData",
    "TfrxDetailData",
    "TfrxSubdetailData",
    "TfrxGroupHeader",
    "TfrxGroupFooter",
    "TfrxChild",
    "TfrxOverlay",
    "TfrxNullBand",
}
_MEMO_TYPES = {"TfrxMemoView", "TfrxCustomMemoView", "TfrxDMPMemoView"}
_LINE_TYPES = {"TfrxLineView", "TfrxCustomLineView", "TfrxDMPLineView"}
_SHAPE_TYPES = {"TfrxShapeView"}
_PICTURE_TYPES = {"TfrxPictureView"}
_BARCODE_TYPES = {
    "TfrxBarcodeView",
    "TfrxBarCodeView",
    "TfrxBarcode2DView",
    "TfrxBarCode2DView",
}
_CHECKBOX_TYPES = {"TfrxCheckBoxView"}
_GENERIC_VIEW_TYPES = {"TfrxView", "TfrxReportComponent"}
_SUPPORTED_TYPES = (
    _BAND_TYPES
    | _MEMO_TYPES
    | _LINE_TYPES
    | _SHAPE_TYPES
    | _PICTURE_TYPES
    | _BARCODE_TYPES
    | _CHECKBOX_TYPES
    | _GENERIC_VIEW_TYPES
)
_ALIASES = {
    "l": "Left",
    "t": "Top",
    "w": "Width",
    "h": "Height",
    "u": "Text",
}
_PAGE_ATTRIBUTES = frozenset(
    {
        "Name",
        "PaperWidth",
        "PaperHeight",
        "PaperSize",
        "Orientation",
        "LeftMargin",
        "TopMargin",
        "RightMargin",
        "BottomMargin",
        "Columns",
        "ColumnWidth",
        "ColumnPositions.Text",
        "HGuides.Text",
        "VGuides.Text",
        "LargeDesignHeight",
        "PrintOnPreviousPage",
        "OnBeforePrint",
        "OnAfterPrint",
    }
)
_COMMON_OBJECT_ATTRIBUTES = frozenset(
    {
        "Name",
        "Left",
        "Top",
        "Width",
        "Height",
        "Visible",
        "Printable",
        "PrintOnly",
        "Color",
        "Transparent",
        "FillType",
        "Frame.Typ",
        "Frame.Color",
        "Frame.Width",
        "Frame.Style",
        "ShowHint",
        "Tag",
        "TagStr",
    }
)
_BAND_ATTRIBUTES = _COMMON_OBJECT_ATTRIBUTES | frozenset(
    {
        "ColumnGap",
        "ColumnWidth",
        "RowCount",
        "OnBeforePrint",
        "OnAfterPrint",
    }
)
_MEMO_ATTRIBUTES = _COMMON_OBJECT_ATTRIBUTES | frozenset(
    {
        "Text",
        "Font.Name",
        "Font.Color",
        "Font.Height",
        "Font.Size",
        "Font.Style",
        "Font.Charset",
        "ParentFont",
        "GapX",
        "GapY",
        "CharSpacing",
        "LineSpacing",
        "WordWrap",
        "VAlign",
        "HAlign",
        "Rotation",
        "Clipped",
        "AllowExpressions",
        "AutoWidth",
        "Wysiwyg",
    }
)
_PICTURE_ATTRIBUTES = _COMMON_OBJECT_ATTRIBUTES | frozenset(
    {
        "Align",
        "ImageIndex",
        "PictureIndex",
        "BlobIndex",
        "Picture.Data",
        "Picture",
        "Data",
        "Image.Data",
        "Stretched",
        "KeepAspectRatio",
        "Center",
        "HightQuality",
        "TransparentColor",
    }
)
_SHAPE_ATTRIBUTES = _COMMON_OBJECT_ATTRIBUTES | frozenset({"Shape"})
_CHECKBOX_ATTRIBUTES = _COMMON_OBJECT_ATTRIBUTES | frozenset({"Checked"})
_EVENT_ATTRIBUTES = frozenset({"OnBeforePrint", "OnAfterPrint"})
_BOOLEAN_ATTRIBUTES = frozenset(
    {
        "Visible",
        "Printable",
        "PrintOnly",
        "Transparent",
        "ShowHint",
        "ParentFont",
        "WordWrap",
        "Clipped",
        "AllowExpressions",
        "AutoWidth",
        "Wysiwyg",
        "Stretched",
        "KeepAspectRatio",
        "Center",
        "HightQuality",
        "Checked",
    }
)
_NUMERIC_ATTRIBUTES = frozenset(
    {
        "Left",
        "Top",
        "Width",
        "Height",
        "Frame.Width",
        "Font.Height",
        "Font.Size",
        "GapX",
        "GapY",
        "CharSpacing",
        "LineSpacing",
        "Rotation",
        "ColumnGap",
        "ColumnWidth",
    }
)
_INTEGER_ATTRIBUTES = frozenset(
    {
        "Frame.Typ",
        "Font.Style",
        "Font.Charset",
        "Tag",
        "RowCount",
        "ImageIndex",
        "PictureIndex",
        "BlobIndex",
    }
)
_COLOR_ATTRIBUTES = frozenset(
    {
        "Color",
        "Frame.Color",
        "Font.Color",
        "TransparentColor",
    }
)
_IMAGE_PAYLOAD_ATTRIBUTES = (
    "Picture.Data",
    "Picture",
    "Data",
    "Image.Data",
)
_FONT_CANDIDATES = {
    "arial": (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ),
    "arial bold": (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ),
    "tahoma": (
        "/System/Library/Fonts/Supplemental/Tahoma.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    "tahoma bold": (
        "/System/Library/Fonts/Supplemental/Tahoma Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "times new roman": (
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    ),
    "courier new": (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ),
    "applegothic": (
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    ),
    "korean-sans": (
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    ),
    "korean-serif": (
        "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    ),
    "korean-fallback": (
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
}
_KOREAN_SANS_NAMES = {
    "굴림",
    "굴림체",
    "돋움",
    "돋움체",
    "맑은 고딕",
    "malgun gothic",
    "gulim",
    "dotum",
}
_KOREAN_SERIF_NAMES = {
    "바탕",
    "바탕체",
    "batang",
}
_REPORTX_ANSI_ATTRIBUTES = (b"Font.Name", b"TagStr")


class FP3RenderError(ValueError):
    """Raised when an FP3 stream cannot be rendered without silent loss."""


def _normalize_reportx_ansi_attributes(data: bytes) -> bytes:
    """Repair the two ANSI attributes emitted into ReportX's UTF-8 FP3 XML.

    The official Windows viewer writes ``Font.Name`` and ``TagStr`` through
    ANSI VCL string properties even though the document declaration is UTF-8.
    Values already valid as UTF-8 are retained.  An invalid value must decode
    wholly and strictly as CP949; all other encoding errors remain fatal.
    """

    replacements: list[tuple[int, int, bytes]] = []
    for name in _REPORTX_ANSI_ATTRIBUTES:
        pattern = re.compile(
            rb"(?<![A-Za-z0-9_.:-])"
            + re.escape(name)
            + rb'="([^"]*)"'
        )
        for match in pattern.finditer(data):
            raw = match.group(1)
            try:
                raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                try:
                    normalized = raw.decode(
                        "cp949",
                        errors="strict",
                    ).encode("utf-8")
                except UnicodeDecodeError as error:
                    raise FP3RenderError(
                        f"{name.decode('ascii')} is neither UTF-8 nor CP949"
                    ) from error
                replacements.append((match.start(1), match.end(1), normalized))
    if replacements:
        chunks: list[bytes] = []
        offset = 0
        for start, end, value in sorted(replacements):
            if start < offset:
                raise FP3RenderError("overlapping legacy FP3 attributes")
            chunks.extend((data[offset:start], value))
            offset = end
        chunks.append(data[offset:])
        normalized_data = b"".join(chunks)
    else:
        normalized_data = data
    try:
        normalized_data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise FP3RenderError(
            "FP3 contains invalid UTF-8 outside supported ANSI attributes"
        ) from error
    return normalized_data


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"", "0", "false", "no", "off"}:
        return False
    raise FP3RenderError("boolean attribute has an unsupported value")


def _float(
    attrs: Mapping[str, str],
    key: str,
    default: float = 0.0,
) -> float:
    raw = attrs.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw.replace(",", "."))
    except ValueError as error:
        raise FP3RenderError(f"{key} is not numeric") from error
    if not math.isfinite(value) or abs(value) > 1_000_000:
        raise FP3RenderError(f"{key} is outside policy")
    return value


def _int(
    attrs: Mapping[str, str],
    key: str,
    default: int = 0,
) -> int:
    raw = attrs.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw, 0)
    except ValueError:
        try:
            parsed = float(raw.replace(",", "."))
        except ValueError as error:
            raise FP3RenderError(f"{key} is not integral") from error
        if not math.isfinite(parsed) or not parsed.is_integer():
            raise FP3RenderError(f"{key} is not integral")
        value = int(parsed)
    if abs(value) > 1_000_000_000:
        raise FP3RenderError(f"{key} is outside policy")
    return value


def _sanitize_pdf_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]", "", value)
    return cleaned[:80] or fallback


def _pdf_number(value: float) -> str:
    if not math.isfinite(value):
        raise FP3RenderError("non-finite PDF coordinate")
    if abs(value) < 0.000_000_5:
        return "0"
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text != "-0" else "0"


def _pdf_literal_bytes(data: bytes) -> bytes:
    escaped = (
        data.replace(b"\\", b"\\\\")
        .replace(b"(", b"\\(")
        .replace(b")", b"\\)")
        .replace(b"\r", b"\\r")
        .replace(b"\n", b"\\n")
    )
    return b"(" + escaped + b")"


def _pdf_string(value: str) -> bytes:
    return _pdf_literal_bytes(value.encode("utf-8"))


def _delphi_color(raw: str | None, *, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if raw is None or raw == "":
        return default
    try:
        value = int(float(raw))
    except ValueError as error:
        raise FP3RenderError("invalid Delphi color") from error
    if value < 0:
        # VCL system colors depend on the Windows theme.  Only the two colors
        # observed in the ReportX print path have theme-independent print
        # equivalents.  Silently mapping any other negative value would turn
        # an unknown color into plausible-looking but incorrect output.
        if value in {-16777211, -16777201}:  # clWindow / clBtnFace
            return (1.0, 1.0, 1.0)
        if value == -16777208:  # clWindowText
            return (0.0, 0.0, 0.0)
        raise FP3RenderError("unsupported Delphi system color")
    value &= 0xFFFFFF
    red = value & 0xFF
    green = (value >> 8) & 0xFF
    blue = (value >> 16) & 0xFF
    return (red / 255.0, green / 255.0, blue / 255.0)


def _validate_event_reference(value: str) -> None:
    if value and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,127}", value) is None:
        raise FP3RenderError("event reference is outside policy")


def _allowed_attributes(class_name: str) -> frozenset[str]:
    if class_name in _BAND_TYPES:
        return _BAND_ATTRIBUTES
    if class_name in _MEMO_TYPES:
        return _MEMO_ATTRIBUTES
    if class_name in _PICTURE_TYPES | _BARCODE_TYPES:
        return _PICTURE_ATTRIBUTES
    if class_name in _SHAPE_TYPES:
        return _SHAPE_ATTRIBUTES
    if class_name in _CHECKBOX_TYPES:
        return _CHECKBOX_ATTRIBUTES
    if class_name in _LINE_TYPES | _GENERIC_VIEW_TYPES:
        return _COMMON_OBJECT_ATTRIBUTES
    raise FP3RenderError(f"unsupported FP3 object class {class_name}")


def _validate_object_attributes(
    class_name: str,
    attrs: Mapping[str, str],
) -> None:
    """Reject visual semantics that the renderer would otherwise ignore."""

    unknown = set(attrs) - _allowed_attributes(class_name)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise FP3RenderError(
            f"unsupported attributes on {class_name}: {names}"
        )
    for key in _BOOLEAN_ATTRIBUTES & attrs.keys():
        _bool(attrs.get(key))
    for key in _NUMERIC_ATTRIBUTES & attrs.keys():
        _float(attrs, key)
    for key in _INTEGER_ATTRIBUTES & attrs.keys():
        value = _int(attrs, key)
        if key in {"ImageIndex", "PictureIndex", "BlobIndex", "RowCount"}:
            if value < 0:
                raise FP3RenderError(f"{key} is outside policy")
        elif key == "Frame.Typ" and value & ~0x0F:
            raise FP3RenderError("Frame.Typ contains unsupported edges")
        elif key == "Font.Style" and value & ~0x0F:
            raise FP3RenderError("Font.Style contains unsupported flags")
        elif key == "Font.Charset" and value not in {0, 1}:
            raise FP3RenderError("Font.Charset is unsupported")
    for key in _COLOR_ATTRIBUTES & attrs.keys():
        _delphi_color(attrs.get(key), default=(0.0, 0.0, 0.0))
    for key in _EVENT_ATTRIBUTES & attrs.keys():
        _validate_event_reference(attrs[key])
    if len(attrs.get("Name", "")) > 256:
        raise FP3RenderError("object name is outside policy")
    if len(attrs.get("TagStr", "")) > 8192:
        raise FP3RenderError("TagStr is outside policy")
    if len(attrs.get("Font.Name", "")) > 256:
        raise FP3RenderError("font name is outside policy")

    fill_type = attrs.get("FillType", "ftBrush")
    if fill_type not in {"", "ftBrush"}:
        raise FP3RenderError(f"unsupported fill type {fill_type}")
    frame_style = attrs.get("Frame.Style", "fsSolid")
    if frame_style not in {
        "",
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "fsSolid",
        "fsDash",
        "fsDot",
        "fsDashDot",
        "fsDashDotDot",
        "fsDouble",
        "fsClear",
    }:
        raise FP3RenderError("unsupported frame style")

    align = attrs.get("Align", "baNone")
    if align not in {"", "baNone", "baCenter"}:
        raise FP3RenderError("unsupported component alignment")

    if class_name in _MEMO_TYPES:
        if attrs.get("HAlign", "haLeft") not in {
            "",
            "haLeft",
            "haRight",
            "haCenter",
        }:
            raise FP3RenderError("unsupported memo horizontal alignment")
        if attrs.get("VAlign", "vaTop") not in {
            "",
            "vaTop",
            "vaCenter",
            "vaBottom",
        }:
            raise FP3RenderError("unsupported memo vertical alignment")
        if _bool(attrs.get("AllowExpressions"), False):
            raise FP3RenderError("unprepared memo expressions are forbidden")
        if _bool(attrs.get("Wysiwyg"), False):
            raise FP3RenderError("Wysiwyg memo metrics are unsupported")
        if "ParentFont" in attrs:
            if _bool(attrs.get("ParentFont")):
                raise FP3RenderError("inherited memo fonts are unsupported")
            required_font = {
                "Font.Name",
                "Font.Color",
                "Font.Height",
                "Font.Style",
            }
            if not required_font.issubset(attrs):
                raise FP3RenderError(
                    "ParentFont=False lacks a complete font tuple"
                )

    if class_name in _PICTURE_TYPES | _BARCODE_TYPES:
        payloads = [
            key for key in _IMAGE_PAYLOAD_ATTRIBUTES if attrs.get(key)
        ]
        if len(payloads) > 1:
            raise FP3RenderError("picture has ambiguous embedded payloads")


@dataclass(frozen=True)
class BaseEntry:
    class_name: str
    source_page: int
    element: ET.Element


@dataclass
class DrawObject:
    class_name: str
    x: float
    y: float
    width: float
    height: float
    attrs: dict[str, str]
    order: int
    text: str = ""
    image_index: int | None = None


@dataclass
class PageModel:
    width_pt: float
    height_pt: float
    margin_left_pt: float
    margin_top_pt: float
    objects: list[DrawObject] = field(default_factory=list)


@dataclass(frozen=True)
class FP3Model:
    pages: tuple[PageModel, ...]
    class_inventory: tuple[tuple[str, int], ...]
    source_sha256: str
    picture_cache: tuple[bytes, ...] = field(repr=False)
    excluded_invisible_count: int = 0
    excluded_nonprintable_count: int = 0


@dataclass(frozen=True)
class RenderedFP3:
    pdf: bytes = field(repr=False)
    page_count: int
    object_count: int
    source_sha256: str
    pdf_sha256: str
    class_inventory: tuple[tuple[str, int], ...]
    font_files: tuple[tuple[str, str], ...]
    image_count: int
    excluded_invisible_count: int
    excluded_nonprintable_count: int

    def manifest(self) -> dict[str, object]:
        return {
            "schema": "reportx-fp3-pdf/v1",
            "status": "rendered_pdf_unverified",
            "page_count": self.page_count,
            "object_count": self.object_count,
            "source_sha256": self.source_sha256,
            "pdf_sha256": self.pdf_sha256,
            "class_inventory": dict(self.class_inventory),
            "font_files": [
                {"path": path, "sha256": digest}
                for path, digest in self.font_files
            ],
            "image_count": self.image_count,
            "excluded_invisible_count": self.excluded_invisible_count,
            "excluded_nonprintable_count": self.excluded_nonprintable_count,
            "official_verification": "not_performed",
        }


def _bounded_xml_root(data: bytes) -> ET.Element:
    if not isinstance(data, bytes):
        raise TypeError("FP3 input must be immutable bytes")
    if not data or len(data) > MAX_FP3_BYTES:
        raise FP3RenderError("FP3 input size is outside policy")
    # ElementTree expands internal entities.  Reject declarations before the
    # parser sees them, scanning the complete bounded input and its NUL-stripped
    # form so UTF-16/32 declarations cannot bypass the policy.
    probe = data.lower()
    nul_stripped_probe = probe.replace(b"\0", b"")
    if any(
        token in candidate
        for candidate in (probe, nul_stripped_probe)
        for token in (b"<!doctype", b"<!entity")
    ):
        raise FP3RenderError("DTD and entities are forbidden")
    if data.startswith((b"\x1f\x8b", b"PK\x03\x04")):
        raise FP3RenderError("compressed or archive FP3 input is unsupported")
    data = _normalize_reportx_ansi_attributes(data)
    parser = ET.XMLPullParser(events=("start", "end"))
    count = 0
    depth = 0
    root: ET.Element | None = None
    try:
        for offset in range(0, len(data), 64 * 1024):
            parser.feed(data[offset : offset + 64 * 1024])
            for event, element in parser.read_events():
                if event == "start":
                    count += 1
                    depth += 1
                    if root is None:
                        root = element
                    if count > MAX_XML_ELEMENTS:
                        raise FP3RenderError(
                            "FP3 element count exceeds policy"
                        )
                    if depth > MAX_XML_DEPTH:
                        raise FP3RenderError("FP3 XML depth exceeds policy")
                else:
                    depth -= 1
        parser.close()
        for event, element in parser.read_events():
            if event == "start":
                count += 1
                depth += 1
                if root is None:
                    root = element
                if count > MAX_XML_ELEMENTS:
                    raise FP3RenderError(
                        "FP3 element count exceeds policy"
                    )
                if depth > MAX_XML_DEPTH:
                    raise FP3RenderError("FP3 XML depth exceeds policy")
            else:
                depth -= 1
    except ET.ParseError as error:
        raise FP3RenderError("FP3 is not well-formed XML") from error
    if root is None or depth != 0:
        raise FP3RenderError("FP3 XML tree is incomplete")
    if _local_name(root.tag).lower() != _SAFE_ROOT:
        raise FP3RenderError("FP3 root must be preparedreport")
    return root


def _child(root: ET.Element, name: str, *, required: bool = True) -> ET.Element | None:
    lowered = name.lower()
    for child in root:
        if _local_name(child.tag).lower() == lowered:
            return child
    if required:
        raise FP3RenderError(f"FP3 is missing {name}")
    return None


def _normalized_attrs(
    base: Mapping[str, str],
    delta: Mapping[str, str],
) -> dict[str, str]:
    merged = dict(base)
    for key, value in delta.items():
        merged[_ALIASES.get(key, key)] = value
    return merged


def _build_source_index(
    sourcepages: ET.Element,
) -> tuple[list[ET.Element], dict[str, BaseEntry]]:
    pages = list(sourcepages)
    if any(
        _local_name(child.tag) not in {"TfrxReportPage", "TfrxDMPPage"}
        for child in pages
    ):
        raise FP3RenderError("sourcepages contains an unsupported entry")
    if not pages or len(pages) > MAX_PAGES:
        raise FP3RenderError("source page count is outside policy")
    index: dict[str, BaseEntry] = {}

    def walk(element: ET.Element, page_no: int) -> None:
        name = element.attrib.get("Name")
        if name:
            key = f"Page{page_no}.{name}"
            if key in index:
                raise FP3RenderError(f"duplicate source object {key}")
            index[key] = BaseEntry(_local_name(element.tag), page_no, element)
        for child in element:
            walk(child, page_no)

    for page_no, page in enumerate(pages):
        walk(page, page_no)
    return pages, index


def _dictionary_index(
    dictionary: ET.Element,
    source_index: Mapping[str, BaseEntry],
) -> dict[str, BaseEntry]:
    result: dict[str, BaseEntry] = {}
    for item in dictionary:
        if list(item) or not set(item.attrib) <= {"name", "Name"}:
            raise FP3RenderError("dictionary item has unsupported structure")
        alias = _local_name(item.tag)
        name = item.attrib.get("name") or item.attrib.get("Name")
        if not alias or not name:
            raise FP3RenderError("dictionary item lacks alias or name")
        if alias in result:
            raise FP3RenderError(f"duplicate dictionary alias {alias}")
        try:
            result[alias] = source_index[name]
        except KeyError as error:
            raise FP3RenderError(
                f"dictionary alias {alias} references missing source object"
            ) from error
    return result


def _page_source_index(
    preview_page: ET.Element,
    dictionary: Mapping[str, BaseEntry],
    fallback: int,
    source_count: int,
) -> int:
    found: list[int] = []
    for element in preview_page.iter():
        entry = dictionary.get(_local_name(element.tag))
        if entry is not None:
            found.append(entry.source_page)
    if found:
        counts: dict[int, int] = {}
        for value in found:
            counts[value] = counts.get(value, 0) + 1
        return max(sorted(counts), key=counts.get)
    return min(fallback, source_count - 1)


def _page_geometry(source_page: ET.Element) -> tuple[float, float, float, float]:
    attrs = source_page.attrib
    unknown = set(attrs) - _PAGE_ATTRIBUTES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise FP3RenderError(f"unsupported report-page attributes: {names}")
    for key in (
        "PaperWidth",
        "PaperHeight",
        "LeftMargin",
        "TopMargin",
        "RightMargin",
        "BottomMargin",
        "ColumnWidth",
    ):
        if key in attrs:
            _float(attrs, key)
    for key in ("PaperSize", "Columns"):
        if key in attrs and _int(attrs, key) < 0:
            raise FP3RenderError(f"{key} is outside policy")
    for key in ("LargeDesignHeight", "PrintOnPreviousPage"):
        if key in attrs:
            _bool(attrs.get(key))
    for key in _EVENT_ATTRIBUTES & attrs.keys():
        _validate_event_reference(attrs[key])
    for key in ("ColumnPositions.Text", "HGuides.Text", "VGuides.Text"):
        if len(attrs.get(key, "")) > 8192:
            raise FP3RenderError(f"{key} is outside policy")
    width_mm = _float(attrs, "PaperWidth", 210.0)
    height_mm = _float(attrs, "PaperHeight", 297.0)
    orientation = attrs.get("Orientation", "")
    if orientation not in {"", "poPortrait", "poLandscape"}:
        raise FP3RenderError("unsupported page orientation")
    if orientation.lower() == "polandscape" and width_mm < height_mm:
        width_mm, height_mm = height_mm, width_mm
    if not (10 <= width_mm <= 2000 and 10 <= height_mm <= 2000):
        raise FP3RenderError("page geometry is outside policy")
    margin_left = _float(attrs, "LeftMargin", 0.0)
    margin_top = _float(attrs, "TopMargin", 0.0)
    margin_right = _float(attrs, "RightMargin", 0.0)
    margin_bottom = _float(attrs, "BottomMargin", 0.0)
    if min(margin_left, margin_top, margin_right, margin_bottom) < 0:
        raise FP3RenderError("negative page margins are unsupported")
    return (
        width_mm * MM_TO_PT,
        height_mm * MM_TO_PT,
        margin_left * MM_TO_PT,
        margin_top * MM_TO_PT,
    )


def _picture_cache(root: ET.Element) -> tuple[bytes, ...]:
    element = _child(root, "picturecache", required=False)
    if element is None:
        return ()
    images: list[bytes] = []
    total = 0
    for item in element:
        if _local_name(item.tag).lower() != "item":
            raise FP3RenderError("picture cache contains an unknown entry")
        if set(item.attrib) != {"stream"} or list(item):
            raise FP3RenderError("picture cache item has unsupported structure")
        encoded = item.attrib["stream"]
        if (
            not encoded
            or len(encoded) % 2
            or len(encoded) > MAX_SIDECAR_BYTES * 2
            or re.fullmatch(r"[0-9A-Fa-f]+", encoded) is None
        ):
            raise FP3RenderError("picture cache item is outside policy")
        try:
            image = bytes.fromhex(encoded)
        except ValueError as error:
            raise FP3RenderError("picture cache item is not strict hex") from error
        total += len(image)
        if total > MAX_TOTAL_SIDECAR_BYTES:
            raise FP3RenderError("aggregate picture cache exceeds policy")
        images.append(image)
        if len(images) > MAX_SIDECARS:
            raise FP3RenderError("too many picture cache items")
    return tuple(images)


def parse_fp3(data: bytes) -> FP3Model:
    """Parse an FP3 prepared report into a bounded data-only page model."""

    root = _bounded_xml_root(data)
    if root.attrib:
        raise FP3RenderError("preparedreport attributes are unsupported")
    allowed_sections = {
        "previewpages",
        "logicalpagenumbers",
        "outline",
        "report",
        "sourcepages",
        "dictionary",
        "picturecache",
    }
    section_counts: dict[str, int] = {}
    for child in root:
        name = _local_name(child.tag).lower()
        if name not in allowed_sections:
            raise FP3RenderError(f"unsupported preparedreport section {name}")
        section_counts[name] = section_counts.get(name, 0) + 1
        if section_counts[name] > 1:
            raise FP3RenderError(f"duplicate preparedreport section {name}")
    previewpages = _child(root, "previewpages")
    sourcepages = _child(root, "sourcepages")
    dictionary_element = _child(root, "dictionary")
    assert previewpages is not None
    assert sourcepages is not None
    assert dictionary_element is not None

    source_page_elements, source_index = _build_source_index(sourcepages)
    dictionary = _dictionary_index(dictionary_element, source_index)
    preview_page_elements = list(previewpages)
    if any(
        re.fullmatch(
            r"page\d+",
            _local_name(item.tag),
            flags=re.IGNORECASE,
        )
        is None
        for item in preview_page_elements
    ):
        raise FP3RenderError("previewpages contains an unsupported entry")
    if not preview_page_elements or len(preview_page_elements) > MAX_PAGES:
        raise FP3RenderError("preview page count is outside policy")

    class_counts: dict[str, int] = {}
    pages: list[PageModel] = []
    order = 0
    total_text_chars = 0
    excluded_invisible_count = 0
    excluded_nonprintable_count = 0

    for preview_no, preview_page in enumerate(preview_page_elements):
        source_no = _page_source_index(
            preview_page,
            dictionary,
            preview_no,
            len(source_page_elements),
        )
        width_pt, height_pt, margin_left_pt, margin_top_pt = _page_geometry(
            source_page_elements[source_no]
        )
        model = PageModel(
            width_pt=width_pt,
            height_pt=height_pt,
            margin_left_pt=margin_left_pt,
            margin_top_pt=margin_top_pt,
        )

        def instantiate(
            element: ET.Element,
            parent_x: float,
            parent_y: float,
        ) -> None:
            nonlocal order, total_text_chars
            nonlocal excluded_invisible_count
            nonlocal excluded_nonprintable_count
            alias = _local_name(element.tag)
            entry = dictionary.get(alias)
            if entry is not None:
                class_name = entry.class_name
                attrs = _normalized_attrs(entry.element.attrib, element.attrib)
            else:
                class_name = alias
                attrs = _normalized_attrs({}, element.attrib)
                if not class_name.startswith("Tfrx"):
                    raise FP3RenderError(f"unknown prepared-page alias {alias}")
            if class_name not in _SUPPORTED_TYPES:
                raise FP3RenderError(f"unsupported FP3 object class {class_name}")
            _validate_object_attributes(
                class_name,
                attrs,
            )
            if not _bool(attrs.get("Visible"), True):
                excluded_invisible_count += 1
                return
            if not _bool(attrs.get("Printable"), True):
                excluded_nonprintable_count += 1
                return
            left = _float(attrs, "Left", 0.0)
            top = _float(attrs, "Top", 0.0)
            width = _float(attrs, "Width", 0.0)
            height = _float(attrs, "Height", 0.0)
            absolute_x = parent_x + left
            absolute_y = parent_y + top
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

            if class_name in _BAND_TYPES:
                if class_name != "TfrxNullBand" and (
                    "Color" in attrs or "Frame.Typ" in attrs
                ):
                    order += 1
                    model.objects.append(
                        DrawObject(
                            class_name="TfrxView",
                            x=absolute_x,
                            y=absolute_y,
                            width=width,
                            height=height,
                            attrs=attrs,
                            order=order,
                        )
                    )
                for child_element in element:
                    instantiate(
                        child_element,
                        absolute_x,
                        absolute_y,
                    )
                return

            order += 1
            text = attrs.get("Text", "")
            total_text_chars += len(text)
            if total_text_chars > MAX_CLEAR_TEXT_CHARS:
                raise FP3RenderError("aggregate FP3 text exceeds policy")
            image_index = None
            if class_name in _PICTURE_TYPES | _BARCODE_TYPES:
                for key in ("ImageIndex", "PictureIndex", "BlobIndex"):
                    if key in attrs:
                        image_index = _int(attrs, key)
                        break
            model.objects.append(
                DrawObject(
                    class_name=class_name,
                    x=absolute_x,
                    y=absolute_y,
                    width=width,
                    height=height,
                    attrs=attrs,
                    order=order,
                    text=text,
                    image_index=image_index,
                )
            )
            for child_element in element:
                instantiate(
                    child_element,
                    absolute_x,
                    absolute_y,
                )

        for item in preview_page:
            instantiate(
                item,
                0.0,
                0.0,
            )
            if len(model.objects) > MAX_OBJECTS_PER_PAGE:
                raise FP3RenderError("FP3 page object count exceeds policy")
        pages.append(model)

    return FP3Model(
        pages=tuple(pages),
        class_inventory=tuple(sorted(class_counts.items())),
        source_sha256=hashlib.sha256(data).hexdigest(),
        excluded_invisible_count=excluded_invisible_count,
        excluded_nonprintable_count=excluded_nonprintable_count,
        picture_cache=_picture_cache(root),
    )


class TrueTypeFont:
    """Small bounded TrueType reader for cmap/metrics and PDF embedding."""

    def __init__(self, path: Path):
        self.path = path
        try:
            info = path.lstat()
        except OSError as error:
            raise FP3RenderError(f"font is unavailable: {path}") from error
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size <= 0
            or info.st_size > 64 * 1024 * 1024
        ):
            raise FP3RenderError("font file is outside policy")
        try:
            with path.open("rb") as handle:
                data = handle.read(64 * 1024 * 1024 + 1)
        except OSError as error:
            raise FP3RenderError(f"font is unavailable: {path}") from error
        if not data or len(data) > 64 * 1024 * 1024:
            raise FP3RenderError("font file is outside policy")
        if data[:4] in {b"ttcf", b"OTTO"}:
            raise FP3RenderError("TTC and CFF fonts are not supported")
        if data[:4] not in {b"\x00\x01\x00\x00", b"true"}:
            raise FP3RenderError("font is not TrueType")
        self.data = data
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.tables = self._tables()
        self.units_per_em = self._u16(self._table("head"), 18)
        if not 16 <= self.units_per_em <= 16384:
            raise FP3RenderError("font units-per-em is invalid")
        self.bbox = tuple(
            self._i16(self._table("head"), offset)
            for offset in (36, 38, 40, 42)
        )
        hhea = self._table("hhea")
        self.ascent = self._i16(hhea, 4)
        self.descent = self._i16(hhea, 6)
        self.number_of_hmetrics = self._u16(hhea, 34)
        self.num_glyphs = self._u16(self._table("maxp"), 4)
        if not 1 <= self.number_of_hmetrics <= self.num_glyphs <= 65535:
            raise FP3RenderError("font glyph metrics are invalid")
        os2 = self.tables.get("OS/2")
        if os2 is not None:
            os2_data = self.data[os2[0] : os2[0] + os2[1]]
            fs_type = self._u16(os2_data, 8)
            if fs_type & 0x0002:
                raise FP3RenderError("font embedding is restricted")
            self.cap_height = (
                self._i16(os2_data, 88) if len(os2_data) >= 90 else self.ascent
            )
        else:
            self.cap_height = self.ascent
        self._advance = self._advance_widths()
        self._cmap = self._select_cmap()
        self.postscript_name = self._postscript_name()

    @staticmethod
    def _u16(data: bytes, offset: int) -> int:
        if offset < 0 or offset + 2 > len(data):
            raise FP3RenderError("font table is truncated")
        return struct.unpack_from(">H", data, offset)[0]

    @staticmethod
    def _i16(data: bytes, offset: int) -> int:
        if offset < 0 or offset + 2 > len(data):
            raise FP3RenderError("font table is truncated")
        return struct.unpack_from(">h", data, offset)[0]

    @staticmethod
    def _u32(data: bytes, offset: int) -> int:
        if offset < 0 or offset + 4 > len(data):
            raise FP3RenderError("font table is truncated")
        return struct.unpack_from(">I", data, offset)[0]

    def _tables(self) -> dict[str, tuple[int, int]]:
        count = self._u16(self.data, 4)
        if not 1 <= count <= 256 or 12 + count * 16 > len(self.data):
            raise FP3RenderError("font table directory is invalid")
        result: dict[str, tuple[int, int]] = {}
        for index in range(count):
            start = 12 + index * 16
            tag = self.data[start : start + 4].decode("latin-1")
            offset = self._u32(self.data, start + 8)
            length = self._u32(self.data, start + 12)
            if offset + length > len(self.data):
                raise FP3RenderError("font table exceeds file")
            result[tag] = (offset, length)
        return result

    def _table(self, name: str) -> bytes:
        try:
            offset, length = self.tables[name]
        except KeyError as error:
            raise FP3RenderError(f"font lacks {name} table") from error
        return self.data[offset : offset + length]

    def _advance_widths(self) -> tuple[int, ...]:
        hmtx = self._table("hmtx")
        required = self.number_of_hmetrics * 4
        if len(hmtx) < required:
            raise FP3RenderError("font hmtx table is truncated")
        widths = [
            self._u16(hmtx, index * 4)
            for index in range(self.number_of_hmetrics)
        ]
        widths.extend([widths[-1]] * (self.num_glyphs - len(widths)))
        return tuple(widths)

    def _select_cmap(self) -> tuple[int, bytes]:
        cmap = self._table("cmap")
        count = self._u16(cmap, 2)
        candidates: list[tuple[int, int, int]] = []
        for index in range(count):
            base = 4 + index * 8
            if base + 8 > len(cmap):
                raise FP3RenderError("font cmap directory is truncated")
            platform = self._u16(cmap, base)
            encoding = self._u16(cmap, base + 2)
            offset = self._u32(cmap, base + 4)
            if offset + 2 > len(cmap):
                continue
            fmt = self._u16(cmap, offset)
            score = -1
            if fmt == 12 and (platform == 0 or (platform == 3 and encoding == 10)):
                score = 100
            elif fmt == 4 and (platform == 0 or (platform == 3 and encoding in {1, 10})):
                score = 80
            if score >= 0:
                candidates.append((score, fmt, offset))
        if not candidates:
            raise FP3RenderError("font lacks a Unicode cmap")
        _, fmt, offset = max(candidates)
        return fmt, cmap[offset:]

    def _postscript_name(self) -> str:
        name_table = self.tables.get("name")
        if name_table is None:
            return _sanitize_pdf_name(self.path.stem, "FP3Font")
        data = self.data[name_table[0] : name_table[0] + name_table[1]]
        if len(data) < 6:
            return _sanitize_pdf_name(self.path.stem, "FP3Font")
        count = self._u16(data, 2)
        storage = self._u16(data, 4)
        candidates: list[tuple[int, str]] = []
        for index in range(count):
            base = 6 + index * 12
            if base + 12 > len(data):
                break
            platform = self._u16(data, base)
            name_id = self._u16(data, base + 6)
            length = self._u16(data, base + 8)
            offset = self._u16(data, base + 10)
            if name_id != 6 or storage + offset + length > len(data):
                continue
            raw = data[storage + offset : storage + offset + length]
            try:
                value = (
                    raw.decode("utf-16-be")
                    if platform in {0, 3}
                    else raw.decode("latin-1")
                )
            except UnicodeDecodeError:
                continue
            candidates.append((1 if platform == 3 else 0, value))
        if not candidates:
            return _sanitize_pdf_name(self.path.stem, "FP3Font")
        return _sanitize_pdf_name(max(candidates)[1], "FP3Font")

    def glyph(self, codepoint: int) -> int:
        fmt, cmap = self._cmap
        if fmt == 12:
            if len(cmap) < 16:
                return 0
            groups = self._u32(cmap, 12)
            if groups > 1_000_000 or 16 + groups * 12 > len(cmap):
                raise FP3RenderError("font cmap format 12 is invalid")
            low = 0
            high = groups
            while low < high:
                middle = (low + high) // 2
                base = 16 + middle * 12
                start = self._u32(cmap, base)
                end = self._u32(cmap, base + 4)
                if codepoint < start:
                    high = middle
                elif codepoint > end:
                    low = middle + 1
                else:
                    gid = self._u32(cmap, base + 8) + codepoint - start
                    return gid if gid < self.num_glyphs else 0
            return 0
        if codepoint > 0xFFFF or len(cmap) < 16:
            return 0
        seg_count = self._u16(cmap, 6) // 2
        if not 1 <= seg_count <= 8192:
            raise FP3RenderError("font cmap format 4 is invalid")
        end_base = 14
        start_base = end_base + 2 * seg_count + 2
        delta_base = start_base + 2 * seg_count
        range_base = delta_base + 2 * seg_count
        if range_base + 2 * seg_count > len(cmap):
            raise FP3RenderError("font cmap format 4 is truncated")
        for index in range(seg_count):
            end = self._u16(cmap, end_base + 2 * index)
            if codepoint > end:
                continue
            start = self._u16(cmap, start_base + 2 * index)
            if codepoint < start:
                return 0
            delta = self._i16(cmap, delta_base + 2 * index)
            range_offset = self._u16(cmap, range_base + 2 * index)
            if range_offset == 0:
                return (codepoint + delta) & 0xFFFF
            address = (
                range_base
                + 2 * index
                + range_offset
                + 2 * (codepoint - start)
            )
            if address + 2 > len(cmap):
                return 0
            gid = self._u16(cmap, address)
            return ((gid + delta) & 0xFFFF) if gid else 0
        return 0

    def supports(self, text: str) -> bool:
        return all(
            char in "\r\n\t" or self.glyph(ord(char)) != 0
            for char in text
        )

    def width_1000(self, codepoint: int) -> int:
        gid = self.glyph(codepoint)
        if gid >= len(self._advance):
            gid = 0
        return max(0, round(self._advance[gid] * 1000 / self.units_per_em))

    def width_pt(self, text: str, size_pt: float) -> float:
        return (
            sum(self.width_1000(ord(char)) for char in text)
            * size_pt
            / 1000.0
        )


@dataclass
class FontUse:
    resource: str
    requested_name: str
    face: TrueTypeFont | None
    codepoints: set[int] = field(default_factory=set)

    @property
    def embedded(self) -> bool:
        return self.face is not None

    def width_pt(self, text: str, size_pt: float) -> float:
        if self.face is not None:
            return self.face.width_pt(text, size_pt)
        return sum(0.278 if char == " " else 0.556 for char in text) * size_pt

    def encode(self, text: str) -> bytes:
        if self.face is None:
            try:
                return _pdf_literal_bytes(text.encode("cp1252"))
            except UnicodeEncodeError as error:
                raise FP3RenderError("non-Latin text requires an embedded font") from error
        result = bytearray()
        for char in text:
            codepoint = ord(char)
            if codepoint > 0xFFFF or self.face.glyph(codepoint) == 0:
                raise FP3RenderError(
                    f"font cannot encode U+{codepoint:04X}"
                )
            self.codepoints.add(codepoint)
            result.extend(codepoint.to_bytes(2, "big"))
        return b"<" + bytes(result).hex().upper().encode("ascii") + b">"


class FontRegistry:
    def __init__(self, explicit_font: Path | None = None):
        self.explicit_font = explicit_font
        self._faces: dict[Path, TrueTypeFont] = {}
        self._uses: list[FontUse] = []
        self._uses_by_key: dict[tuple[str, bool], list[FontUse]] = {}

    def _load(self, path: Path) -> TrueTypeFont:
        resolved = path.expanduser().resolve()
        face = self._faces.get(resolved)
        if face is None:
            face = TrueTypeFont(resolved)
            self._faces[resolved] = face
        return face

    def _paths_for(self, name: str, bold: bool) -> Iterator[Path]:
        if self.explicit_font is not None:
            yield self.explicit_font
            return
        lowered = name.strip().lower()
        if lowered in _KOREAN_SERIF_NAMES:
            key = "korean-serif"
        elif lowered in _KOREAN_SANS_NAMES:
            key = "korean-sans"
        else:
            key = f"{lowered} bold" if bold else lowered
        for value in _FONT_CANDIDATES.get(key, ()):
            yield Path(value)
        if key != lowered:
            for value in _FONT_CANDIDATES.get(lowered, ()):
                yield Path(value)
        for value in _FONT_CANDIDATES["korean-fallback"]:
            yield Path(value)

    def select(self, name: str, text: str, bold: bool) -> FontUse:
        ascii_only = all(ord(char) < 128 for char in text)
        key = (name.strip().lower() or "arial", bold)
        for existing in self._uses_by_key.get(key, ()):
            if existing.face is None:
                if ascii_only:
                    return existing
            elif existing.face.supports(text):
                return existing
        for path in self._paths_for(name, bold):
            if not path.is_file() or path.suffix.lower() != ".ttf":
                continue
            try:
                face = self._load(path)
            except FP3RenderError:
                continue
            if face.supports(text):
                for existing in self._uses:
                    if (
                        existing.face is not None
                        and existing.face.path == face.path
                        and existing.face.supports(text)
                    ):
                        self._uses_by_key.setdefault(key, []).append(existing)
                        return existing
                use = FontUse(
                    resource=f"F{len(self._uses) + 1}",
                    requested_name=name,
                    face=face,
                )
                self._uses.append(use)
                self._uses_by_key.setdefault(key, []).append(use)
                return use
        if ascii_only:
            use = FontUse(
                resource=f"F{len(self._uses) + 1}",
                requested_name=name,
                face=None,
            )
            self._uses.append(use)
            self._uses_by_key.setdefault(key, []).append(use)
            return use
        raise FP3RenderError(f"no embeddable font covers text for {name!r}")

    @property
    def uses(self) -> tuple[FontUse, ...]:
        return tuple(self._uses)


@dataclass(frozen=True)
class PDFImage:
    width: int
    height: int
    colorspace: bytes
    bits: int
    data: bytes = field(repr=False)
    filter_name: bytes
    decode_parms: bytes | None = None
    alpha: bytes | None = field(default=None, repr=False)
    color_key_mask: bytes | None = None
    interpolate: bool = False


def _jpeg_size(data: bytes) -> tuple[int, int, int]:
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise FP3RenderError("invalid JPEG signature")
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise FP3RenderError("truncated JPEG segment")
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if length < 8:
                raise FP3RenderError("invalid JPEG frame")
            precision = data[offset + 2]
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            components = data[offset + 7]
            if (
                precision != 8
                or width == 0
                or height == 0
                or components not in {1, 3}
            ):
                raise FP3RenderError("unsupported JPEG frame")
            return width, height, components
        offset += length
    raise FP3RenderError("JPEG lacks a frame header")


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise FP3RenderError("invalid PNG signature")
    offset = 8
    result: list[tuple[bytes, bytes]] = []
    saw_end = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if length > MAX_SIDECAR_BYTES or end > len(data):
            raise FP3RenderError("PNG chunk exceeds input")
        payload = data[offset + 8 : offset + 8 + length]
        expected = int.from_bytes(data[offset + 8 + length : end], "big")
        actual = binascii.crc32(kind + payload) & 0xFFFFFFFF
        if actual != expected:
            raise FP3RenderError("PNG CRC mismatch")
        result.append((kind, payload))
        offset = end
        if kind == b"IEND":
            saw_end = True
            break
    if not saw_end or offset != len(data):
        raise FP3RenderError("PNG is truncated or has trailing data")
    return result


def _bounded_zlib_decompress(compressed: bytes, expected: int) -> bytes:
    if expected < 0 or expected > MAX_IMAGE_PIXELS * 5:
        raise FP3RenderError("image inflate size exceeds policy")
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(compressed, expected + 1)
        if len(raw) <= expected:
            raw += inflater.flush(expected + 1 - len(raw))
    except zlib.error as error:
        raise FP3RenderError("PNG IDAT is invalid") from error
    if (
        len(raw) != expected
        or not inflater.eof
        or inflater.unconsumed_tail
        or inflater.unused_data
    ):
        raise FP3RenderError("PNG scanline size mismatch")
    return raw


def _png_unfilter(
    compressed: bytes,
    width: int,
    height: int,
    channels: int,
) -> bytes:
    row_bytes = width * channels
    expected = height * (row_bytes + 1)
    raw = _bounded_zlib_decompress(compressed, expected)
    output = bytearray(height * row_bytes)
    prior = bytearray(row_bytes)
    for row in range(height):
        source = raw[row * (row_bytes + 1) : (row + 1) * (row_bytes + 1)]
        filter_type = source[0]
        current = bytearray(source[1:])
        for index in range(row_bytes):
            left = current[index - channels] if index >= channels else 0
            up = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 1:
                current[index] = (current[index] + left) & 0xFF
            elif filter_type == 2:
                current[index] = (current[index] + up) & 0xFF
            elif filter_type == 3:
                current[index] = (current[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = left + up - upper_left
                pa = abs(predictor - left)
                pb = abs(predictor - up)
                pc = abs(predictor - upper_left)
                choice = left if pa <= pb and pa <= pc else (up if pb <= pc else upper_left)
                current[index] = (current[index] + choice) & 0xFF
            elif filter_type != 0:
                raise FP3RenderError("unsupported PNG filter")
        start = row * row_bytes
        output[start : start + row_bytes] = current
        prior = current
    return bytes(output)


def _png_image(
    data: bytes,
    transparent_color: tuple[int, int, int] | None = None,
) -> PDFImage:
    chunks = _png_chunks(data)
    ihdr_values = [payload for kind, payload in chunks if kind == b"IHDR"]
    if len(ihdr_values) != 1 or len(ihdr_values[0]) != 13:
        raise FP3RenderError("PNG must have one IHDR")
    width, height, bits, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr_values[0]
    )
    if (
        width == 0
        or height == 0
        or width * height > MAX_IMAGE_PIXELS
        or bits != 8
        or compression != 0
        or filtering != 0
        or interlace != 0
    ):
        raise FP3RenderError("PNG geometry or encoding is unsupported")
    idat = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not idat:
        raise FP3RenderError("PNG lacks IDAT")
    if any(kind == b"tRNS" for kind, _ in chunks):
        raise FP3RenderError("PNG tRNS transparency is unsupported")
    if color_type in {0, 2}:
        channels = 1 if color_type == 0 else 3
        colorspace = b"/DeviceGray" if channels == 1 else b"/DeviceRGB"
        # Validate the compressed scanlines before embedding their original
        # predictor stream into the PDF.
        decoded = _png_unfilter(idat, width, height, channels)
        alpha = None
        if transparent_color is not None:
            mask = bytearray(width * height)
            for pixel in range(width * height):
                start = pixel * channels
                if channels == 1:
                    value = decoded[start]
                    rgb = (value, value, value)
                else:
                    rgb = tuple(decoded[start : start + 3])
                mask[pixel] = 0 if rgb == transparent_color else 255
            alpha = zlib.compress(bytes(mask), 9)
        return PDFImage(
            width,
            height,
            colorspace,
            8,
            idat,
            b"/FlateDecode",
            (
                b"<< /Predictor 15 /Colors "
                + str(channels).encode("ascii")
                + b" /BitsPerComponent 8 /Columns "
                + str(width).encode("ascii")
                + b" >>"
            ),
            alpha=alpha,
        )
    if color_type not in {4, 6}:
        raise FP3RenderError("palette PNG is unsupported")
    channels = 2 if color_type == 4 else 4
    decoded = _png_unfilter(idat, width, height, channels)
    color_channels = 1 if color_type == 4 else 3
    color = bytearray(width * height * color_channels)
    alpha = bytearray(width * height)
    for pixel in range(width * height):
        source = pixel * channels
        target = pixel * color_channels
        color[target : target + color_channels] = decoded[
            source : source + color_channels
        ]
        alpha[pixel] = decoded[source + color_channels]
        if transparent_color is not None:
            if color_channels == 1:
                value = color[target]
                rgb = (value, value, value)
            else:
                rgb = tuple(color[target : target + 3])
            if rgb == transparent_color:
                alpha[pixel] = 0
    return PDFImage(
        width,
        height,
        b"/DeviceGray" if color_channels == 1 else b"/DeviceRGB",
        8,
        zlib.compress(bytes(color), 9),
        b"/FlateDecode",
        alpha=zlib.compress(bytes(alpha), 9),
    )


def _bmp_image(
    data: bytes,
    transparent_color: tuple[int, int, int] | None = None,
) -> PDFImage:
    if not data.startswith(b"BM") or len(data) < 54:
        raise FP3RenderError("invalid BMP signature")
    pixel_offset = int.from_bytes(data[10:14], "little")
    dib_size = int.from_bytes(data[14:18], "little")
    if dib_size < 40 or 14 + dib_size > len(data):
        raise FP3RenderError("unsupported BMP DIB header")
    width = int.from_bytes(data[18:22], "little", signed=True)
    signed_height = int.from_bytes(data[22:26], "little", signed=True)
    planes = int.from_bytes(data[26:28], "little")
    bits = int.from_bytes(data[28:30], "little")
    compression = int.from_bytes(data[30:34], "little")
    if (
        width <= 0
        or signed_height == 0
        or width * abs(signed_height) > MAX_IMAGE_PIXELS
        or planes != 1
        or bits not in {8, 24, 32}
        or compression != 0
    ):
        raise FP3RenderError("BMP geometry or encoding is unsupported")
    height = abs(signed_height)
    source_stride = ((width * bits + 31) // 32) * 4
    required = pixel_offset + source_stride * height
    if pixel_offset < 14 + dib_size or required > len(data):
        raise FP3RenderError("BMP pixel data is truncated")
    bottom_up = signed_height > 0
    if bits == 8:
        colors_used = int.from_bytes(data[46:50], "little")
        palette_count = colors_used or 256
        if not 1 <= palette_count <= 256:
            raise FP3RenderError("BMP palette size is outside policy")
        palette_start = 14 + dib_size
        palette_end = palette_start + palette_count * 4
        if palette_end > pixel_offset or palette_end > len(data):
            raise FP3RenderError("BMP palette is truncated")
        palette = bytearray(palette_count * 3)
        for index in range(palette_count):
            blue, green, red, _reserved = data[
                palette_start + index * 4 :
                palette_start + index * 4 + 4
            ]
            palette[index * 3 : index * 3 + 3] = bytes(
                (red, green, blue)
            )
        indices = bytearray(width * height)
        alpha = (
            bytearray(width * height)
            if transparent_color is not None
            else None
        )
        for output_y in range(height):
            source_y = height - 1 - output_y if bottom_up else output_y
            row = data[
                pixel_offset + source_y * source_stride :
                pixel_offset + source_y * source_stride + width
            ]
            if any(value >= palette_count for value in row):
                raise FP3RenderError(
                    "BMP pixel references a missing palette entry"
                )
            start = output_y * width
            indices[start : start + width] = row
            if alpha is not None:
                for x, value in enumerate(row):
                    palette_offset = value * 3
                    rgb = tuple(
                        palette[palette_offset : palette_offset + 3]
                    )
                    alpha[start + x] = (
                        0 if rgb == transparent_color else 255
                    )
        colorspace = (
            b"[/Indexed /DeviceRGB "
            + str(palette_count - 1).encode("ascii")
            + b" <"
            + bytes(palette).hex().upper().encode("ascii")
            + b">]"
        )
        return PDFImage(
            width,
            height,
            colorspace,
            8,
            zlib.compress(bytes(indices), 9),
            b"/FlateDecode",
            alpha=(
                zlib.compress(bytes(alpha), 9)
                if alpha is not None
                else None
            ),
        )
    rgb = bytearray(width * height * 3)
    alpha = (
        bytearray(width * height)
        if transparent_color is not None
        else None
    )
    # BI_RGB's fourth byte is reserved, not a trustworthy alpha channel.
    # Supporting alpha requires a bitfield header whose masks we validate.
    for output_y in range(height):
        source_y = height - 1 - output_y if bottom_up else output_y
        row = pixel_offset + source_y * source_stride
        for x in range(width):
            source = row + x * (bits // 8)
            target = (output_y * width + x) * 3
            blue, green, red = data[source : source + 3]
            rgb[target : target + 3] = bytes((red, green, blue))
            if alpha is not None:
                alpha[output_y * width + x] = (
                    0
                    if (red, green, blue) == transparent_color
                    else 255
                )
    return PDFImage(
        width,
        height,
        b"/DeviceRGB",
        8,
        zlib.compress(bytes(rgb), 9),
        b"/FlateDecode",
        alpha=(
            zlib.compress(bytes(alpha), 9)
            if alpha is not None
            else None
        ),
    )


def decode_image(
    data: bytes,
    *,
    transparent_color: tuple[int, int, int] | None = None,
    interpolate: bool = False,
) -> PDFImage:
    if not isinstance(data, bytes):
        raise TypeError("image sidecar must be immutable bytes")
    if not data or len(data) > MAX_SIDECAR_BYTES:
        raise FP3RenderError("image sidecar size is outside policy")
    if data.startswith(b"\xff\xd8"):
        width, height, components = _jpeg_size(data)
        if width * height > MAX_IMAGE_PIXELS:
            raise FP3RenderError("JPEG dimensions exceed policy")
        colorspace = (
            b"/DeviceGray"
            if components == 1
            else (b"/DeviceCMYK" if components == 4 else b"/DeviceRGB")
        )
        return PDFImage(
            width,
            height,
            colorspace,
            8,
            data,
            b"/DCTDecode",
            color_key_mask=(
                b"["
                + b" ".join(
                    str(value).encode("ascii")
                    for channel in transparent_color
                    for value in (channel, channel)
                )
                + b"]"
                if transparent_color is not None
                else None
            ),
            interpolate=interpolate,
        )
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        image = _png_image(data, transparent_color)
        return replace(image, interpolate=interpolate)
    if data.startswith(b"BM"):
        image = _bmp_image(data, transparent_color)
        return replace(image, interpolate=interpolate)
    raise FP3RenderError("unsupported image sidecar encoding")


def _embedded_picture(attrs: Mapping[str, str]) -> bytes | None:
    for key in ("Picture.Data", "Picture", "Data", "Image.Data"):
        raw = attrs.get(key)
        if not raw:
            continue
        compact = "".join(raw.split())
        try:
            if re.fullmatch(r"[0-9A-Fa-f]+", compact) and len(compact) % 2 == 0:
                return bytes.fromhex(compact)
            return base64.b64decode(compact, validate=True)
        except (ValueError, binascii.Error) as error:
            raise FP3RenderError(f"{key} is not encoded image data") from error
    return None


class PDFBuilder:
    def __init__(self):
        self.objects: list[bytes] = []

    def add(self, body: bytes) -> int:
        if not isinstance(body, bytes):
            raise TypeError("PDF object must be bytes")
        self.objects.append(body)
        return len(self.objects)

    def stream(
        self,
        dictionary: bytes,
        data: bytes,
        *,
        compress: bool = False,
    ) -> int:
        payload = zlib.compress(data, 9) if compress else data
        filter_part = b" /Filter /FlateDecode" if compress else b""
        body = (
            b"<< "
            + dictionary.strip()
            + b" /Length "
            + str(len(payload)).encode("ascii")
            + filter_part
            + b" >>\nstream\n"
            + payload
            + b"\nendstream"
        )
        return self.add(body)

    def finish(self, root: int) -> bytes:
        header = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
        chunks = [header]
        offsets = [0]
        position = len(header)
        for number, body in enumerate(self.objects, 1):
            object_bytes = (
                f"{number} 0 obj\n".encode("ascii")
                + body
                + b"\nendobj\n"
            )
            offsets.append(position)
            chunks.append(object_bytes)
            position += len(object_bytes)
        xref_offset = position
        xref = [
            f"xref\n0 {len(self.objects) + 1}\n".encode("ascii"),
            b"0000000000 65535 f \n",
        ]
        xref.extend(
            f"{offset:010d} 00000 n \n".encode("ascii")
            for offset in offsets[1:]
        )
        trailer = (
            b"trailer\n<< /Size "
            + str(len(self.objects) + 1).encode("ascii")
            + b" /Root "
            + f"{root} 0 R".encode("ascii")
            + b" >>\nstartxref\n"
            + str(xref_offset).encode("ascii")
            + b"\n%%EOF\n"
        )
        result = b"".join(chunks + xref + [trailer])
        if len(result) > MAX_PDF_BYTES:
            raise FP3RenderError("rendered PDF exceeds policy")
        return result


def _font_pdf_objects(
    builder: PDFBuilder,
    use: FontUse,
) -> int:
    if use.face is None:
        return builder.add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        )
    face = use.face
    codepoints = sorted(use.codepoints or {0x20})
    max_cid = max(codepoints)
    gid_map = bytearray((max_cid + 1) * 2)
    widths: list[bytes] = []
    for codepoint in codepoints:
        gid = face.glyph(codepoint)
        if gid == 0 and codepoint != 0x20:
            raise FP3RenderError(f"font lacks U+{codepoint:04X}")
        gid_map[codepoint * 2 : codepoint * 2 + 2] = gid.to_bytes(2, "big")
        widths.append(
            str(codepoint).encode("ascii")
            + b" ["
            + str(face.width_1000(codepoint)).encode("ascii")
            + b"]"
        )
    cid_map_obj = builder.stream(b"", bytes(gid_map), compress=True)
    font_file_obj = builder.stream(
        b"/Length1 " + str(len(face.data)).encode("ascii"),
        face.data,
        compress=True,
    )
    scale = 1000.0 / face.units_per_em
    bbox = b" ".join(
        _pdf_number(value * scale).encode("ascii")
        for value in face.bbox
    )
    font_name = _sanitize_pdf_name(face.postscript_name, "FP3Font")
    descriptor = builder.add(
        b"<< /Type /FontDescriptor /FontName /"
        + font_name.encode("ascii")
        + b" /Flags 32 /FontBBox ["
        + bbox
        + b"] /ItalicAngle 0 /Ascent "
        + _pdf_number(face.ascent * scale).encode("ascii")
        + b" /Descent "
        + _pdf_number(face.descent * scale).encode("ascii")
        + b" /CapHeight "
        + _pdf_number(face.cap_height * scale).encode("ascii")
        + b" /StemV 80 /FontFile2 "
        + f"{font_file_obj} 0 R".encode("ascii")
        + b" >>"
    )
    cid_font = builder.add(
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /"
        + font_name.encode("ascii")
        + b" /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
        b"/Supplement 0 >> /FontDescriptor "
        + f"{descriptor} 0 R".encode("ascii")
        + b" /DW 1000 /W ["
        + b" ".join(widths)
        + b"] /CIDToGIDMap "
        + f"{cid_map_obj} 0 R".encode("ascii")
        + b" >>"
    )
    cmap_parts = [
        b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n",
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n",
        b"/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n",
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n",
    ]
    for start in range(0, len(codepoints), 100):
        chunk = codepoints[start : start + 100]
        cmap_parts.append(f"{len(chunk)} beginbfchar\n".encode("ascii"))
        for codepoint in chunk:
            unicode_hex = chr(codepoint).encode("utf-16-be").hex().upper()
            cmap_parts.append(
                f"<{codepoint:04X}> <{unicode_hex}>\n".encode("ascii")
            )
        cmap_parts.append(b"endbfchar\n")
    cmap_parts.append(
        b"endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    )
    to_unicode = builder.stream(b"", b"".join(cmap_parts), compress=True)
    return builder.add(
        b"<< /Type /Font /Subtype /Type0 /BaseFont /"
        + font_name.encode("ascii")
        + b" /Encoding /Identity-H /DescendantFonts ["
        + f"{cid_font} 0 R".encode("ascii")
        + b"] /ToUnicode "
        + f"{to_unicode} 0 R".encode("ascii")
        + b" >>"
    )


def _frame_style(attrs: Mapping[str, str]) -> tuple[float, bytes]:
    width = max(0.1, _float(attrs, "Frame.Width", 1.0) * PX_TO_PT)
    style = attrs.get("Frame.Style", "fsSolid")
    if style in {"", "0", "fsSolid"}:
        dash = b"[] 0 d"
    elif style in {"1", "fsDash"}:
        dash = b"[6 3] 0 d"
    elif style in {"2", "fsDot"}:
        dash = b"[1 2] 0 d"
    elif style in {"3", "fsDashDot"}:
        dash = b"[6 2 1 2] 0 d"
    elif style in {"4", "fsDashDotDot"}:
        dash = b"[6 2 1 2 1 2] 0 d"
    elif style == "fsDouble":
        dash = b"[] 0 d"
        width = max(width, 0.75)
    elif style in {"5", "fsClear"}:
        return 0.0, b"[] 0 d"
    else:
        raise FP3RenderError(f"unsupported frame style {style}")
    return width, dash


def _wrap_text(
    text: str,
    width_pt: float,
    font: FontUse,
    size_pt: float,
    word_wrap: bool,
    char_spacing_pt: float = 0.0,
) -> list[str]:
    def measured(value: str) -> float:
        return max(
            0.0,
            font.width_pt(value, size_pt)
            + max(0, len(value) - 1) * char_spacing_pt,
        )

    logical = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not word_wrap or width_pt <= 0:
        return logical
    lines: list[str] = []
    for paragraph in logical:
        if not paragraph:
            lines.append("")
            continue
        remaining = paragraph
        while remaining:
            if measured(remaining) <= width_pt:
                lines.append(remaining)
                break
            low = 1
            high = len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                if measured(remaining[:middle]) <= width_pt:
                    low = middle
                else:
                    high = middle - 1
            cut = max(1, low)
            whitespace = max(
                remaining.rfind(" ", 0, cut + 1),
                remaining.rfind("\t", 0, cut + 1),
            )
            if whitespace > 0:
                cut = whitespace
            line = remaining[:cut].rstrip()
            lines.append(line)
            remaining = remaining[cut:].lstrip()
    return lines


def _object_box(
    page: PageModel,
    item: DrawObject,
) -> tuple[float, float, float, float]:
    x = page.margin_left_pt + item.x * PX_TO_PT
    top = page.height_pt - page.margin_top_pt - item.y * PX_TO_PT
    width = item.width * PX_TO_PT
    height = item.height * PX_TO_PT
    bottom = top - height
    return x, bottom, width, height


def _collect_fonts(
    model: FP3Model,
    registry: FontRegistry,
) -> dict[int, FontUse]:
    result: dict[int, FontUse] = {}
    for page in model.pages:
        for item in page.objects:
            if item.class_name not in _MEMO_TYPES:
                continue
            if not item.text:
                continue
            styles = _int(item.attrs, "Font.Style", 0)
            use = registry.select(
                item.attrs.get("Font.Name", "Arial"),
                item.text,
                bool(styles & 1),
            )
            for char in item.text:
                if use.face is not None and char not in "\r\n\t":
                    use.codepoints.add(ord(char))
            result[id(item)] = use
    return result


def _render_page_content(
    page: PageModel,
    fonts_by_item: Mapping[int, FontUse],
    images_by_item: Mapping[int, tuple[str, PDFImage]],
    suppressed_picture_items: frozenset[int],
) -> bytes:
    commands: list[bytes] = []

    def draw_fill_and_frame(
        item: DrawObject,
        *,
        fill: bool = True,
        frame: bool = True,
    ) -> None:
        x, y, width, height = _object_box(page, item)
        attrs = item.attrs
        transparent = _bool(attrs.get("Transparent"), "Color" not in attrs)
        if fill and not transparent and width > 0 and height > 0:
            red, green, blue = _delphi_color(
                attrs.get("Color"),
                default=(1.0, 1.0, 1.0),
            )
            commands.append(
                b"q "
                + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} rg ".encode(
                    "ascii"
                )
                + f"{_pdf_number(x)} {_pdf_number(y)} {_pdf_number(width)} {_pdf_number(height)} re f Q\n".encode(
                    "ascii"
                )
            )
        typ = _int(attrs, "Frame.Typ", 0)
        if frame and typ and width >= 0 and height >= 0:
            line_width, dash = _frame_style(attrs)
            if line_width <= 0:
                return
            red, green, blue = _delphi_color(
                attrs.get("Frame.Color"),
                default=(0.0, 0.0, 0.0),
            )
            prefix = (
                b"q "
                + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} RG {_pdf_number(line_width)} w ".encode(
                    "ascii"
                )
                + dash
                + b" "
            )
            segments: list[str] = []
            if typ & 1:
                segments.append(
                    f"{_pdf_number(x)} {_pdf_number(y)} m "
                    f"{_pdf_number(x)} {_pdf_number(y + height)} l S"
                )
            if typ & 2:
                segments.append(
                    f"{_pdf_number(x + width)} {_pdf_number(y)} m "
                    f"{_pdf_number(x + width)} {_pdf_number(y + height)} l S"
                )
            if typ & 4:
                segments.append(
                    f"{_pdf_number(x)} {_pdf_number(y + height)} m "
                    f"{_pdf_number(x + width)} {_pdf_number(y + height)} l S"
                )
            if typ & 8:
                segments.append(
                    f"{_pdf_number(x)} {_pdf_number(y)} m "
                    f"{_pdf_number(x + width)} {_pdf_number(y)} l S"
                )
            if segments:
                commands.append(
                    prefix + " ".join(segments).encode("ascii") + b" Q\n"
                )

    for item in sorted(page.objects, key=lambda value: value.order):
        attrs = item.attrs
        x, y, width, height = _object_box(page, item)
        if item.class_name in _GENERIC_VIEW_TYPES:
            draw_fill_and_frame(item)
            continue
        if item.class_name in _MEMO_TYPES:
            draw_fill_and_frame(item)
            if not item.text or width <= 0 or height < 0:
                continue
            use = fonts_by_item[id(item)]
            style = _int(attrs, "Font.Style", 0)
            size_pt = abs(_float(attrs, "Font.Height", -13.0)) * PX_TO_PT
            if "Font.Size" in attrs:
                size_pt = abs(_float(attrs, "Font.Size", size_pt))
            size_pt = max(1.0, min(size_pt, 512.0))
            gap_x = max(0.0, _float(attrs, "GapX", 2.0) * PX_TO_PT)
            gap_y = max(0.0, _float(attrs, "GapY", 1.0) * PX_TO_PT)
            available_width = max(0.0, width - 2 * gap_x)
            char_spacing = (
                _float(attrs, "CharSpacing", 0.0) * PX_TO_PT
            )
            if abs(char_spacing) > 100:
                raise FP3RenderError("CharSpacing is outside policy")
            if _bool(attrs.get("AutoWidth"), False):
                natural_width = max(
                    0.0,
                    use.width_pt(item.text, size_pt)
                    + max(0, len(item.text) - 1) * char_spacing,
                )
                if (
                    "\n" in item.text
                    or "\r" in item.text
                    or _bool(attrs.get("WordWrap"), True)
                    or attrs.get("HAlign", "haLeft") not in {"", "haLeft"}
                    or _int(attrs, "Frame.Typ", 0)
                    or not _bool(
                        attrs.get("Transparent"),
                        "Color" not in attrs,
                    )
                    or natural_width > available_width + 0.75
                ):
                    raise FP3RenderError(
                        "AutoWidth memo is not a validated prepared-page no-op"
                    )
            lines = _wrap_text(
                item.text,
                available_width,
                use,
                size_pt,
                _bool(attrs.get("WordWrap"), True),
                char_spacing,
            )
            line_spacing = _float(attrs, "LineSpacing", 0.0) * PX_TO_PT
            if abs(line_spacing) > 100:
                raise FP3RenderError("LineSpacing is outside policy")
            line_height = max(0.1, size_pt * 1.15 + line_spacing)
            total_height = len(lines) * line_height
            valign = attrs.get("VAlign", "vaTop")
            if valign == "vaCenter":
                first_baseline = y + (height + total_height) / 2 - line_height
            elif valign == "vaBottom":
                first_baseline = y + total_height - line_height + gap_y
            else:
                first_baseline = y + height - line_height - gap_y
            red, green, blue = _delphi_color(
                attrs.get("Font.Color"),
                default=(0.0, 0.0, 0.0),
            )
            rotation = _float(attrs, "Rotation", 0.0)
            radians = math.radians(rotation)
            cosine = math.cos(radians)
            sine = math.sin(radians)
            shear = 0.22 if style & 2 else 0.0
            clip = _bool(attrs.get("Clipped"), True)
            commands.append(b"q\n")
            if clip and width > 0 and height > 0:
                commands.append(
                    f"{_pdf_number(x)} {_pdf_number(y)} {_pdf_number(width)} {_pdf_number(height)} re W n\n".encode(
                        "ascii"
                    )
                )
            for line_no, line in enumerate(lines):
                line_width = max(
                    0.0,
                    use.width_pt(line, size_pt)
                    + max(0, len(line) - 1) * char_spacing,
                )
                halign = attrs.get("HAlign", "haLeft")
                if halign == "haRight":
                    line_x = x + width - gap_x - line_width
                elif halign == "haCenter":
                    line_x = x + (width - line_width) / 2
                else:
                    line_x = x + gap_x
                baseline = first_baseline - line_no * line_height
                encoded = use.encode(line)
                matrix_c = -sine + shear * cosine
                matrix_d = cosine + shear * sine
                commands.append(
                    b"BT /"
                    + use.resource.encode("ascii")
                    + b" "
                    + _pdf_number(size_pt).encode("ascii")
                    + b" Tf "
                    + _pdf_number(char_spacing).encode("ascii")
                    + b" Tc "
                    + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} rg ".encode(
                        "ascii"
                    )
                )
                if style & 1:
                    commands.append(
                        b"2 Tr "
                        + _pdf_number(max(0.15, size_pt / 35)).encode("ascii")
                        + b" w "
                        + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} RG ".encode(
                            "ascii"
                        )
                    )
                commands.append(
                    f"{_pdf_number(cosine)} {_pdf_number(sine)} "
                    f"{_pdf_number(matrix_c)} {_pdf_number(matrix_d)} "
                    f"{_pdf_number(line_x)} {_pdf_number(baseline)} Tm ".encode(
                        "ascii"
                    )
                    + encoded
                    + b" Tj ET\n"
                )
                if style & 4:
                    underline_y = baseline - size_pt * 0.12
                    commands.append(
                        f"{_pdf_number(line_x)} {_pdf_number(underline_y)} m "
                        f"{_pdf_number(line_x + line_width)} {_pdf_number(underline_y)} l "
                        f"{_pdf_number(max(0.4, size_pt / 18))} w S\n".encode(
                            "ascii"
                        )
                    )
                if style & 8:
                    strike_y = baseline + size_pt * 0.3
                    commands.append(
                        f"{_pdf_number(line_x)} {_pdf_number(strike_y)} m "
                        f"{_pdf_number(line_x + line_width)} {_pdf_number(strike_y)} l "
                        f"{_pdf_number(max(0.4, size_pt / 18))} w S\n".encode(
                            "ascii"
                        )
                    )
            commands.append(b"Q\n")
            continue
        if item.class_name in _LINE_TYPES:
            line_width, dash = _frame_style(attrs)
            red, green, blue = _delphi_color(
                attrs.get("Frame.Color") or attrs.get("Color"),
                default=(0.0, 0.0, 0.0),
            )
            commands.append(
                b"q "
                + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} RG {_pdf_number(line_width)} w ".encode(
                    "ascii"
                )
                + dash
                + b" "
                + f"{_pdf_number(x)} {_pdf_number(y + height)} m "
                f"{_pdf_number(x + width)} {_pdf_number(y)} l S Q\n".encode(
                    "ascii"
                )
            )
            continue
        if item.class_name in _SHAPE_TYPES:
            draw_fill_and_frame(item)
            shape = attrs.get("Shape", "skRectangle")
            red, green, blue = _delphi_color(
                attrs.get("Frame.Color"),
                default=(0.0, 0.0, 0.0),
            )
            line_width, dash = _frame_style(attrs)
            if shape in {"skRectangle", "skRoundRectangle"}:
                path = (
                    f"{_pdf_number(x)} {_pdf_number(y)} "
                    f"{_pdf_number(width)} {_pdf_number(height)} re S"
                )
            elif shape == "skEllipse":
                # Four cubic Bézier segments approximate the ellipse.
                kappa = 0.5522847498
                cx = x + width / 2
                cy = y + height / 2
                rx = width / 2
                ry = height / 2
                path = (
                    f"{_pdf_number(cx + rx)} {_pdf_number(cy)} m "
                    f"{_pdf_number(cx + rx)} {_pdf_number(cy + kappa * ry)} "
                    f"{_pdf_number(cx + kappa * rx)} {_pdf_number(cy + ry)} "
                    f"{_pdf_number(cx)} {_pdf_number(cy + ry)} c "
                    f"{_pdf_number(cx - kappa * rx)} {_pdf_number(cy + ry)} "
                    f"{_pdf_number(cx - rx)} {_pdf_number(cy + kappa * ry)} "
                    f"{_pdf_number(cx - rx)} {_pdf_number(cy)} c "
                    f"{_pdf_number(cx - rx)} {_pdf_number(cy - kappa * ry)} "
                    f"{_pdf_number(cx - kappa * rx)} {_pdf_number(cy - ry)} "
                    f"{_pdf_number(cx)} {_pdf_number(cy - ry)} c "
                    f"{_pdf_number(cx + kappa * rx)} {_pdf_number(cy - ry)} "
                    f"{_pdf_number(cx + rx)} {_pdf_number(cy - kappa * ry)} "
                    f"{_pdf_number(cx + rx)} {_pdf_number(cy)} c S"
                )
            elif shape in {"skTriangle", "skDiamond"}:
                if shape == "skTriangle":
                    points = (
                        (x + width / 2, y + height),
                        (x + width, y),
                        (x, y),
                    )
                else:
                    points = (
                        (x + width / 2, y + height),
                        (x + width, y + height / 2),
                        (x + width / 2, y),
                        (x, y + height / 2),
                    )
                path = (
                    f"{_pdf_number(points[0][0])} {_pdf_number(points[0][1])} m "
                    + " ".join(
                        f"{_pdf_number(px)} {_pdf_number(py)} l"
                        for px, py in points[1:]
                    )
                    + " h S"
                )
            else:
                raise FP3RenderError(f"unsupported shape {shape}")
            commands.append(
                b"q "
                + f"{_pdf_number(red)} {_pdf_number(green)} {_pdf_number(blue)} RG {_pdf_number(line_width)} w ".encode(
                    "ascii"
                )
                + dash
                + b" "
                + path.encode("ascii")
                + b" Q\n"
            )
            continue
        if item.class_name in _CHECKBOX_TYPES:
            draw_fill_and_frame(item)
            checked = _bool(attrs.get("Checked"), False)
            commands.append(
                f"q 0 0 0 RG 0.75 w {_pdf_number(x)} {_pdf_number(y)} "
                f"{_pdf_number(width)} {_pdf_number(height)} re S ".encode("ascii")
            )
            if checked:
                commands.append(
                    f"{_pdf_number(x)} {_pdf_number(y)} m "
                    f"{_pdf_number(x + width)} {_pdf_number(y + height)} l "
                    f"{_pdf_number(x)} {_pdf_number(y + height)} m "
                    f"{_pdf_number(x + width)} {_pdf_number(y)} l S ".encode(
                        "ascii"
                    )
                )
            commands.append(b"Q\n")
            continue
        if item.class_name in _PICTURE_TYPES | _BARCODE_TYPES:
            if id(item) in suppressed_picture_items:
                continue
            try:
                resource, image = images_by_item[id(item)]
            except KeyError as error:
                raise FP3RenderError(
                    f"{item.class_name} lacks a supported image payload"
                ) from error
            if width <= 0 or height <= 0:
                continue
            draw_fill_and_frame(item, frame=False)
            draw_width = width
            draw_height = height
            draw_x = x
            draw_y = y
            if not _bool(attrs.get("Stretched"), True):
                raise FP3RenderError(
                    "non-stretched picture rendering is unsupported"
                )
            if _bool(attrs.get("KeepAspectRatio"), True):
                scale = min(width / image.width, height / image.height)
                draw_width = image.width * scale
                draw_height = image.height * scale
                if _bool(attrs.get("Center"), False):
                    draw_x += (width - draw_width) / 2
                    draw_y += (height - draw_height) / 2
                else:
                    # FastReport picture frames use an upper-left origin.
                    # PDF uses a lower-left origin, so an uncentered contained
                    # image must retain the frame's top edge.
                    draw_y += height - draw_height
            commands.append(
                b"q "
                + f"{_pdf_number(draw_width)} 0 0 {_pdf_number(draw_height)} "
                f"{_pdf_number(draw_x)} {_pdf_number(draw_y)} cm /{resource} Do Q\n".encode(
                    "ascii"
                )
            )
            draw_fill_and_frame(item, fill=False)
            continue
        raise FP3RenderError(f"unhandled FP3 object class {item.class_name}")
    return b"".join(commands)


def render_fp3_pdf(
    data: bytes,
    sidecars: Sequence[bytes] = (),
    *,
    font_path: Path | None = None,
    runtime_pictures: Mapping[str, bytes] | None = None,
    runtime_text: Mapping[str, str] | None = None,
    official_empty_pictures: frozenset[str] = frozenset(),
) -> RenderedFP3:
    """Render one FP3 stream and return a deterministic PDF byte container.

    ``runtime_pictures`` and ``runtime_text`` materialize named placeholders
    that the Windows ReportX client mutates after loading a prepared report.
    Every supplied binding must resolve exactly one object.  Empty picture
    placeholders are accepted only when their exact names have been approved
    by a caller-side, source-specific resolver.
    """

    if len(sidecars) > MAX_SIDECARS:
        raise FP3RenderError("too many image sidecars")
    total_sidecar_bytes = 0
    for sidecar in sidecars:
        if not isinstance(sidecar, bytes) or len(sidecar) > MAX_SIDECAR_BYTES:
            raise FP3RenderError("image sidecar is outside policy")
        total_sidecar_bytes += len(sidecar)
        if total_sidecar_bytes > MAX_TOTAL_SIDECAR_BYTES:
            raise FP3RenderError("aggregate image sidecars exceed policy")
    model = parse_fp3(data)
    picture_bindings = dict(runtime_pictures or {})
    text_bindings = dict(runtime_text or {})
    if len(picture_bindings) + len(text_bindings) > MAX_SIDECARS:
        raise FP3RenderError("too many ReportX runtime bindings")
    for name, raw in picture_bindings.items():
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 256
            or not isinstance(raw, bytes)
            or not raw
            or len(raw) > MAX_SIDECAR_BYTES
        ):
            raise FP3RenderError("picture runtime binding is outside policy")
    for name, value in text_bindings.items():
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 256
            or not isinstance(value, str)
            or len(value) > MAX_CLEAR_TEXT_CHARS
        ):
            raise FP3RenderError("text runtime binding is outside policy")
    if (
        not isinstance(official_empty_pictures, frozenset)
        or any(
            not isinstance(name, str) or not name or len(name) > 256
            for name in official_empty_pictures
        )
    ):
        raise FP3RenderError("empty-picture approval is outside policy")

    picture_matches = {name: 0 for name in picture_bindings}
    text_matches = {name: 0 for name in text_bindings}
    empty_matches = {name: 0 for name in official_empty_pictures}
    for page in model.pages:
        for item in page.objects:
            name = item.attrs.get("Name", "")
            if name in text_bindings:
                if item.class_name not in _MEMO_TYPES:
                    raise FP3RenderError(
                        "text runtime binding targets a non-memo object"
                    )
                item.text = text_bindings[name]
                item.attrs["Text"] = text_bindings[name]
                text_matches[name] += 1
            if name in picture_bindings:
                if item.class_name not in _PICTURE_TYPES | _BARCODE_TYPES:
                    raise FP3RenderError(
                        "picture runtime binding targets a non-picture object"
                    )
                picture_matches[name] += 1
            if name in official_empty_pictures:
                if item.class_name not in _PICTURE_TYPES | _BARCODE_TYPES:
                    raise FP3RenderError(
                        "empty-picture approval targets a non-picture object"
                    )
                empty_matches[name] += 1
    if any(count != 1 for count in picture_matches.values()):
        raise FP3RenderError("picture runtime binding is not one-to-one")
    if any(count != 1 for count in text_matches.values()):
        raise FP3RenderError("text runtime binding is not one-to-one")
    if any(count != 1 for count in empty_matches.values()):
        raise FP3RenderError("empty-picture approval is not one-to-one")

    if (
        len(model.picture_cache)
        + len(sidecars)
        + len(picture_bindings)
        > MAX_SIDECARS
    ):
        raise FP3RenderError("too many combined image resources")
    total_image_bytes = sum(len(item) for item in model.picture_cache) + sum(
        len(item) for item in sidecars
    ) + sum(len(item) for item in picture_bindings.values())
    if total_image_bytes > MAX_TOTAL_SIDECAR_BYTES:
        raise FP3RenderError("aggregate image resources exceed policy")
    registry = FontRegistry(font_path)
    fonts_by_item = _collect_fonts(model, registry)

    image_cache: dict[
        tuple[str, tuple[int, int, int] | None, bool],
        tuple[str, PDFImage],
    ] = {}
    images_by_item: dict[int, tuple[str, PDFImage]] = {}
    suppressed_picture_items: set[int] = set()
    external_targets = [
        item
        for page in model.pages
        for item in page.objects
        if (
            item.class_name in _PICTURE_TYPES | _BARCODE_TYPES
            and item.image_index == 0
            and item.attrs.get("Name", "") not in picture_bindings
            and item.attrs.get("Name", "") not in official_empty_pictures
            and (
                not model.picture_cache
                or item.attrs.get("Name", "").upper() == "__2DBARCODE__"
            )
        )
    ]
    if len(external_targets) != len(sidecars):
        raise FP3RenderError(
            "ReportX external image count does not match __2DBARCODE__ objects"
        )
    external_by_item = {
        id(item): sidecar
        for item, sidecar in zip(external_targets, sidecars)
    }
    for page in model.pages:
        for item in page.objects:
            if item.class_name not in _PICTURE_TYPES | _BARCODE_TYPES:
                continue
            name = item.attrs.get("Name", "")
            raw = _embedded_picture(item.attrs)
            runtime_raw = picture_bindings.get(name)
            if runtime_raw is not None:
                if raw is not None:
                    raise FP3RenderError(
                        "runtime picture collides with an embedded payload"
                    )
                raw = runtime_raw
            if raw is None:
                raw = external_by_item.get(id(item))
            if raw is None and item.image_index is not None:
                index = item.image_index
                if index == 0:
                    if name in official_empty_pictures:
                        suppressed_picture_items.add(id(item))
                        continue
                    raise FP3RenderError(
                        "zero image index has no ReportX external binding"
                    )
                resolved = index - 1
                if resolved < 0 or resolved >= len(model.picture_cache):
                    raise FP3RenderError(
                        f"image index {index} has no picture cache item"
                    )
                raw = model.picture_cache[resolved]
            if raw is None:
                continue
            transparent_color = None
            if _bool(item.attrs.get("Transparent"), False):
                color = _delphi_color(
                    item.attrs.get("TransparentColor"),
                    default=(1.0, 1.0, 1.0),
                )
                transparent_color = tuple(
                    round(channel * 255) for channel in color
                )
            digest = hashlib.sha256(raw).hexdigest()
            interpolate = _bool(item.attrs.get("HightQuality"), False)
            cache_key = (digest, transparent_color, interpolate)
            cached = image_cache.get(cache_key)
            if cached is None:
                decoded = decode_image(
                    raw,
                    transparent_color=transparent_color,
                    interpolate=interpolate,
                )
                cached = (f"Im{len(image_cache) + 1}", decoded)
                image_cache[cache_key] = cached
            images_by_item[id(item)] = cached

    # Encoding text populates the final codepoint sets before font objects are
    # emitted.  The page content is generated once and retained.
    page_contents = [
        _render_page_content(
            page,
            fonts_by_item,
            images_by_item,
            frozenset(suppressed_picture_items),
        )
        for page in model.pages
    ]

    builder = PDFBuilder()
    font_objects = {
        use.resource: _font_pdf_objects(builder, use)
        for use in registry.uses
    }
    image_objects: dict[str, int] = {}
    for resource, image in sorted(
        (value for value in image_cache.values()),
        key=lambda value: value[0],
    ):
        alpha_obj = None
        if image.alpha is not None:
            alpha_obj = builder.stream(
                b"/Type /XObject /Subtype /Image /Width "
                + str(image.width).encode("ascii")
                + b" /Height "
                + str(image.height).encode("ascii")
                + b" /ColorSpace /DeviceGray /BitsPerComponent 8 "
                b"/Filter /FlateDecode",
                image.alpha,
            )
        dictionary = (
            b"/Type /XObject /Subtype /Image /Width "
            + str(image.width).encode("ascii")
            + b" /Height "
            + str(image.height).encode("ascii")
            + b" /ColorSpace "
            + image.colorspace
            + b" /BitsPerComponent "
            + str(image.bits).encode("ascii")
            + b" /Filter "
            + image.filter_name
        )
        if image.decode_parms is not None:
            dictionary += b" /DecodeParms " + image.decode_parms
        if image.color_key_mask is not None:
            dictionary += b" /Mask " + image.color_key_mask
        dictionary += (
            b" /Interpolate true"
            if image.interpolate
            else b" /Interpolate false"
        )
        if alpha_obj is not None:
            dictionary += b" /SMask " + f"{alpha_obj} 0 R".encode("ascii")
        image_objects[resource] = builder.stream(dictionary, image.data)

    pages_placeholder = builder.add(b"<< /Type /Pages /Count 0 /Kids [] >>")
    page_objects: list[int] = []
    for page, content in zip(model.pages, page_contents):
        content_obj = builder.stream(b"", content, compress=True)
        font_resources = b" ".join(
            b"/"
            + name.encode("ascii")
            + b" "
            + f"{number} 0 R".encode("ascii")
            for name, number in sorted(font_objects.items())
        )
        image_resources = b" ".join(
            b"/"
            + name.encode("ascii")
            + b" "
            + f"{number} 0 R".encode("ascii")
            for name, number in sorted(image_objects.items())
        )
        resources = b"<< /Font << " + font_resources + b" >>"
        if image_resources:
            resources += b" /XObject << " + image_resources + b" >>"
        resources += b" >>"
        page_obj = builder.add(
            b"<< /Type /Page /Parent "
            + f"{pages_placeholder} 0 R".encode("ascii")
            + b" /MediaBox [0 0 "
            + _pdf_number(page.width_pt).encode("ascii")
            + b" "
            + _pdf_number(page.height_pt).encode("ascii")
            + b"] /Resources "
            + resources
            + b" /Contents "
            + f"{content_obj} 0 R".encode("ascii")
            + b" >>"
        )
        page_objects.append(page_obj)
    builder.objects[pages_placeholder - 1] = (
        b"<< /Type /Pages /Count "
        + str(len(page_objects)).encode("ascii")
        + b" /Kids ["
        + b" ".join(f"{number} 0 R".encode("ascii") for number in page_objects)
        + b"] >>"
    )
    catalog = builder.add(
        b"<< /Type /Catalog /Pages "
        + f"{pages_placeholder} 0 R".encode("ascii")
        + b" >>"
    )
    pdf = builder.finish(catalog)
    validate_pdf(pdf)
    font_files = tuple(
        sorted(
            {
                (str(use.face.path), use.face.sha256)
                for use in registry.uses
                if use.face is not None
            }
        )
    )
    return RenderedFP3(
        pdf=pdf,
        page_count=len(model.pages),
        object_count=sum(len(page.objects) for page in model.pages),
        source_sha256=model.source_sha256,
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        class_inventory=model.class_inventory,
        font_files=font_files,
        image_count=len(image_cache),
        excluded_invisible_count=model.excluded_invisible_count,
        excluded_nonprintable_count=model.excluded_nonprintable_count,
    )


def validate_pdf(data: bytes) -> None:
    """Validate the deterministic PDF container emitted by this renderer."""

    if not data.startswith(b"%PDF-1.7\n") or not data.endswith(b"%%EOF\n"):
        raise FP3RenderError("rendered PDF has invalid boundaries")
    match = re.search(rb"startxref\n([0-9]+)\n%%EOF\n\Z", data)
    if match is None:
        raise FP3RenderError("rendered PDF lacks startxref")
    xref = int(match.group(1))
    if xref <= 0 or xref >= len(data) or not data[xref:].startswith(b"xref\n"):
        raise FP3RenderError("rendered PDF startxref is invalid")
    trailer = data[xref:]
    if b"/Root " not in trailer or b"/Size " not in trailer:
        raise FP3RenderError("rendered PDF trailer is incomplete")


def _secure_atomic_write(path: Path, data: bytes) -> None:
    parent = path.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and path.is_symlink():
        raise FP3RenderError("refusing to replace a symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _read_bounded_regular(
    path: Path,
    *,
    maximum: int,
    label: str,
) -> bytes:
    try:
        info = path.lstat()
    except OSError as error:
        raise FP3RenderError(f"cannot inspect {label}") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size <= 0
        or info.st_size > maximum
    ):
        raise FP3RenderError(f"{label} is outside file policy")
    try:
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except OSError as error:
        raise FP3RenderError(f"cannot read {label}") from error
    if not data or len(data) > maximum:
        raise FP3RenderError(f"{label} is outside size policy")
    return data


def _load_sidecars(paths: Iterable[Path]) -> tuple[bytes, ...]:
    result: list[bytes] = []
    total = 0
    for path in paths:
        value = _read_bounded_regular(
            path,
            maximum=MAX_SIDECAR_BYTES,
            label="image sidecar",
        )
        total += len(value)
        if total > MAX_TOTAL_SIDECAR_BYTES:
            raise FP3RenderError("aggregate image sidecars exceed policy")
        result.append(value)
    return tuple(result)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or render FastReport VCL prepared-report FP3 XML.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Parse and inventory an FP3 stream without rendering.",
    )
    inspect_parser.add_argument("input", type=Path)
    render_parser = subparsers.add_parser(
        "render",
        help="Render one FP3 stream to a new local PDF.",
    )
    render_parser.add_argument("input", type=Path)
    render_parser.add_argument("--output", required=True, type=Path)
    render_parser.add_argument(
        "--sidecar",
        action="append",
        default=[],
        type=Path,
        help="Outer ReportX image component in response order; repeat as needed.",
    )
    render_parser.add_argument(
        "--font",
        type=Path,
        help="Explicit embeddable TrueType font for all text.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data = _read_bounded_regular(
            args.input,
            maximum=MAX_FP3_BYTES,
            label="FP3 input",
        )
        if args.command == "inspect":
            model = parse_fp3(data)
            payload = {
                "ok": True,
                "schema": "reportx-fp3-inspection/v1",
                "source_sha256": model.source_sha256,
                "page_count": len(model.pages),
                "object_count": sum(len(page.objects) for page in model.pages),
                "class_inventory": dict(model.class_inventory),
                "picture_cache_count": len(model.picture_cache),
            }
        else:
            sidecars = _load_sidecars(args.sidecar)
            rendered = render_fp3_pdf(data, sidecars, font_path=args.font)
            _secure_atomic_write(args.output, rendered.pdf)
            payload = {
                "ok": True,
                **rendered.manifest(),
                "output": str(args.output.resolve()),
            }
    except (OSError, FP3RenderError, TypeError) as error:
        payload = {
            "ok": False,
            "error": type(error).__name__,
            "message": str(error),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
