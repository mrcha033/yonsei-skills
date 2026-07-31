#!/usr/bin/env python3
"""Clean-room decoder for the ReportX 1.0 ticket and first remote action.

The implementation mirrors the data path recovered from the currently
distributed REPORTX.exe, without executing that Windows binary:

* strip ``dzreportx:`` in :mod:`reportx_protocol`;
* accept ``||`` as the vendor's plaintext diagnostic form, otherwise decode
  Base64 and ARIA-192-ECB;
* unwrap the four-byte little-endian payload length;
* restore ``|`` query separators to ``&``;
* parse the command URL and build the URLFile request.

This module performs no network, filesystem, browser, PDF, or printer I/O.
The transport broker in :mod:`reportx_protocol` remains the only component
that can turn a tracked server response into an artifact.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import re
import urllib.parse
from dataclasses import dataclass

from reportx_protocol import (
    AcceptServerResponse,
    Failed,
    NetworkResponse,
    RequestAction,
    SessionContext,
    TicketEnvelope,
)


DECODER_ID = "reportx-1.0-cleanroom"
DECODER_VERSION = "0.3.0"
REPORTX_KEY_SEED = b"10001"
MAX_CLEAR_PAYLOAD_BYTES = 64 * 1024
SUPPORTED_COMMANDS = frozenset({"SHOWREPORT", "SHOWREPORT_PRINTAUTO"})
ALLOWED_URLFILE_HOSTS = frozenset(
    {
        "icert.yonsei.ac.kr",
        "uni.webminwon.com",
    }
)
ALLOWED_URLCHECK_PATHS = frozenset(
    {
        "/ys1.0/jsp/report/senddocno.jsp",
    }
)
ALLOWED_URLPOST_PATHS = frozenset(
    {
        "/ys1.0/jsp/report/printcomplete.jsp",
    }
)
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._~:@%+\-/]{1,1024}$")


class TicketDecodeError(ValueError):
    """Raised when a ReportX ticket fails a strict compatibility check."""


def _table(hex_text: str) -> tuple[int, ...]:
    raw = bytes.fromhex("".join(hex_text.split()))
    if len(raw) != 256:
        raise AssertionError("ARIA S-box must contain 256 bytes")
    return tuple(raw)


# RFC 5794 section 2.4.2. SB3 and SB4 are the inverses of SB1 and SB2.
_SB1 = _table(
    """
    637c777bf26b6fc53001672bfed7ab76
    ca82c97dfa5947f0add4a2af9ca472c0
    b7fd9326363ff7cc34a5e5f171d83115
    04c723c31896059a071280e2eb27b275
    09832c1a1b6e5aa0523bd6b329e32f84
    53d100ed20fcb15b6acbbe394a4c58cf
    d0efaafb434d338545f9027f503c9fa8
    51a3408f929d38f5bcb6da2110fff3d2
    cd0c13ec5f974417c4a77e3d645d1973
    60814fdc222a908846eeb814de5e0bdb
    e0323a0a4906245cc2d3ac629195e479
    e7c8376d8dd54ea96c56f4ea657aae08
    ba78252e1ca6b4c6e8dd741f4bbd8b8a
    703eb5664803f60e613557b986c11d9e
    e1f8981169d98e949b1e87e9ce5528df
    8ca1890dbfe6426841992d0fb054bb16
    """
)
_SB2 = _table(
    """
    e24e54fc94c24acc620d6a463c4d8bd1
    5efa64cbb497be2bbc772e03d31959c1
    1d06416b55f09969ea9c18ae63dfe7bb
    007366fb964c85e43a0945aa0fee10eb
    2d7ff429accfad918d78c895f92fcecd
    087a88385c832a2847dbb8c793a41253
    ff870e3136215848018e377432cae9b1
    b7ab0cd7c4564226079860d9b6b91140
    ec208cbda0c984044923f14f501f13dc
    d8c09e57e3c37b653b028f3ee82592e5
    15ddfd17a9bfd49a7ec53967fe769d43
    a7e1d0f568f21b347005a38ad57986a8
    30c6514b1ea627f635d26e2416825fda
    e675a2ef2cb21c9f5d6f800a72449b6c
    900b5b337d5a52f361a1f7b0d63f7c6d
    ed14e0a53d22b3f889de711aafbab581
    """
)


def _inverse(table: tuple[int, ...]) -> tuple[int, ...]:
    out = [0] * 256
    for index, value in enumerate(table):
        out[value] = index
    return tuple(out)


_SB3 = _inverse(_SB1)
_SB4 = _inverse(_SB2)
_C1 = bytes.fromhex("517cc1b727220a94fe13abe8fa9a6ee0")
_C2 = bytes.fromhex("6db14acc9e21c820ff28b1d5ef5de2b0")
_C3 = bytes.fromhex("db92371d2126e9700324977504e8c90e")
_MASK128 = (1 << 128) - 1


def _xor(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("ARIA xor operands must have equal length")
    return bytes(a ^ b for a, b in zip(left, right))


def _sl1(value: bytes) -> bytes:
    boxes = (_SB1, _SB2, _SB3, _SB4)
    return bytes(boxes[index % 4][byte] for index, byte in enumerate(value))


def _sl2(value: bytes) -> bytes:
    boxes = (_SB3, _SB4, _SB1, _SB2)
    return bytes(boxes[index % 4][byte] for index, byte in enumerate(value))


def _diffuse(value: bytes) -> bytes:
    if len(value) != 16:
        raise ValueError("ARIA diffusion input must be one block")
    x = value
    return bytes(
        (
            x[3] ^ x[4] ^ x[6] ^ x[8] ^ x[9] ^ x[13] ^ x[14],
            x[2] ^ x[5] ^ x[7] ^ x[8] ^ x[9] ^ x[12] ^ x[15],
            x[1] ^ x[4] ^ x[6] ^ x[10] ^ x[11] ^ x[12] ^ x[15],
            x[0] ^ x[5] ^ x[7] ^ x[10] ^ x[11] ^ x[13] ^ x[14],
            x[0] ^ x[2] ^ x[5] ^ x[8] ^ x[11] ^ x[14] ^ x[15],
            x[1] ^ x[3] ^ x[4] ^ x[9] ^ x[10] ^ x[14] ^ x[15],
            x[0] ^ x[2] ^ x[7] ^ x[9] ^ x[10] ^ x[12] ^ x[13],
            x[1] ^ x[3] ^ x[6] ^ x[8] ^ x[11] ^ x[12] ^ x[13],
            x[0] ^ x[1] ^ x[4] ^ x[7] ^ x[10] ^ x[13] ^ x[15],
            x[0] ^ x[1] ^ x[5] ^ x[6] ^ x[11] ^ x[12] ^ x[14],
            x[2] ^ x[3] ^ x[5] ^ x[6] ^ x[8] ^ x[13] ^ x[15],
            x[2] ^ x[3] ^ x[4] ^ x[7] ^ x[9] ^ x[12] ^ x[14],
            x[1] ^ x[2] ^ x[6] ^ x[7] ^ x[9] ^ x[11] ^ x[12],
            x[0] ^ x[3] ^ x[6] ^ x[7] ^ x[8] ^ x[10] ^ x[13],
            x[0] ^ x[3] ^ x[4] ^ x[5] ^ x[9] ^ x[11] ^ x[14],
            x[1] ^ x[2] ^ x[4] ^ x[5] ^ x[8] ^ x[10] ^ x[15],
        )
    )


def _fo(data: bytes, round_key: bytes) -> bytes:
    return _diffuse(_sl1(_xor(data, round_key)))


def _fe(data: bytes, round_key: bytes) -> bytes:
    return _diffuse(_sl2(_xor(data, round_key)))


def _ror128(value: int, count: int) -> int:
    count %= 128
    return ((value >> count) | (value << (128 - count))) & _MASK128


def _rol128(value: int, count: int) -> int:
    return _ror128(value, 128 - (count % 128))


def _round_keys(
    master_key: bytes,
    *,
    reportx_w3_quirk: bool = False,
) -> tuple[bytes, ...]:
    if len(master_key) not in {16, 24, 32}:
        raise ValueError("ARIA key must be 128, 192, or 256 bits")
    constants = {
        16: (_C1, _C2, _C3),
        24: (_C2, _C3, _C1),
        32: (_C3, _C1, _C2),
    }[len(master_key)]
    kl = master_key[:16]
    kr = master_key[16:].ljust(16, b"\0")
    w0 = kl
    w1 = _xor(_fo(w0, constants[0]), kr)
    w2 = _xor(_fe(w1, constants[1]), w0)
    w3_intermediate = _fo(w2, constants[2])
    if reportx_w3_quirk:
        # REPORTX.exe 1.0.0.36 at 0x54ca65-0x54ca7d and the Yonsei
        # package 1.0.0.29 binary at 0x54be82-0x54be8d use the mutable
        # second byte of the W3 destination as a latch instead of XORing W1
        # byte-for-byte with the FO result. At index 1 the loop overwrites
        # that latch, so indices 2..15 use the newly written value.
        w3_mutable = bytearray(w3_intermediate)
        for index in range(16):
            w3_mutable[index] = w1[index] ^ w3_mutable[1]
        w3 = bytes(w3_mutable)
    else:
        w3 = _xor(w3_intermediate, w1)
    wi = tuple(int.from_bytes(item, "big") for item in (w0, w1, w2, w3))

    values = (
        wi[0] ^ _ror128(wi[1], 19),
        wi[1] ^ _ror128(wi[2], 19),
        wi[2] ^ _ror128(wi[3], 19),
        _ror128(wi[0], 19) ^ wi[3],
        wi[0] ^ _ror128(wi[1], 31),
        wi[1] ^ _ror128(wi[2], 31),
        wi[2] ^ _ror128(wi[3], 31),
        _ror128(wi[0], 31) ^ wi[3],
        wi[0] ^ _rol128(wi[1], 61),
        wi[1] ^ _rol128(wi[2], 61),
        wi[2] ^ _rol128(wi[3], 61),
        _rol128(wi[0], 61) ^ wi[3],
        wi[0] ^ _rol128(wi[1], 31),
        wi[1] ^ _rol128(wi[2], 31),
        wi[2] ^ _rol128(wi[3], 31),
        _rol128(wi[0], 31) ^ wi[3],
        wi[0] ^ _rol128(wi[1], 19),
    )
    rounds = {16: 12, 24: 14, 32: 16}[len(master_key)]
    return tuple(
        value.to_bytes(16, "big") for value in values[: rounds + 1]
    )


def _reportx_round_keys(master_key: bytes) -> tuple[bytes, ...]:
    """Return round keys matching the vendor's non-RFC W3 schedule."""

    return _round_keys(master_key, reportx_w3_quirk=True)


