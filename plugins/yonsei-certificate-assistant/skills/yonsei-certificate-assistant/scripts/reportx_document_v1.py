#!/usr/bin/env python3
"""Decode the first ReportX server-response container without rendering it.

Static analysis of REPORTX.exe 1.0.0.36 established this pipeline:

* derive a 192-bit ARIA key from the ticket's ``MINNO`` value;
* decrypt the URLFile response as independent 16-byte ARIA blocks;
* remove its little-endian compressed-length envelope and zero cipher padding;
* inflate the enclosed zlib stream;
* read one primary length-prefixed stream and a bounded list of additional
  length-prefixed streams.

The primary payload is consumed as a FastReport prepared-report XML stream and
the additional payloads as image sidecars by the Windows viewer. Their renderer
is not implemented here. This module performs no network, filesystem, PDF, or
printer I/O and never modifies component bytes.
"""

from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass, field

from reportx_protocol_v1 import reportx_aria_decrypt_block


MAX_ENCRYPTED_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_INFLATED_RESPONSE_BYTES = 128 * 1024 * 1024
MAX_COMPONENT_BYTES = 64 * 1024 * 1024
MAX_ADDITIONAL_COMPONENTS = 256


class ReportXDocumentError(ValueError):
    """Raised when a server response fails the recovered container contract."""


def reportx_document_key(min_no: str) -> bytes:
    """Return the lower-case MD5-hex ARIA-192 key used by REPORTX.exe."""

    if not isinstance(min_no, str):
        raise TypeError("MINNO must be text")
    try:
        encoded = min_no.encode("ascii", errors="strict")
    except UnicodeEncodeError as error:
        raise ReportXDocumentError("MINNO must be ASCII") from error
    if not encoded or len(encoded) > 256 or any(byte < 0x20 for byte in encoded):
        raise ReportXDocumentError("MINNO is outside policy")
    return hashlib.md5(encoded).hexdigest().encode("ascii")[:24]


def decrypt_reportx_response(response: bytes, min_no: str) -> bytes:
    """Decrypt blocks and return the strictly framed compressed payload."""

    if not isinstance(response, bytes):
        raise TypeError("ReportX response must be immutable bytes")
    if (
        not response
        or len(response) > MAX_ENCRYPTED_RESPONSE_BYTES
        or len(response) % 16
    ):
        raise ReportXDocumentError(
            "encrypted ReportX response must contain bounded whole ARIA blocks"
        )
    key = reportx_document_key(min_no)
    cleartext = b"".join(
        reportx_aria_decrypt_block(response[offset : offset + 16], key)
        for offset in range(0, len(response), 16)
    )
    if len(cleartext) < 4:
        raise ReportXDocumentError("decrypted ReportX response lacks length frame")
    declared = int.from_bytes(cleartext[:4], "little", signed=False)
    if declared == 0 or declared > MAX_ENCRYPTED_RESPONSE_BYTES:
        raise ReportXDocumentError(
            "compressed ReportX response length is outside policy"
        )
    end = 4 + declared
    if end > len(cleartext):
        raise ReportXDocumentError("compressed ReportX response is truncated")
    if any(cleartext[end:]):
        raise ReportXDocumentError(
            "ReportX response has non-zero cipher padding"
        )
    return cleartext[4:end]


def inflate_reportx_response(cleartext: bytes) -> bytes:
    """Inflate exactly one bounded zlib stream."""

    inflater = zlib.decompressobj(zlib.MAX_WBITS)
    try:
        inflated = inflater.decompress(
            cleartext,
            MAX_INFLATED_RESPONSE_BYTES + 1,
        )
        if len(inflated) > MAX_INFLATED_RESPONSE_BYTES or inflater.unconsumed_tail:
            raise ReportXDocumentError("inflated ReportX response exceeds policy")
        remaining = MAX_INFLATED_RESPONSE_BYTES + 1 - len(inflated)
        inflated += inflater.flush(remaining)
    except zlib.error as error:
        raise ReportXDocumentError("ReportX response is not a valid zlib stream") from error
    if len(inflated) > MAX_INFLATED_RESPONSE_BYTES:
        raise ReportXDocumentError("inflated ReportX response exceeds policy")
    if not inflater.eof:
        raise ReportXDocumentError("ReportX zlib stream is truncated")
    if inflater.unused_data:
        raise ReportXDocumentError("ReportX zlib stream has trailing bytes")
    return inflated


@dataclass(frozen=True)
class ReportXDocumentBundle:
    """Unmodified component bytes extracted from the recovered outer framing."""

    primary: bytes = field(repr=False)
    additional: tuple[bytes, ...] = field(repr=False)

    @property
    def component_count(self) -> int:
        return 1 + len(self.additional)

    @property
    def primary_sha256(self) -> str:
        return hashlib.sha256(self.primary).hexdigest()

    @property
    def additional_sha256(self) -> tuple[str, ...]:
        return tuple(hashlib.sha256(item).hexdigest() for item in self.additional)


def parse_reportx_document_frame(frame: bytes) -> ReportXDocumentBundle:
    """Parse the length-prefixed component list recovered at 0x54d280."""

    if not isinstance(frame, bytes):
        raise TypeError("ReportX document frame must be immutable bytes")
    view = memoryview(frame)
    offset = 0

    def read_u32(label: str) -> int:
        nonlocal offset
        if offset + 4 > len(view):
            raise ReportXDocumentError(f"missing {label}")
        value = int.from_bytes(view[offset : offset + 4], "little", signed=False)
        offset += 4
        return value

    def read_component(label: str) -> bytes:
        nonlocal offset
        size = read_u32(f"{label} length")
        if size == 0 or size > MAX_COMPONENT_BYTES:
            raise ReportXDocumentError(f"{label} length is outside policy")
        end = offset + size
        if end > len(view):
            raise ReportXDocumentError(f"{label} exceeds the document frame")
        value = bytes(view[offset:end])
        offset = end
        return value

    primary = read_component("primary component")
    additional_count = read_u32("additional component count")
    if additional_count > MAX_ADDITIONAL_COMPONENTS:
        raise ReportXDocumentError("too many additional ReportX components")
    additional = tuple(
        read_component(f"additional component {index}")
        for index in range(additional_count)
    )
    if offset != len(view):
        raise ReportXDocumentError("ReportX document frame has trailing bytes")
    return ReportXDocumentBundle(primary=primary, additional=additional)


def decode_reportx_document(response: bytes, min_no: str) -> ReportXDocumentBundle:
    """Run the recovered response pipeline and return unrendered components."""

    cleartext = decrypt_reportx_response(response, min_no)
    frame = inflate_reportx_response(cleartext)
    return parse_reportx_document_frame(frame)
