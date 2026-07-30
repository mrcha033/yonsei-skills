#!/usr/bin/env python3
"""Data-only protocol boundary for clean-room ReportX interoperability.

This module deliberately contains no ReportX cipher, key, HTTP client, cookie
jar, filesystem access, or printing code.  A decoder may describe a bounded
HTTPS request and may select an exact response previously supplied by a
transport.  It cannot return artifact bytes of its own.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Protocol, Union, runtime_checkable
from urllib.parse import urlsplit


TICKET_PREFIX = "dzreportx:"
DEFAULT_MAX_TICKET_BYTES = 64 * 1024
DEFAULT_MAX_CONTEXT_ITEMS = 32
DEFAULT_MAX_CONTEXT_VALUE_BYTES = 4 * 1024
DEFAULT_MAX_CONTEXT_BYTES = 32 * 1024

_CONTEXT_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "host",
        "proxy-authorization",
    }
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _contains_control(value: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)


@dataclass(frozen=True)
class TicketEnvelope:
    """Strict, opaque outer ``dzreportx:`` envelope.

    The payload is kept byte-for-byte as visible ASCII.  Parsing the outer
    envelope does not assume base64, a cipher mode, padding, or a key.
    """

    payload: bytes = field(repr=False)
    raw_length: int
    raw_sha256: str
    scheme: str = "dzreportx"

    @classmethod
    def parse(
        cls,
        value: str,
        *,
        max_bytes: int = DEFAULT_MAX_TICKET_BYTES,
    ) -> "TicketEnvelope":
        if not isinstance(value, str):
            raise TypeError("ticket must be text")
        if not isinstance(max_bytes, int) or max_bytes < len(TICKET_PREFIX) + 1:
            raise ValueError("max_bytes is too small")
        try:
            raw = value.encode("ascii", errors="strict")
        except UnicodeEncodeError as error:
            raise ValueError("ticket must contain visible ASCII only") from error
        if len(raw) > max_bytes:
            raise ValueError("ticket exceeds the configured size limit")
        if not value.startswith(TICKET_PREFIX):
            raise ValueError("ticket must start with dzreportx:")
        payload = raw[len(TICKET_PREFIX) :]
        if not payload:
            raise ValueError("ticket payload is empty")
        if any(byte < 0x21 or byte > 0x7E for byte in payload):
            raise ValueError("ticket payload must contain visible ASCII only")
        return cls(
            payload=payload,
            raw_length=len(raw),
            raw_sha256=_sha256(raw),
        )

    def as_uri(self) -> str:
        """Reconstruct the in-memory envelope without decoding its payload."""

        return TICKET_PREFIX + self.payload.decode("ascii")

    @property
    def payload_sha256(self) -> str:
        return _sha256(self.payload)


@dataclass(frozen=True)
class SessionContext:
    """Bounded non-credential context made available to a decoder."""

    origin: str
    values: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.origin, str):
            raise TypeError("context origin must be text")
        if not self.origin or len(self.origin.encode("utf-8")) > 512:
            raise ValueError("context origin is empty or too large")
        if _contains_control(self.origin):
            raise ValueError("context origin contains control characters")
        if len(self.values) > DEFAULT_MAX_CONTEXT_ITEMS:
            raise ValueError("too many context values")

        seen: set[str] = set()
        total = len(self.origin.encode("utf-8"))
        for item in self.values:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("context values must be (key, value) tuples")
            key, value = item
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("context keys and values must be text")
            if not _CONTEXT_KEY_RE.fullmatch(key):
                raise ValueError(f"invalid context key: {key!r}")
            folded = key.casefold()
            if folded in seen:
                raise ValueError(f"duplicate context key: {key!r}")
            seen.add(folded)
            encoded = value.encode("utf-8")
            if len(encoded) > DEFAULT_MAX_CONTEXT_VALUE_BYTES:
                raise ValueError(f"context value is too large: {key!r}")
            if _contains_control(value):
                raise ValueError(f"context value contains control characters: {key!r}")
            total += len(key.encode("utf-8")) + len(encoded)
            if total > DEFAULT_MAX_CONTEXT_BYTES:
                raise ValueError("context exceeds the total size limit")

    @classmethod
    def from_mapping(cls, origin: str, values: Mapping[str, str]) -> "SessionContext":
        if not isinstance(values, Mapping):
            raise TypeError("context values must be a mapping")
        return cls(origin=origin, values=tuple(sorted(values.items())))

    def get(self, key: str, default: str | None = None) -> str | None:
        for candidate, value in self.values:
            if candidate == key:
                return value
        return default

    @property
    def mapping(self) -> Mapping[str, str]:
        return MappingProxyType(dict(self.values))


Headers = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RequestAction:
    request_id: str
    method: str
    url: str
    headers: Headers = ()
    body: bytes = field(default=b"", repr=False)


@dataclass(frozen=True)
class NetworkResponse:
    request_id: str
    url: str
    status: int
    headers: Headers
    body: bytes = field(repr=False)
    body_sha256: str

    @classmethod
    def from_bytes(
        cls,
        *,
        request_id: str,
        url: str,
        status: int,
        headers: Headers = (),
        body: bytes,
    ) -> "NetworkResponse":
        immutable_body = bytes(body)
        return cls(
            request_id=request_id,
            url=url,
            status=status,
            headers=tuple(headers),
            body=immutable_body,
            body_sha256=_sha256(immutable_body),
        )


@dataclass(frozen=True)
class NeedContext:
    keys: tuple[str, ...]
    reason: str = ""


@dataclass(frozen=True)
class AcceptServerResponse:
    """Select a tracked server response; intentionally has no bytes field."""

    request_id: str
    expected_sha256: str


@dataclass(frozen=True)
class Unsupported:
    reason: str


@dataclass(frozen=True)
class Failed:
    code: str
    message: str


ProtocolAction = Union[
    RequestAction,
    NeedContext,
    AcceptServerResponse,
    Unsupported,
    Failed,
]
ProtocolInput = Optional[
    Union[
        SessionContext,
        NetworkResponse,
    ]
]


@runtime_checkable
class ProtocolSession(Protocol):
    """A deterministic decoder state machine without I/O capabilities."""

    def step(self, event: ProtocolInput = None) -> ProtocolAction:
        ...


@runtime_checkable
class Decoder(Protocol):
    decoder_id: str
    version: str

    def supports(self, ticket: TicketEnvelope) -> bool:
        ...

    def open(
        self,
        ticket: TicketEnvelope,
        context: SessionContext,
    ) -> ProtocolSession:
        ...


ProtocolDecoder = Decoder


def _bundled_decoder_types() -> tuple[type[Decoder], ...]:
    """Return only decoder implementations shipped beside this module."""

    # Local import avoids a module cycle: the implementation consumes the
    # immutable action types above. There is intentionally no configurable
    # module path, entry point, environment variable, or filesystem loader.
    from reportx_protocol_v1 import ReportXProtocolV1Decoder

    return (ReportXProtocolV1Decoder,)


class BundledDecoderRegistry:
    """Fixed source-bundled decoder registry."""

    __slots__ = ("_decoders",)

    def __init__(self) -> None:
        self._decoders: tuple[Decoder, ...] = tuple(
            decoder_type() for decoder_type in _bundled_decoder_types()
        )

    @property
    def decoder_ids(self) -> tuple[str, ...]:
        return tuple(decoder.decoder_id for decoder in self._decoders)

    def open(
        self,
        ticket: TicketEnvelope,
        context: SessionContext,
    ) -> ProtocolSession | Unsupported | Failed:
        for decoder in self._decoders:
            try:
                if decoder.supports(ticket):
                    return decoder.open(ticket, context)
            except Exception as error:  # fail closed at the decoder boundary
                return Failed("decoder_open_failed", type(error).__name__)
        return Unsupported("no bundled decoder supports this ticket")


@dataclass(frozen=True)
class BrokerPolicy:
    """Transport policy enforced before an action reaches an HTTP client."""

    allowed_hosts: frozenset[str]
    max_steps: int = 16
    max_request_body_bytes: int = 1024 * 1024
    max_response_body_bytes: int = 32 * 1024 * 1024
    max_total_response_bytes: int = 64 * 1024 * 1024
    max_headers: int = 32
    max_header_bytes: int = 16 * 1024

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("an exact host allowlist is required")
        for host in self.allowed_hosts:
            if (
                not isinstance(host, str)
                or not host
                or host != host.lower()
                or "*" in host
                or "/" in host
                or ":" in host
                or _contains_control(host)
            ):
                raise ValueError(f"invalid exact allowlist host: {host!r}")
        for name in (
            "max_steps",
            "max_request_body_bytes",
            "max_response_body_bytes",
            "max_total_response_bytes",
            "max_headers",
            "max_header_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class AcceptedArtifact:
    """Unmodified bytes selected from one tracked network response."""

    request_id: str
    source_url: str
    status: int
    body: bytes = field(repr=False)
    sha256: str


def _validate_request_id(request_id: str) -> str | None:
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
        return "request_id must be 1-64 safe ASCII characters"
    return None


def _validate_headers(
    headers: Headers,
    *,
    policy: BrokerPolicy,
    decoder_supplied: bool,
) -> str | None:
    if not isinstance(headers, tuple):
        return "headers must be an immutable tuple"
    if len(headers) > policy.max_headers:
        return "too many headers"
    total = 0
    seen: set[str] = set()
    for item in headers:
        if not isinstance(item, tuple) or len(item) != 2:
            return "headers must contain (name, value) tuples"
        name, value = item
        if not isinstance(name, str) or not isinstance(value, str):
            return "header names and values must be text"
        if not _HEADER_NAME_RE.fullmatch(name):
            return "invalid header name"
        if _contains_control(value):
            return "header value contains control characters"
        folded = name.casefold()
        if folded in seen:
            return "duplicate header"
        seen.add(folded)
        if decoder_supplied and (
            folded in _FORBIDDEN_REQUEST_HEADERS or folded.startswith("proxy-")
        ):
            return f"decoder may not set {name}"
        total += len(name.encode("ascii")) + len(value.encode("utf-8"))
        if total > policy.max_header_bytes:
            return "headers exceed the size limit"
    return None


def validate_request_action(
    action: RequestAction,
    policy: BrokerPolicy,
) -> Failed | None:
    """Validate a decoder request without performing it."""

    request_id_error = _validate_request_id(action.request_id)
    if request_id_error:
        return Failed("invalid_request_id", request_id_error)
    if action.method not in {"GET", "POST"}:
        return Failed("method_forbidden", "only GET and POST are allowed")
    if not isinstance(action.url, str) or _contains_control(action.url):
        return Failed("invalid_url", "request URL is invalid")
    try:
        parsed = urlsplit(action.url)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        return Failed("invalid_url", "request URL is invalid")
    if parsed.scheme != "https":
        return Failed("scheme_forbidden", "only HTTPS is allowed")
    if parsed.username is not None or parsed.password is not None:
        return Failed("userinfo_forbidden", "URL userinfo is forbidden")
    if parsed.fragment:
        return Failed("fragment_forbidden", "URL fragments are forbidden")
    if not host or host != host.lower() or host not in policy.allowed_hosts:
        return Failed("host_forbidden", "request host is not exactly allowlisted")
    if port not in {None, 443}:
        return Failed("port_forbidden", "only HTTPS port 443 is allowed")
    if not isinstance(action.body, bytes):
        return Failed("invalid_request_body", "request body must be immutable bytes")
    if len(action.body) > policy.max_request_body_bytes:
        return Failed("request_too_large", "request body exceeds the size limit")
    if action.method == "GET" and action.body:
        return Failed("get_body_forbidden", "GET requests may not contain a body")
    header_error = _validate_headers(
        action.headers,
        policy=policy,
        decoder_supplied=True,
    )
    if header_error:
        return Failed("header_forbidden", header_error)
    return None


class ProtocolBroker:
    """Policy gate between a pure decoder session and an external transport.

    ``start`` and ``provide_context`` may emit a validated ``RequestAction``.
    The caller performs that request with redirects disabled, then supplies the
    response through ``receive``.  Only bytes from such a tracked response can
    become ``accepted_artifact``.
    """

    __slots__ = (
        "_accepted",
        "_completed",
        "_pending",
        "_policy",
        "_session",
        "_state",
        "_steps",
        "_total_response_bytes",
    )

    def __init__(self, session: ProtocolSession, policy: BrokerPolicy) -> None:
        if not isinstance(session, ProtocolSession):
            raise TypeError("session must implement ProtocolSession")
        self._session = session
        self._policy = policy
        self._state = "new"
        self._steps = 0
        self._pending: dict[str, RequestAction] = {}
        self._completed: dict[str, NetworkResponse] = {}
        self._accepted: AcceptedArtifact | None = None
        self._total_response_bytes = 0

    @property
    def accepted_artifact(self) -> AcceptedArtifact | None:
        return self._accepted

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> ProtocolAction:
        if self._state != "new":
            return self._terminal_failure("invalid_state", "broker is already started")
        return self._step(None)

    def provide_context(self, context: SessionContext) -> ProtocolAction:
        if self._state != "need_context":
            return self._terminal_failure("invalid_state", "context was not requested")
        return self._step(context)

    def receive(self, response: NetworkResponse) -> ProtocolAction:
        if self._state != "waiting_response":
            return self._terminal_failure("invalid_state", "no response is pending")
        request_id_error = _validate_request_id(response.request_id)
        if request_id_error:
            return self._terminal_failure("invalid_response_id", request_id_error)
        request = self._pending.get(response.request_id)
        if request is None:
            return self._terminal_failure(
                "untracked_response",
                "response does not match a tracked request",
            )
        if response.url != request.url:
            return self._terminal_failure(
                "redirect_forbidden",
                "response URL differs from the requested URL",
            )
        if not isinstance(response.status, int) or not 100 <= response.status <= 599:
            return self._terminal_failure("invalid_status", "invalid HTTP status")
        if 300 <= response.status <= 399:
            return self._terminal_failure(
                "redirect_forbidden",
                "redirect responses are not followed or accepted",
            )
        header_error = _validate_headers(
            response.headers,
            policy=self._policy,
            decoder_supplied=False,
        )
        if header_error:
            return self._terminal_failure("invalid_response_headers", header_error)
        if not isinstance(response.body, bytes):
            return self._terminal_failure(
                "invalid_response_body",
                "response body must be immutable bytes",
            )
        if len(response.body) > self._policy.max_response_body_bytes:
            return self._terminal_failure(
                "response_too_large",
                "response body exceeds the size limit",
            )
        actual_sha256 = _sha256(response.body)
        if (
            not isinstance(response.body_sha256, str)
            or not _HEX_SHA256_RE.fullmatch(response.body_sha256)
            or response.body_sha256 != actual_sha256
        ):
            return self._terminal_failure(
                "response_hash_mismatch",
                "response body does not match its declared sha256",
            )
        self._total_response_bytes += len(response.body)
        if self._total_response_bytes > self._policy.max_total_response_bytes:
            return self._terminal_failure(
                "responses_too_large",
                "session responses exceed the total size limit",
            )

        del self._pending[response.request_id]
        self._completed[response.request_id] = response
        return self._step(response)

    def _step(self, event: ProtocolInput) -> ProtocolAction:
        self._steps += 1
        if self._steps > self._policy.max_steps:
            return self._terminal_failure(
                "step_limit_exceeded",
                "decoder exceeded the protocol step limit",
            )
        try:
            action = self._session.step(event)
        except Exception as error:
            return self._terminal_failure("decoder_failed", type(error).__name__)
        return self._handle_action(action)

    def _handle_action(self, action: object) -> ProtocolAction:
        if isinstance(action, RequestAction):
            if self._pending:
                return self._terminal_failure(
                    "parallel_request_forbidden",
                    "only one request may be pending",
                )
            validation_error = validate_request_action(action, self._policy)
            if validation_error:
                return self._terminal_failure(
                    validation_error.code,
                    validation_error.message,
                )
            if action.request_id in self._completed:
                return self._terminal_failure(
                    "duplicate_request_id",
                    "request_id was already used in this session",
                )
            self._pending[action.request_id] = action
            self._state = "waiting_response"
            return action

        if isinstance(action, NeedContext):
            if not action.keys or len(action.keys) > DEFAULT_MAX_CONTEXT_ITEMS:
                return self._terminal_failure(
                    "invalid_context_request",
                    "decoder requested an invalid number of context keys",
                )
            if len(set(action.keys)) != len(action.keys) or any(
                not isinstance(key, str) or not _CONTEXT_KEY_RE.fullmatch(key)
                for key in action.keys
            ):
                return self._terminal_failure(
                    "invalid_context_request",
                    "decoder requested invalid context keys",
                )
            if not isinstance(action.reason, str) or len(action.reason) > 512:
                return self._terminal_failure(
                    "invalid_context_request",
                    "context request reason is invalid",
                )
            self._state = "need_context"
            return action

        if isinstance(action, AcceptServerResponse):
            response = self._completed.get(action.request_id)
            if response is None:
                return self._terminal_failure(
                    "untracked_accept",
                    "decoder selected an untracked response",
                )
            if (
                not isinstance(action.expected_sha256, str)
                or not _HEX_SHA256_RE.fullmatch(action.expected_sha256)
                or action.expected_sha256 != response.body_sha256
                or action.expected_sha256 != _sha256(response.body)
            ):
                return self._terminal_failure(
                    "accept_hash_mismatch",
                    "selected response does not match the expected sha256",
                )
            self._accepted = AcceptedArtifact(
                request_id=response.request_id,
                source_url=response.url,
                status=response.status,
                body=response.body,
                sha256=response.body_sha256,
            )
            self._state = "accepted"
            return action

        if isinstance(action, Unsupported):
            self._state = "unsupported"
            return action

        if isinstance(action, Failed):
            self._state = "failed"
            return action

        return self._terminal_failure(
            "invalid_decoder_action",
            "decoder returned a value that is not a protocol action",
        )

    def _terminal_failure(self, code: str, message: str) -> Failed:
        self._state = "failed"
        return Failed(code=code, message=message)