def _crypt_block(block: bytes, round_keys: tuple[bytes, ...]) -> bytes:
    if len(block) != 16:
        raise ValueError("ARIA block must contain 16 bytes")
    rounds = len(round_keys) - 1
    state = block
    for index in range(rounds - 1):
        state = (
            _fo(state, round_keys[index])
            if index % 2 == 0
            else _fe(state, round_keys[index])
        )
    return _xor(_sl2(_xor(state, round_keys[-2])), round_keys[-1])


def aria_encrypt_block(block: bytes, master_key: bytes) -> bytes:
    """Encrypt one ARIA block; exposed for deterministic RFC-vector tests."""

    return _crypt_block(block, _round_keys(master_key))


def aria_decrypt_block(block: bytes, master_key: bytes) -> bytes:
    """Decrypt one ARIA block using the RFC 5794 inverse key schedule."""

    encryption_keys = _round_keys(master_key)
    decryption_keys = (
        encryption_keys[-1],
        *(_diffuse(key) for key in reversed(encryption_keys[1:-1])),
        encryption_keys[0],
    )
    return _crypt_block(block, decryption_keys)


def reportx_aria_encrypt_block(block: bytes, master_key: bytes) -> bytes:
    """Encrypt one block with the key-schedule behavior in REPORTX.exe."""

    return _crypt_block(block, _reportx_round_keys(master_key))


def reportx_aria_decrypt_block(block: bytes, master_key: bytes) -> bytes:
    """Decrypt one block with the key-schedule behavior in REPORTX.exe."""

    encryption_keys = _reportx_round_keys(master_key)
    decryption_keys = (
        encryption_keys[-1],
        *(_diffuse(key) for key in reversed(encryption_keys[1:-1])),
        encryption_keys[0],
    )
    return _crypt_block(block, decryption_keys)


def _reportx_key() -> bytes:
    # REPORTX.exe first formats upper-case MD5 hex, then immediately runs the
    # result through its ASCII lower-case helper before assigning the ARIA key.
    # The object is fixed to 192 bits, so only the first 24 bytes are consumed.
    return hashlib.md5(REPORTX_KEY_SEED).hexdigest().encode("ascii")[:24]


def decode_ticket_cleartext(ticket: TicketEnvelope) -> tuple[bytes, bool]:
    """Return the framed ticket payload and whether encryption was used."""

    if ticket.payload.startswith(b"||"):
        clear = ticket.payload[2:]
        if not clear:
            raise TicketDecodeError("plaintext ReportX ticket is empty")
        return clear, False

    try:
        ciphertext = base64.b64decode(ticket.payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise TicketDecodeError("ticket payload is not strict Base64") from error
    if not ciphertext or len(ciphertext) % 16:
        raise TicketDecodeError("encrypted ticket is not whole ARIA blocks")

    key = _reportx_key()
    framed = b"".join(
        reportx_aria_decrypt_block(ciphertext[offset : offset + 16], key)
        for offset in range(0, len(ciphertext), 16)
    )
    if len(framed) < 4:
        raise TicketDecodeError("decrypted ticket frame is too short")
    declared = int.from_bytes(framed[:4], "little", signed=False)
    if declared == 0 or declared > MAX_CLEAR_PAYLOAD_BYTES:
        raise TicketDecodeError("decrypted ticket length is outside policy")
    end = 4 + declared
    if end > len(framed):
        raise TicketDecodeError("decrypted ticket length exceeds its frame")
    if any(framed[end:]):
        raise TicketDecodeError("decrypted ticket has non-zero block padding")
    return framed[4:end], True


@dataclass(frozen=True)
class ParsedReportXTicket:
    command: str
    source_url: str
    fields: tuple[tuple[str, str], ...]
    request_url: str
    encrypted: bool

    def get(self, key: str) -> str | None:
        for candidate, value in self.fields:
            if candidate == key:
                return value
        return None


def _safe_request_value(
    parsed: ParsedReportXTicket,
    key: str,
    *,
    allow_empty: bool = False,
    maximum: int = 256,
) -> str:
    value = parsed.get(key)
    if value is None or (not value and not allow_empty):
        raise TicketDecodeError(f"ticket is missing {key}")
    if (
        len(value) > maximum
        or not value.isascii()
        or (value and _SAFE_COMPONENT_RE.fullmatch(value) is None)
    ):
        raise TicketDecodeError(f"{key} is outside policy")
    return value


def build_document_number_action(
    parsed: ParsedReportXTicket,
) -> RequestAction:
    """Build the one-shot URLCheck reservation request used before printing."""

    endpoint = _safe_request_value(parsed, "URLCheck", maximum=2048)
    host, path = _parse_urlfile(endpoint)
    if path not in ALLOWED_URLCHECK_PATHS:
        raise TicketDecodeError("URLCheck path is outside policy")
    copies = _safe_request_value(parsed, "Copies", maximum=2)
    if copies != "1":
        raise TicketDecodeError("only one-copy document reservation is supported")
    min_no = _safe_request_value(parsed, "MINNO")
    receive_type = _safe_request_value(parsed, "RECEIVE_TYPE", maximum=64)
    receive_target = _safe_request_value(
        parsed,
        "RECEIVE_TARGET",
        allow_empty=True,
    )
    url = urllib.parse.urlunsplit(
        (
            "https",
            host,
            path,
            urllib.parse.urlencode(
                (
                    ("MIN_NO", min_no),
                    ("RECEIVE_TYPE", receive_type),
                    ("RECEIVE_TARGET", receive_target),
                )
            ),
            "",
        )
    )
    return RequestAction(
        request_id="reportx-document-number",
        method="GET",
        url=url,
        headers=(("Accept", "text/plain"),),
    )


def parse_document_number_response(response: NetworkResponse) -> str:
    """Validate the exact 16-character response from URLCheck.

    The Windows client accepts a longer concatenation for multiple copies.
    This compatibility path deliberately supports one copy only so a network
    retry can never allocate an untracked second number.
    """

    if response.request_id != "reportx-document-number":
        raise TicketDecodeError("URLCheck response id does not match")
    if response.status != 200:
        raise TicketDecodeError("URLCheck returned non-200")
    if b"<" in response.body or b"Bad" in response.body:
        raise TicketDecodeError("URLCheck returned an error marker")
    body = response.body
    if b"\0" in body:
        if len(body) != 1000 or any(body[16:]):
            raise TicketDecodeError(
                "URLCheck response has invalid NUL padding"
            )
        value_bytes = body[:16]
    else:
        value_bytes = body
    try:
        value = value_bytes.decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise TicketDecodeError("URLCheck response is not ASCII") from error
    if len(value) != 16 or re.fullmatch(r"[0-9A-Za-z]{16}", value) is None:
        raise TicketDecodeError("URLCheck response is not one document number")
    return value


def build_print_completion_action(
    parsed: ParsedReportXTicket,
    *,
    document_number: str,
    system_ip: str,
    printer_model: str,
) -> RequestAction:
    """Build the vendor print-completion GET after a durable PDF save."""

    endpoint = _safe_request_value(parsed, "URLPost", maximum=2048)
    host, path = _parse_urlfile(endpoint)
    if path not in ALLOWED_URLPOST_PATHS:
        raise TicketDecodeError("URLPost path is outside policy")
    tpid = _safe_request_value(parsed, "TPID")
    receive_type = _safe_request_value(parsed, "RECEIVE_TYPE", maximum=64)
    if re.fullmatch(r"[0-9A-Za-z]{16}", document_number) is None:
        raise TicketDecodeError("document number is outside policy")
    try:
        address = ipaddress.ip_address(system_ip)
    except ValueError as error:
        raise TicketDecodeError("system IP is outside policy") from error
    if address.version != 4:
        raise TicketDecodeError("system IP must be IPv4")
    if (
        not printer_model
        or len(printer_model) > 64
        or not printer_model.isascii()
        or any(ord(char) < 0x20 for char in printer_model)
    ):
        raise TicketDecodeError("printer model is outside policy")
    url = urllib.parse.urlunsplit(
        (
            "https",
            host,
            path,
            urllib.parse.urlencode(
                (
                    ("TPID", tpid),
                    ("SYSTEM_IP", str(address)),
                    ("P_MODEL", printer_model),
                    ("MIN_DOC_NO", document_number),
                    ("RECEIVE_TYPE", receive_type),
                )
            ),
            "",
        )
    )
    return RequestAction(
        request_id="reportx-print-completion",
        method="GET",
        url=url,
        headers=(("Accept", "text/plain, */*"),),
    )


def _parse_urlfile(value: str) -> tuple[str, str]:
    if not value or len(value) > 2048 or not _SAFE_COMPONENT_RE.fullmatch(value):
        raise TicketDecodeError("URLFile contains unsupported characters")
    parsed = urllib.parse.urlsplit("//" + value)
    if (
        not parsed.hostname
        or parsed.hostname.lower() not in ALLOWED_URLFILE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise TicketDecodeError("URLFile is outside the Yonsei host policy")
    path = parsed.path or "/"
    if not path.startswith("/") or ".." in path.split("/"):
        raise TicketDecodeError("URLFile path is invalid")
    return parsed.hostname.lower(), path


def parse_reportx_ticket(ticket: TicketEnvelope) -> ParsedReportXTicket:
    clear_bytes, encrypted = decode_ticket_cleartext(ticket)
    try:
        # REPORTX 1.0 is a non-Unicode Windows application.  Yonsei tickets
        # can carry Korean display-only fields in the system ANSI code page,
        # while the four request-bearing fields remain restricted below.
        clear = clear_bytes.decode("cp949", errors="strict")
    except UnicodeDecodeError as error:
        raise TicketDecodeError("ticket cleartext is not strict CP949") from error
    if len(clear) > MAX_CLEAR_PAYLOAD_BYTES or any(ord(char) < 0x20 for char in clear):
        raise TicketDecodeError("ticket cleartext is outside policy")

    restored = clear.replace("|", "&")
    parsed = urllib.parse.urlsplit(restored)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TicketDecodeError("ticket cleartext is not a ReportX command URL")
    command = parsed.path.rsplit("/", 1)[-1].upper()
    if command not in SUPPORTED_COMMANDS:
        raise TicketDecodeError(f"unsupported ReportX command: {command or '<empty>'}")
    try:
        pairs = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=64,
        )
    except ValueError as error:
        raise TicketDecodeError("ticket query is malformed") from error
    if len({key for key, _ in pairs}) != len(pairs):
        raise TicketDecodeError("ticket query contains duplicate fields")
    fields = dict(pairs)
    required = ("URLFile", "TPID", "MINNO", "GIWAN_NO")
    missing = tuple(name for name in required if not fields.get(name))
    if missing:
        raise TicketDecodeError("ticket is missing fields: " + ",".join(missing))
    for name in ("TPID", "MINNO", "GIWAN_NO"):
        value = fields[name]
        if (
            len(value) > 256
            or not value.isascii()
            or not _SAFE_COMPONENT_RE.fullmatch(value)
        ):
            raise TicketDecodeError(f"{name} is outside policy")

    host, path = _parse_urlfile(fields["URLFile"])
    # The Windows viewer hard-codes http://. The clean-room broker upgrades the
    # same host/path/query to HTTPS because the current endpoint supports it and
    # the broker deliberately refuses cleartext transport.
    request_url = urllib.parse.urlunsplit(
        (
            "https",
            host,
            path,
            urllib.parse.urlencode(
                (
                    ("TPID", fields["TPID"]),
                    ("MIN_NO", fields["MINNO"]),
                    ("GIWAN_NO", fields["GIWAN_NO"]),
                )
            ),
            "",
        )
    )
    return ParsedReportXTicket(
        command=command,
        source_url=restored,
        fields=tuple(pairs),
        request_url=request_url,
        encrypted=encrypted,
    )


class ReportXProtocolV1Session:
    """One-request decoder state machine for SHOWREPORT URLFile."""

    __slots__ = ("parsed", "_state")
    decoder_id = DECODER_ID
    decoder_version = DECODER_VERSION

    def __init__(self, parsed: ParsedReportXTicket) -> None:
        self.parsed = parsed
        self._state = "new"

    def step(self, event=None):  # noqa: ANN001, ANN201
        if self._state == "new":
            if event is not None:
                return Failed("unexpected_event", "initial decoder event must be empty")
            self._state = "waiting"
            return RequestAction(
                request_id="reportx-page",
                method="GET",
                url=self.parsed.request_url,
                headers=(("Accept", "application/octet-stream, application/pdf"),),
            )
        if self._state == "waiting":
            if not isinstance(event, NetworkResponse):
                return Failed("response_required", "URLFile response is required")
            if event.request_id != "reportx-page":
                return Failed("response_mismatch", "URLFile response id does not match")
            if event.status != 200:
                return Failed("remote_status", f"URLFile returned HTTP {event.status}")
            if not event.body:
                return Failed("empty_response", "URLFile returned an empty body")
            self._state = "accepted"
            return AcceptServerResponse(
                request_id=event.request_id,
                expected_sha256=event.body_sha256,
            )
        return Failed("session_complete", "decoder session is already complete")


class ReportXProtocolV1Decoder:
    decoder_id = DECODER_ID
    version = DECODER_VERSION

    def supports(self, ticket: TicketEnvelope) -> bool:
        # Both the official plaintext diagnostic form and encrypted Base64 form
        # are part of ReportX 1.0. Parsing remains strict in open().
        return ticket.payload.startswith(b"||") or bool(ticket.payload)

    def open(
        self,
        ticket: TicketEnvelope,
        context: SessionContext,
    ) -> ReportXProtocolV1Session:
        del context  # Ticket contains the request inputs; credentials are forbidden.
        return ReportXProtocolV1Session(parse_reportx_ticket(ticket))
