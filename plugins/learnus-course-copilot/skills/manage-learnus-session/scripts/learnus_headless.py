#!/usr/bin/env python3
"""Headless LearnUs authentication with a TTY-only password prompt.

The background process keeps the password and authenticated cookies in memory.
It exposes a small, user-only Unix socket for status and authorized fetches.
"""

from __future__ import annotations

import argparse
import errno
import getpass
import http.cookiejar
import json
import os
import re
import signal
import socket
import socketserver
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


LEARNUS_ORIGIN = "https://ys.learnus.org"
LEARNUS_HOST = "ys.learnus.org"
SSO_HOST = "infra.yonsei.ac.kr"
SSO_START_PATH = "/passni/sso/spLogin2.php"
SSO_SERVICE_PATH = "/sso/PmSSOService"
SSO_AUTH_PATH = "/sso/PmSSOAuthService"
SSO_HANDOFF_PATH = "/passni/sso/spLoginData.php"
SSO_FINALIZE_PATH = "/passni/spLoginProcess.php"
AUTH_CHECK_PATH = "/my/"
COURSE_VIEW_PATH = "/course/view.php"
ACCESS_DENIED_MARKERS = (
    "access denied",
    "access forbidden",
    "접근 권한이 없습니다",
    "접근권한이 없습니다",
    "권한이 없습니다",
)
MAINTENANCE_MARKERS = (
    "service maintenance",
    "temporarily unavailable",
    "서비스 점검 중",
    "서비스 점검중",
    "시스템 점검 중",
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_SECONDS = 30
DEFAULT_HTTP_BODY_LIMIT = 8 * 1024 * 1024
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
MAX_ALLOWED_BYTES = 512 * 1024 * 1024
MAX_REQUEST_LINE = 64 * 1024
SOCKET_TIMEOUT_SECONDS = 180
DEFAULT_SOCKET = Path(tempfile.gettempdir()) / (
    f"yonsei-skills-learnus-{getattr(os, 'getuid', lambda: 0)()}.sock"
)

PLAINTEXT_CREDENTIAL_FIELDS = {
    "loginid",
    "loginpasswd",
    "password",
    "passwd",
    "username",
    "userid",
    "userpw",
}
SSO_HANDOFF_FIELDS = {"E3", "E4", "S2", "CLTID"}


class LearnUsError(RuntimeError):
    """A controlled error that is safe to show without secret-bearing context."""


class AuthenticationFailed(LearnUsError):
    pass


class AdditionalVerificationRequired(AuthenticationFailed):
    pass


class ContractChanged(AuthenticationFailed):
    pass


class AuthorizationBoundaryError(LearnUsError):
    pass


class DaemonNotRunning(LearnUsError):
    pass


class ProtocolError(LearnUsError):
    pass


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    content_type: str
    effective_url: str
    status_code: int


@dataclass(frozen=True)
class ParsedInput:
    name: str
    value: str
    input_type: str


@dataclass
class ParsedForm:
    name: str
    action: str
    method: str
    inputs: list[ParsedInput]


class AuthHTMLParser(HTMLParser):
    """Capture only the small HTML surface needed by the SSO contract."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[ParsedForm] = []
        self.current_form: ParsedForm | None = None
        self.all_inputs: list[ParsedInput] = []
        self.body_classes: set[str] = set()
        self.has_password_input = False
        self.has_logout_link = False
        self.has_usermenu = False
        self.text_parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self.ignored_depth += 1
            return
        if lowered == "body":
            self.body_classes.update(values.get("class", "").lower().split())
        if values.get("data-region", "").lower() == "usermenu":
            self.has_usermenu = True
        if lowered == "a" and "/login/logout.php" in values.get("href", ""):
            self.has_logout_link = True
        if lowered == "form":
            form = ParsedForm(
                name=values.get("name", ""),
                action=values.get("action", ""),
                method=values.get("method", "get").lower(),
                inputs=[],
            )
            self.forms.append(form)
            self.current_form = form
            return
        if lowered != "input":
            return
        parsed_input = ParsedInput(
            name=values.get("name", ""),
            value=values.get("value", ""),
            input_type=values.get("type", "text").lower(),
        )
        self.all_inputs.append(parsed_input)
        if self.current_form is not None:
            self.current_form.inputs.append(parsed_input)
        if parsed_input.input_type == "password":
            self.has_password_input = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            if self.ignored_depth:
                self.ignored_depth -= 1
            return
        if lowered == "form":
            self.current_form = None

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.text_parts.append(cleaned)

    @property
    def visible_text(self) -> str:
        return " ".join(self.text_parts)


def parse_auth_html(html: str) -> AuthHTMLParser:
    parser = AuthHTMLParser()
    parser.feed(html)
    parser.close()
    return parser


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def validate_https_destination(url: str, *, allowed_hosts: set[str] | frozenset[str]) -> str:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as error:
        raise AuthorizationBoundaryError("The request URL contains an invalid port.") from error
    hostname = (parts.hostname or "").lower()
    if (
        parts.scheme.lower() != "https"
        or hostname not in {host.lower() for host in allowed_hosts}
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
    ):
        raise AuthorizationBoundaryError(
            "The request or redirect crossed the approved HTTPS service boundary."
        )
    return urlunsplit(("https", parts.netloc, parts.path or "/", parts.query, ""))


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str] | frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        validate_https_destination(newurl, allowed_hosts=self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpResponse:
    def __init__(self, raw: Any, *, max_bytes: int) -> None:
        self.url = raw.geturl()
        self.status_code = int(getattr(raw, "status", raw.getcode()))
        self.headers = raw.headers
        try:
            self.content = raw.read(max_bytes + 1)
        finally:
            raw.close()
        if len(self.content) > max_bytes:
            raise AuthorizationBoundaryError(
                "The HTTP response exceeds the configured transfer limit."
            )
        charset = (
            self.headers.get_content_charset()
            if hasattr(self.headers, "get_content_charset")
            else None
        )
        self.text = self.content.decode(charset or "utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise urllib.error.HTTPError(
                self.url,
                self.status_code,
                "HTTP request failed",
                self.headers,
                None,
            )


class HttpSession:
    """A small requests-like session implemented with Python's standard library."""

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.headers: dict[str, str] = {}
        self.allowed_hosts = frozenset(
            host.lower()
            for host in (allowed_hosts or {LEARNUS_HOST, SSO_HOST})
        )
        self.cookies = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(self.cookies)
        self.opener = urllib.request.build_opener(
            cookie_handler,
            SafeRedirectHandler(self.allowed_hosts),
        )
        self.no_redirect_opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            NoRedirectHandler(),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = HTTP_TIMEOUT_SECONDS,
        allow_redirects: bool = True,
        max_bytes: int = DEFAULT_HTTP_BODY_LIMIT,
    ) -> HttpResponse:
        url = validate_https_destination(url, allowed_hosts=self.allowed_hosts)
        merged_headers = {**self.headers, **(headers or {})}
        encoded = None
        if data is not None:
            encoded = urlencode(data).encode("utf-8")
            merged_headers.setdefault(
                "Content-Type",
                "application/x-www-form-urlencoded",
            )
        request = urllib.request.Request(
            url,
            data=encoded,
            headers=merged_headers,
            method=method.upper(),
        )
        opener = self.opener if allow_redirects else self.no_redirect_opener
        try:
            raw = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            raw = error
        return HttpResponse(raw, max_bytes=max_bytes)

    def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self.cookies.clear()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def validate_learnus_url(url: str, *, origin: str = LEARNUS_ORIGIN) -> str:
    parts = urlsplit(url)
    origin_parts = urlsplit(origin)
    try:
        port = parts.port
    except ValueError as error:
        raise AuthorizationBoundaryError("The LearnUs URL contains an invalid port.") from error
    if (
        parts.scheme != "https"
        or parts.hostname != origin_parts.hostname
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
    ):
        raise AuthorizationBoundaryError(
            "Only HTTPS URLs on ys.learnus.org are allowed."
        )
    if parts.path == AUTH_CHECK_PATH:
        if parts.query:
            raise AuthorizationBoundaryError(
                "The LearnUs dashboard fetch does not accept query parameters."
            )
    elif parts.path == COURSE_VIEW_PATH:
        query = parse_qsl(parts.query, keep_blank_values=True)
        if (
            len(query) != 1
            or query[0][0] != "id"
            or not query[0][1].isdigit()
        ):
            raise AuthorizationBoundaryError(
                "A LearnUs course fetch requires one numeric course id."
            )
    else:
        raise AuthorizationBoundaryError(
            "Only the read-only LearnUs dashboard and course-view paths are allowed."
        )
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def validate_sso_action(
    url: str,
    expected_path: str,
    *,
    sso_host: str = SSO_HOST,
) -> None:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as error:
        raise ContractChanged("Yonsei SSO returned an invalid credential endpoint.") from error
    if (
        parts.scheme != "https"
        or parts.hostname != sso_host
        or port not in (None, 443)
        or parts.path != expected_path
    ):
        raise ContractChanged("Yonsei SSO returned an unexpected credential endpoint.")


def named_input_value(document: AuthHTMLParser, name: str) -> str | None:
    for element in document.all_inputs:
        if element.name == name:
            return element.value
    return None


def safe_inputs_payload(inputs: list[ParsedInput]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for element in inputs:
        name = element.name
        normalized = name.lower()
        if (
            not name
            or normalized in PLAINTEXT_CREDENTIAL_FIELDS
            or element.input_type in {"password", "submit", "button", "image", "file"}
        ):
            continue
        payload[name] = element.value
    return payload


def safe_form_payload(form: ParsedForm) -> dict[str, str]:
    return safe_inputs_payload(form.inputs)


def require_regex(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise ContractChanged(f"Yonsei SSO no longer exposes {label} as expected.")
    return match.group(1)


def extract_rsa_contract(html: str) -> tuple[str, str, str]:
    document = parse_auth_html(html)
    challenge = named_input_value(document, "ssoChallenge")
    if not challenge:
        challenge = require_regex(
            r"var\s+ssoChallenge\s*=\s*['\"]([A-Fa-f0-9]+)['\"]",
            html,
            "the login challenge",
        )
    modulus = named_input_value(document, "keyModulus")
    exponent = named_input_value(document, "keyExponent")
    if not modulus:
        key_match = re.search(
            r"rsa\.setPublic\(\s*['\"]([A-Fa-f0-9]+)['\"]\s*,\s*"
            r"['\"]([A-Fa-f0-9]+)['\"]\s*\)",
            html,
        )
        if key_match is None:
            raise ContractChanged("Yonsei SSO no longer exposes its RSA public key.")
        modulus, exponent = key_match.groups()
    if not exponent:
        exponent = "10001"
    if not all(re.fullmatch(r"[A-Fa-f0-9]+", item) for item in (challenge, modulus, exponent)):
        raise ContractChanged("Yonsei SSO returned a malformed login challenge.")
    return challenge, modulus, exponent


def encrypt_credentials(
    username: str,
    password: str,
    challenge: str,
    modulus_hex: str,
    exponent_hex: str,
) -> str:
    plaintext = json.dumps(
        {
            "userid": username,
            "userpw": password,
            "ssoChallenge": challenge,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        modulus = int(modulus_hex, 16)
        exponent = int(exponent_hex, 16)
    except (TypeError, ValueError) as error:
        raise ContractChanged("Yonsei SSO returned an invalid RSA public key.") from error
    key_size = (modulus.bit_length() + 7) // 8
    if key_size < 128 or key_size > 1024:
        raise ContractChanged("Yonsei SSO returned an unsupported RSA key size.")
    if len(plaintext) > key_size - 11:
        raise AuthenticationFailed("The supplied credentials exceed the SSO request size limit.")
    padding_size = key_size - len(plaintext) - 3
    padding = bytearray()
    while len(padding) < padding_size:
        padding.extend(value for value in os.urandom(padding_size) if value)
    encoded = b"\x00\x02" + bytes(padding[:padding_size]) + b"\x00" + plaintext
    encoded_integer = int.from_bytes(encoded, "big")
    if encoded_integer >= modulus:
        raise ContractChanged("Yonsei SSO returned an invalid RSA modulus.")
    encrypted = pow(encoded_integer, exponent, modulus)
    return encrypted.to_bytes(key_size, "big").hex()


def request_checked(
    session: Any,
    method: str,
    url: str,
    *,
    phase: str,
    allowed_hosts: set[str] | frozenset[str] | None = None,
    **kwargs: Any,
) -> Any:
    approved_hosts = allowed_hosts or {LEARNUS_HOST, SSO_HOST}
    validate_https_destination(url, allowed_hosts=approved_hosts)
    try:
        response = getattr(session, method)(
            url,
            timeout=HTTP_TIMEOUT_SECONDS,
            **kwargs,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LearnUsError(f"{phase} could not reach the service.") from error
    try:
        response.raise_for_status()
    except urllib.error.HTTPError as error:
        status = getattr(response, "status_code", "unknown")
        raise LearnUsError(f"{phase} failed with HTTP status {status}.") from error
    validate_https_destination(str(response.url), allowed_hosts=approved_hosts)
    return response


def has_active_challenge(document: AuthHTMLParser) -> bool:
    captcha = named_input_value(document, "captcha_yn")
    if captcha and captcha.strip().upper() in {"Y", "YES", "1", "TRUE"}:
        return True
    visible_text = document.visible_text.lower()
    markers = (
        "추가 인증",
        "본인 인증",
        "일회용 비밀번호",
        "one-time password",
        "multi-factor",
    )
    return any(marker in visible_text for marker in markers)


def response_is_authenticated(response: Any, *, origin: str = LEARNUS_ORIGIN) -> bool:
    parts = urlsplit(str(response.url))
    origin_parts = urlsplit(origin)
    try:
        port = parts.port
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or parts.hostname != origin_parts.hostname
        or port not in (None, 443)
    ):
        return False
    if parts.path.startswith(("/login/", "/passni/sso/")):
        return False
    document = parse_auth_html(response.text)
    text = document.visible_text.lower()
    if any(marker in text for marker in ACCESS_DENIED_MARKERS + MAINTENANCE_MARKERS):
        return False
    if "notloggedin" in document.body_classes:
        return False
    if "loggedin" in document.body_classes or "logged-in" in document.body_classes:
        return True
    if document.has_logout_link:
        return True
    return document.has_usermenu and not document.has_password_input


def response_requires_login(response: Any, *, origin: str = LEARNUS_ORIGIN) -> bool:
    parts = urlsplit(str(response.url))
    origin_parts = urlsplit(origin)
    if parts.hostname != origin_parts.hostname:
        return True
    if parts.path.startswith(("/login/", "/passni/sso/", SSO_FINALIZE_PATH)):
        return True
    if getattr(response, "status_code", 200) == 401:
        return True
    content_type = str(response.headers.get("Content-Type", "")).lower()
    if "html" not in content_type and not response.content.lstrip().startswith(b"<"):
        return False
    document = parse_auth_html(response.text)
    if document.has_password_input:
        return True
    if "notloggedin" in document.body_classes:
        return True
    text = document.visible_text.lower()
    return "portal login" in text or "external login" in text


def response_content_problem(response: Any) -> str | None:
    content_type = str(response.headers.get("Content-Type", "")).lower()
    if "html" not in content_type and not response.content.lstrip().startswith(b"<"):
        return None
    text = parse_auth_html(response.text).visible_text.lower()
    if any(marker in text for marker in ACCESS_DENIED_MARKERS):
        return "access_denied"
    if any(marker in text for marker in MAINTENANCE_MARKERS):
        return "maintenance"
    return None


class LearnUsClient:
    """Own an authenticated requests session and reauthenticate once on expiry."""

    def __init__(
        self,
        username: str,
        password: bytearray,
        *,
        session_factory: Callable[[], Any] | None = None,
        origin: str = LEARNUS_ORIGIN,
        sso_host: str = SSO_HOST,
    ) -> None:
        if not username.strip() or len(username) > 256 or any(ch in username for ch in "\r\n"):
            raise AuthenticationFailed("A valid Yonsei username is required.")
        if not password or len(password) > 4096:
            raise AuthenticationFailed("A non-empty password is required.")
        self.username = username
        self.password = password
        self.origin = origin.rstrip("/")
        self.sso_host = sso_host
        self.allowed_hosts = frozenset(
            {
                (urlsplit(self.origin).hostname or "").lower(),
                self.sso_host.lower(),
            }
        )
        self.session_factory = session_factory or (
            lambda: HttpSession(allowed_hosts=self.allowed_hosts)
        )
        self.session: Any | None = None
        self.lock = threading.RLock()
        self.auth_generation = 0
        self.reauth_count = 0
        self.last_authenticated_at: str | None = None
        self.last_error: str | None = None

    def _new_session(self) -> Any:
        session = self.session_factory()
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            }
        )
        return session

    def _password_text(self) -> str:
        try:
            return self.password.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AuthenticationFailed("The password could not be encoded for SSO.") from error

    def authenticate(self) -> None:
        with self.lock:
            previous_generation = self.auth_generation
            candidate = self._new_session()
            try:
                self._authenticate_session(candidate)
            except LearnUsError as error:
                candidate.close()
                self.last_error = str(error)
                raise
            old_session = self.session
            self.session = candidate
            if old_session is not None:
                old_session.close()
            self.auth_generation += 1
            if previous_generation:
                self.reauth_count += 1
            self.last_authenticated_at = utc_now()
            self.last_error = None

    def _authenticate_session(self, session: Any) -> None:
        start = request_checked(
            session,
            "get",
            f"{self.origin}{SSO_START_PATH}",
            phase="LearnUs SSO start",
            allowed_hosts=self.allowed_hosts,
            headers={"Referer": f"{self.origin}/"},
            allow_redirects=True,
        )
        start_document = parse_auth_html(start.text)
        start_form = next(
            (form for form in start_document.forms if form.name == "frmSSO"),
            None,
        )
        if start_form is None:
            raise ContractChanged("LearnUs did not return the expected SSO start form.")
        challenge_url = urljoin(str(start.url), start_form.action)
        validate_sso_action(
            challenge_url,
            SSO_SERVICE_PATH,
            sso_host=self.sso_host,
        )

        challenge_response = request_checked(
            session,
            "post",
            challenge_url,
            phase="Yonsei SSO challenge",
            allowed_hosts=self.allowed_hosts,
            data=safe_form_payload(start_form),
            headers={"Referer": f"{self.origin}/"},
            allow_redirects=True,
        )
        challenge_document = parse_auth_html(challenge_response.text)
        login_form = next(
            (form for form in challenge_document.forms if form.name == "ssoLoginForm"),
            None,
        )
        if login_form is None:
            raise ContractChanged("Yonsei SSO did not return the expected login form.")
        auth_url = urljoin(str(challenge_response.url), login_form.action)
        validate_sso_action(
            auth_url,
            SSO_AUTH_PATH,
            sso_host=self.sso_host,
        )
        challenge, modulus, exponent = extract_rsa_contract(challenge_response.text)
        encrypted = encrypt_credentials(
            self.username,
            self._password_text(),
            challenge,
            modulus,
            exponent,
        )
        auth_payload = safe_form_payload(login_form)
        auth_payload["E2"] = encrypted

        auth_response = request_checked(
            session,
            "post",
            auth_url,
            phase="Yonsei SSO authentication",
            allowed_hosts=self.allowed_hosts,
            data=auth_payload,
            headers={"Referer": str(challenge_response.url)},
            allow_redirects=False,
        )
        auth_document = parse_auth_html(auth_response.text)
        handoff_payload: dict[str, str] | None = None
        for form in auth_document.forms:
            values = safe_form_payload(form)
            if SSO_HANDOFF_FIELDS.issubset(values):
                handoff_payload = values
                break
        if handoff_payload is None:
            document_payload = safe_inputs_payload(auth_document.all_inputs)
            if SSO_HANDOFF_FIELDS.issubset(document_payload):
                handoff_payload = document_payload
        if handoff_payload is None:
            if has_active_challenge(auth_document):
                raise AdditionalVerificationRequired(
                    "Yonsei SSO requires CAPTCHA, MFA, or another interactive verification."
                )
            if (
                any(form.name == "ssoLoginForm" for form in auth_document.forms)
                or auth_document.has_password_input
            ):
                raise AuthenticationFailed(
                    "Yonsei SSO rejected the credentials or requested interactive verification."
                )
            raise ContractChanged("Yonsei SSO did not return the expected login handoff.")

        if not SSO_HANDOFF_FIELDS.issubset(handoff_payload):
            raise ContractChanged("Yonsei SSO returned an incomplete login handoff.")
        request_checked(
            session,
            "post",
            f"{self.origin}{SSO_HANDOFF_PATH}",
            phase="LearnUs SSO handoff",
            allowed_hosts=self.allowed_hosts,
            data=handoff_payload,
            headers={"Referer": str(auth_response.url)},
            allow_redirects=False,
        )
        request_checked(
            session,
            "get",
            f"{self.origin}{SSO_FINALIZE_PATH}",
            phase="LearnUs SSO finalization",
            allowed_hosts=self.allowed_hosts,
            headers={"Referer": f"{self.origin}/"},
            allow_redirects=True,
        )
        auth_check = request_checked(
            session,
            "get",
            f"{self.origin}{AUTH_CHECK_PATH}",
            phase="LearnUs authentication check",
            allowed_hosts=self.allowed_hosts,
            headers={"Referer": f"{self.origin}/"},
            allow_redirects=True,
        )
        if not response_is_authenticated(auth_check, origin=self.origin):
            raise AuthenticationFailed("LearnUs did not establish an authenticated session.")

    def fetch(self, url: str, *, max_bytes: int = DEFAULT_MAX_BYTES) -> FetchResult:
        target = validate_learnus_url(url, origin=self.origin)
        if max_bytes < 1 or max_bytes > MAX_ALLOWED_BYTES:
            raise AuthorizationBoundaryError("The requested byte limit is outside the safe range.")
        with self.lock:
            if self.session is None:
                self.authenticate()
            response = request_checked(
                self.session,
                "get",
                target,
                phase="LearnUs fetch",
                allowed_hosts=self.allowed_hosts,
                allow_redirects=True,
                max_bytes=max_bytes,
            )
            if response_requires_login(response, origin=self.origin):
                self.authenticate()
                response = request_checked(
                    self.session,
                    "get",
                    target,
                    phase="LearnUs fetch after reauthentication",
                    allowed_hosts=self.allowed_hosts,
                    allow_redirects=True,
                    max_bytes=max_bytes,
                )
                if response_requires_login(response, origin=self.origin):
                    raise AuthenticationFailed(
                        "LearnUs still requires login after automatic reauthentication."
                    )
            validate_learnus_url(str(response.url), origin=self.origin)
            problem = response_content_problem(response)
            if problem == "access_denied":
                raise AuthorizationBoundaryError(
                    "LearnUs denied access to the requested page."
                )
            if problem == "maintenance":
                raise LearnUsError(
                    "LearnUs returned a service-maintenance page instead of course content."
                )
            body = bytes(response.content)
            if len(body) > max_bytes:
                raise AuthorizationBoundaryError(
                    "The resource exceeds the configured transfer limit."
                )
            content_type = str(response.headers.get("Content-Type", "application/octet-stream"))
            content_type = content_type.replace("\r", "").replace("\n", "")[:200]
            return FetchResult(
                body=body,
                content_type=content_type,
                effective_url=redact_url(str(response.url)),
                status_code=int(response.status_code),
            )

    def status(self) -> dict[str, Any]:
        with self.lock:
            if self.last_error:
                authentication_state = "error"
            elif self.session is not None:
                authentication_state = "last-known-authenticated"
            else:
                authentication_state = "not-established"
            return {
                "running": True,
                "session_established": self.session is not None,
                "authentication_state": authentication_state,
                "remote_check_performed": False,
                "automatic_reauthentication_ready": bool(self.password),
                "auth_generation": self.auth_generation,
                "reauth_count": self.reauth_count,
                "last_authenticated_at": self.last_authenticated_at,
                "last_error": self.last_error,
            }

    def close(self) -> None:
        with self.lock:
            if self.session is not None:
                self.session.close()
                self.session = None
            for index in range(len(self.password)):
                self.password[index] = 0


class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        socket_path: Path,
        handler: type[socketserver.StreamRequestHandler],
        client: LearnUsClient,
    ) -> None:
        self.client = client
        self.socket_path = socket_path
        super().__init__(str(socket_path), handler)


def send_json_line(stream: Any, payload: dict[str, Any]) -> None:
    stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            line = self.rfile.readline(MAX_REQUEST_LINE + 1)
            if len(line) > MAX_REQUEST_LINE:
                raise ProtocolError("Request is too large.")
            request = json.loads(line.decode("utf-8"))
            if not isinstance(request, dict):
                raise ProtocolError("Request must be a JSON object.")
            operation = request.get("op")
            server: ThreadedUnixServer = self.server  # type: ignore[assignment]
            if operation == "status":
                send_json_line(self.wfile, {"ok": True, **server.client.status()})
                return
            if operation == "fetch":
                url = request.get("url")
                max_bytes = request.get("max_bytes", DEFAULT_MAX_BYTES)
                if not isinstance(url, str) or not isinstance(max_bytes, int):
                    raise ProtocolError("Fetch requires a URL and integer byte limit.")
                result = server.client.fetch(url, max_bytes=max_bytes)
                send_json_line(
                    self.wfile,
                    {
                        "ok": True,
                        "bytes": len(result.body),
                        "content_type": result.content_type,
                        "effective_url": result.effective_url,
                        "status_code": result.status_code,
                    },
                )
                self.wfile.write(result.body)
                self.wfile.flush()
                return
            if operation == "stop":
                send_json_line(self.wfile, {"ok": True, "stopping": True})
                threading.Thread(target=server.shutdown, daemon=True).start()
                return
            raise ProtocolError("Unsupported operation.")
        except (LearnUsError, json.JSONDecodeError, UnicodeDecodeError) as error:
            kind = "protocol" if isinstance(error, (ProtocolError, json.JSONDecodeError)) else "runtime"
            send_json_line(
                self.wfile,
                {"ok": False, "kind": kind, "error": str(error)},
            )


def assert_socket_path_available(socket_path: Path) -> None:
    if len(os.fsencode(socket_path)) >= 100:
        raise LearnUsError("Unix socket path is too long.")
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not os.path.lexists(socket_path):
        return
    metadata = os.lstat(socket_path)
    if not stat.S_ISSOCK(metadata.st_mode):
        raise LearnUsError("Refusing to replace a non-socket filesystem entry.")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise LearnUsError("Refusing to replace a socket owned by another user.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            connection.connect(str(socket_path))
    except OSError as error:
        if error.errno in {errno.ECONNREFUSED, errno.ENOENT}:
            socket_path.unlink()
            return
        raise LearnUsError(
            "Could not prove that the existing LearnUs socket is stale."
        ) from error
    try:
        reply, _ = socket_rpc(socket_path, {"op": "status"}, timeout=1)
    except LearnUsError as error:
        raise LearnUsError(
            "An active but unrecognized process is using the LearnUs socket."
        ) from error
    if reply.get("ok"):
        raise LearnUsError("LearnUs headless service is already running.")
    raise LearnUsError("An unrecognized process is using the LearnUs socket.")


def create_server(socket_path: Path, client: LearnUsClient) -> ThreadedUnixServer:
    assert_socket_path_available(socket_path)
    previous_umask = os.umask(0o077)
    try:
        server = ThreadedUnixServer(socket_path, RequestHandler, client)
    finally:
        os.umask(previous_umask)
    os.chmod(socket_path, 0o600)
    return server


def read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(min(remaining, 1024 * 1024))
        if not chunk:
            raise ProtocolError("The local service ended the response early.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def socket_rpc(
    socket_path: Path,
    request: dict[str, Any],
    *,
    timeout: float = SOCKET_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], bytes]:
    if not os.path.lexists(socket_path):
        raise DaemonNotRunning("LearnUs headless service is not running.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(str(socket_path))
            connection.sendall(
                (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
            )
            stream = connection.makefile("rb")
            line = stream.readline(MAX_REQUEST_LINE + 1)
            if not line or len(line) > MAX_REQUEST_LINE:
                raise ProtocolError("The local service returned an invalid response.")
            header = json.loads(line.decode("utf-8"))
            if not isinstance(header, dict):
                raise ProtocolError("The local service returned invalid metadata.")
            if not header.get("ok"):
                raise LearnUsError(str(header.get("error") or "Local service request failed."))
            size = header.get("bytes", 0)
            if not isinstance(size, int) or size < 0 or size > MAX_ALLOWED_BYTES:
                raise ProtocolError("The local service returned an invalid byte count.")
            return header, read_exact(stream, size) if size else b""
    except (ConnectionError, OSError, socket.timeout) as error:
        raise DaemonNotRunning("LearnUs headless service is not reachable.") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProtocolError("The local service returned malformed metadata.") from error


def cleanup_socket(socket_path: Path) -> None:
    if not os.path.lexists(socket_path):
        return
    metadata = os.lstat(socket_path)
    if stat.S_ISSOCK(metadata.st_mode) and (
        not hasattr(os, "getuid") or metadata.st_uid == os.getuid()
    ):
        socket_path.unlink()


def disable_core_dumps() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, OSError, ValueError):
        pass


def serve(server: ThreadedUnixServer) -> None:
    def request_shutdown(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        cleanup_socket(server.socket_path)
        server.client.close()


def daemonize(server: ThreadedUnixServer) -> int:
    if not hasattr(os, "fork"):
        raise LearnUsError("Background mode requires a Unix-like operating system.")
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid:
        os.close(write_fd)
        ready = os.read(read_fd, 1)
        os.close(read_fd)
        server.server_close()
        server.client.close()
        if ready != b"1":
            raise LearnUsError("LearnUs headless service failed to start.")
        return pid

    try:
        os.close(read_fd)
        os.setsid()
        with open(os.devnull, "rb", buffering=0) as null_in, open(
            os.devnull, "ab", buffering=0
        ) as null_out:
            os.dup2(null_in.fileno(), 0)
            os.dup2(null_out.fileno(), 1)
            os.dup2(null_out.fileno(), 2)
        os.write(write_fd, b"1")
        os.close(write_fd)
        serve(server)
    except BaseException:
        try:
            os.close(write_fd)
        except OSError:
            pass
        os._exit(1)
    os._exit(0)


def prompt_password() -> bytearray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password_text = getpass.getpass("Yonsei password (hidden): ")
    except (EOFError, getpass.GetPassWarning) as error:
        raise AuthenticationFailed(
            "Run start from an interactive terminal; password input must not be echoed."
        ) from error
    if not password_text:
        raise AuthenticationFailed("A non-empty password is required.")
    password = bytearray(password_text, "utf-8")
    password_text = ""
    return password


def secure_write(path: Path, body: bytes, *, force: bool) -> None:
    destination = path.expanduser().absolute()
    if not destination.parent.is_dir():
        raise LearnUsError("Output directory does not exist.")
    if os.path.lexists(destination) and not force:
        raise LearnUsError("Output already exists; pass --force to replace it.")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        os.chmod(destination, 0o600)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def print_json(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Password-prompted, headless LearnUs session service."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser(
        "start",
        help="Prompt for the password and start the memory-only session service.",
    )
    start.add_argument("--username", required=True, help="Yonsei login ID.")
    start.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    start.add_argument(
        "--foreground",
        action="store_true",
        help="Keep the service in the current terminal instead of detaching.",
    )

    status = subparsers.add_parser("status", help="Check the local session service.")
    status.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)

    fetch = subparsers.add_parser(
        "fetch",
        help="Fetch an authorized LearnUs URL through the local service.",
    )
    fetch.add_argument("--url", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    fetch.add_argument("--force", action="store_true")
    fetch.add_argument(
        "--max-mib",
        type=int,
        default=DEFAULT_MAX_BYTES // (1024 * 1024),
        help="Maximum response size in MiB (default: 64, maximum: 512).",
    )

    stop = subparsers.add_parser("stop", help="Stop the service and forget the password.")
    stop.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)

    subparsers.add_parser("self-test", help="Run deterministic tests without real credentials.")
    return parser


def run_start(args: argparse.Namespace) -> int:
    socket_path = args.socket.expanduser().absolute()
    if os.path.lexists(socket_path):
        try:
            reply, _ = socket_rpc(socket_path, {"op": "status"}, timeout=1)
        except LearnUsError:
            pass
        else:
            print_json({"ok": True, "already_running": True, **reply})
            return 0
    password = prompt_password()
    client = LearnUsClient(args.username, password)
    try:
        client.authenticate()
        server = create_server(socket_path, client)
    except BaseException:
        client.close()
        raise
    if args.foreground:
        print_json(
            {
                "ok": True,
                "running": True,
                "foreground": True,
                "socket": str(socket_path),
            }
        )
        serve(server)
        return 0
    pid = daemonize(server)
    print_json(
        {
            "ok": True,
            "running": True,
            "pid": pid,
            "socket": str(socket_path),
            "password_storage": "memory-only",
        }
    )
    return 0


def run_status(args: argparse.Namespace) -> int:
    reply, _ = socket_rpc(args.socket.expanduser().absolute(), {"op": "status"})
    print_json(reply)
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    if args.max_mib < 1 or args.max_mib > MAX_ALLOWED_BYTES // (1024 * 1024):
        raise AuthorizationBoundaryError("--max-mib must be between 1 and 512.")
    header, body = socket_rpc(
        args.socket.expanduser().absolute(),
        {
            "op": "fetch",
            "url": args.url,
            "max_bytes": args.max_mib * 1024 * 1024,
        },
    )
    secure_write(args.output, body, force=args.force)
    print_json(
        {
            "ok": True,
            "output": str(args.output.expanduser().absolute()),
            "bytes": header["bytes"],
            "content_type": header["content_type"],
            "effective_url": header["effective_url"],
            "status_code": header["status_code"],
        }
    )
    return 0


def run_stop(args: argparse.Namespace) -> int:
    reply, _ = socket_rpc(args.socket.expanduser().absolute(), {"op": "stop"})
    print_json(reply)
    return 0


def run_self_test() -> int:
    checks = 0
    modulus = (
        "d13c970b54bf764ab6e8d87f323188ba82d80d46baba174370714565af9a8d1b"
        "d68b61c6e97c03d2d324ff4136d9c12b034badd7c3873ce7be6280710f51cb196"
        "3fe00b4a74589cbdb4a95bcef9beec16684d2a523db4a5830055e1d155b6aaf09"
        "a2aa78bed40379834d81c5aaea4e0e82c270fc049e0df59bafc597b03e919f"
    )
    exponent = "10001"
    private_exponent = int(
        (
            "2c632d2bd333b6d58cce02b7a11f4f013a26b9524ae49570d216c58117eab28a"
            "b84de3553e4cf7c6aed247703f419cb01247e8be40159d7f102d775004cef645af"
            "4ec54ce7a2707cc7b3da9674915237f4ad5f53bc9d31b9dab999fccf0a6cd19e8"
            "6012497ba66f17d6a81e188bed8963d43fd09dbbefd2b2ceda3318c8f9af1"
        ),
        16,
    )
    modulus_integer = int(modulus, 16)
    challenge = "a1b2c3d4"
    expected_username = "test-user"
    expected_password = "test-password"

    def decrypt_fixture(ciphertext_hex: str) -> bytes:
        key_size = (modulus_integer.bit_length() + 7) // 8
        encoded = pow(
            int(ciphertext_hex, 16),
            private_exponent,
            modulus_integer,
        ).to_bytes(key_size, "big")
        assert encoded.startswith(b"\x00\x02")
        separator = encoded.find(b"\x00", 2)
        assert separator >= 10
        return encoded[separator + 1 :]

    class FakeResponse:
        def __init__(
            self,
            url: str,
            body: str | bytes,
            *,
            status: int = 200,
            content_type: str = "text/html; charset=utf-8",
        ) -> None:
            self.url = url
            self.status_code = status
            self.headers = {"Content-Type": content_type}
            self.content = body.encode("utf-8") if isinstance(body, str) else body
            self.text = self.content.decode("utf-8", errors="replace")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise urllib.error.HTTPError(
                    self.url,
                    self.status_code,
                    "test error",
                    self.headers,
                    None,
                )

    class FakeFactory:
        def __init__(self) -> None:
            self.sessions = 0
            self.expired_once = False

        def __call__(self) -> Any:
            index = self.sessions
            self.sessions += 1
            factory = self

            class FakeSession:
                def __init__(self) -> None:
                    self.headers: dict[str, str] = {}
                    self.authenticated = False
                    self.closed = False

                def get(self, url: str, **_kwargs: Any) -> FakeResponse:
                    path = urlsplit(url).path
                    if path == SSO_START_PATH:
                        return FakeResponse(
                            url,
                            (
                                f"<form name='frmSSO' action='https://{SSO_HOST}{SSO_SERVICE_PATH}'>"
                                "<input type='hidden' name='app_id' value='ednetYonsei'>"
                                "</form>"
                            ),
                        )
                    if path == SSO_FINALIZE_PATH:
                        self.authenticated = True
                        return FakeResponse(url, "<body class='loggedin'></body>")
                    if path == AUTH_CHECK_PATH:
                        body = (
                            "<body class='loggedin'><a href='/login/logout.php'>Logout</a></body>"
                            if self.authenticated
                            else "<body class='notloggedin'><input type='password'></body>"
                        )
                        return FakeResponse(url, body)
                    if path == "/course/view.php":
                        if index == 0 and not factory.expired_once:
                            factory.expired_once = True
                            self.authenticated = False
                            return FakeResponse(
                                f"{LEARNUS_ORIGIN}/login/index.php",
                                "<body class='notloggedin'><input type='password'></body>",
                            )
                        return FakeResponse(
                            url,
                            "<body class='loggedin'><h1>Systems</h1></body>",
                        )
                    raise AssertionError(f"unexpected GET path: {path}")

                def post(self, url: str, data: dict[str, str], **_kwargs: Any) -> FakeResponse:
                    path = urlsplit(url).path
                    if path == SSO_SERVICE_PATH and "E2" not in data:
                        return FakeResponse(
                            url,
                            (
                                f"<script>var ssoChallenge='{challenge}';"
                                f"rsa.setPublic('{modulus}','{exponent}');</script>"
                                f"<form name='ssoLoginForm' action='https://{SSO_HOST}{SSO_AUTH_PATH}'>"
                                "<input type='hidden' name='E2' value=''>"
                                "<input type='hidden' name='captcha_yn' value='N'>"
                                "</form>"
                            ),
                        )
                    if path == SSO_AUTH_PATH and "E2" in data:
                        decrypted = decrypt_fixture(data["E2"])
                        supplied = json.loads(decrypted.decode("utf-8"))
                        if supplied != {
                            "userid": expected_username,
                            "userpw": expected_password,
                            "ssoChallenge": challenge,
                        }:
                            return FakeResponse(
                                url,
                                (
                                    "<form name='ssoLoginForm'>"
                                    "<input type='password' name='loginPasswd'>"
                                    "</form>"
                                ),
                            )
                        return FakeResponse(
                            url,
                            (
                                f"<form action='{LEARNUS_ORIGIN}{SSO_HANDOFF_PATH}'>"
                                "<input type='hidden' name='E3' value='three'>"
                                "<input type='hidden' name='E4' value='four'>"
                                "<input type='hidden' name='S2' value='two'>"
                                "<input type='hidden' name='CLTID' value='client'>"
                                "</form>"
                            ),
                        )
                    if path == SSO_HANDOFF_PATH:
                        assert SSO_HANDOFF_FIELDS.issubset(data)
                        assert not (set(name.lower() for name in data) & PLAINTEXT_CREDENTIAL_FIELDS)
                        return FakeResponse(url, "<body>handoff accepted</body>")
                    raise AssertionError(f"unexpected POST path: {path}")

                def close(self) -> None:
                    self.closed = True

            return FakeSession()

    encrypted = encrypt_credentials(
        expected_username,
        expected_password,
        challenge,
        modulus,
        exponent,
    )
    decrypted = decrypt_fixture(encrypted)
    assert json.loads(decrypted.decode("utf-8"))["userpw"] == expected_password
    checks += 1

    try:
        validate_learnus_url("https://attacker.example/steal")
    except AuthorizationBoundaryError:
        checks += 1
    else:
        raise AssertionError("off-origin URL was accepted")

    for unsafe_url in (
        "http://ys.learnus.org/course/view.php?id=7",
        "https://ys.learnus.org:444/course/view.php?id=7",
        "https://user:pass@ys.learnus.org/course/view.php?id=7",
        "https://ys.learnus.org/login/logout.php?sesskey=secret",
        "https://ys.learnus.org/mod/assign/view.php?id=7",
        "https://ys.learnus.org/course/view.php?id=7&action=delete",
        "https://ys.learnus.org/my/?redirect=1",
    ):
        try:
            validate_learnus_url(unsafe_url)
        except AuthorizationBoundaryError:
            checks += 1
        else:
            raise AssertionError(f"unsafe LearnUs URL was accepted: {unsafe_url}")

    redirect_handler = SafeRedirectHandler({LEARNUS_HOST, SSO_HOST})
    try:
        redirect_handler.redirect_request(
            urllib.request.Request(f"{LEARNUS_ORIGIN}/my/"),
            None,
            302,
            "Found",
            {},
            "https://attacker.example/steal",
        )
    except AuthorizationBoundaryError:
        checks += 1
    else:
        raise AssertionError("external redirect was accepted")

    access_denied = FakeResponse(
        f"{LEARNUS_ORIGIN}/course/view.php?id=7",
        "<body class='loggedin'><a href='/login/logout.php'>Logout</a>Access denied</body>",
    )
    assert response_is_authenticated(access_denied) is False
    assert response_content_problem(access_denied) == "access_denied"
    checks += 2
    maintenance = FakeResponse(
        f"{LEARNUS_ORIGIN}/course/view.php?id=7",
        "<body class='loggedin'><div data-region='usermenu'>User</div>서비스 점검 중</body>",
    )
    assert response_is_authenticated(maintenance) is False
    assert response_content_problem(maintenance) == "maintenance"
    checks += 2

    class StaticSession:
        def __init__(self, response: FakeResponse) -> None:
            self.response = response
            self.headers: dict[str, str] = {}

        def get(self, _url: str, **_kwargs: Any) -> FakeResponse:
            return self.response

        def close(self) -> None:
            return None

    for response, expected_error in (
        (access_denied, AuthorizationBoundaryError),
        (maintenance, LearnUsError),
        (
            FakeResponse(
                "https://attacker.example/landing",
                "<body class='loggedin'>Unexpected redirect</body>",
            ),
            AuthorizationBoundaryError,
        ),
    ):
        static_client = LearnUsClient(
            expected_username,
            bytearray(expected_password, "utf-8"),
            session_factory=lambda response=response: StaticSession(response),
        )
        static_client.session = StaticSession(response)
        try:
            static_client.fetch(f"{LEARNUS_ORIGIN}/course/view.php?id=7")
        except expected_error:
            checks += 1
        else:
            raise AssertionError("unsafe LearnUs fetch content was accepted")
        finally:
            static_client.close()

    factory = FakeFactory()
    client = LearnUsClient(
        expected_username,
        bytearray(expected_password, "utf-8"),
        session_factory=factory,
    )
    client.authenticate()
    assert client.auth_generation == 1
    checks += 1
    fetched = client.fetch(f"{LEARNUS_ORIGIN}/course/view.php?id=7")
    assert b"Systems" in fetched.body
    assert client.auth_generation == 2 and client.reauth_count == 1
    assert factory.sessions == 2
    checks += 3

    with tempfile.TemporaryDirectory(prefix="learnus-headless-test-") as temporary:
        socket_path = Path(temporary) / "service.sock"
        server = create_server(socket_path, client)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        mode = stat.S_IMODE(os.lstat(socket_path).st_mode)
        assert mode == 0o600
        checks += 1
        status_reply, _ = socket_rpc(socket_path, {"op": "status"})
        assert status_reply["session_established"] is True
        assert status_reply["authentication_state"] == "last-known-authenticated"
        assert status_reply["remote_check_performed"] is False
        assert status_reply["automatic_reauthentication_ready"] is True
        checks += 1
        fetch_reply, fetch_body = socket_rpc(
            socket_path,
            {
                "op": "fetch",
                "url": f"{LEARNUS_ORIGIN}/course/view.php?id=7",
                "max_bytes": DEFAULT_MAX_BYTES,
            },
        )
        assert fetch_reply["bytes"] == len(fetch_body) and b"Systems" in fetch_body
        checks += 1
        stop_reply, _ = socket_rpc(socket_path, {"op": "stop"})
        assert stop_reply["stopping"] is True
        thread.join(timeout=5)
        assert not thread.is_alive()
        server.server_close()
        cleanup_socket(socket_path)
        client.close()
        assert not any(client.password)
        checks += 2

    daemon_factory = FakeFactory()
    daemon_factory.expired_once = True
    daemon_client = LearnUsClient(
        expected_username,
        bytearray(expected_password, "utf-8"),
        session_factory=daemon_factory,
    )
    daemon_client.authenticate()
    with tempfile.TemporaryDirectory(prefix="learnus-headless-daemon-test-") as temporary:
        socket_path = Path(temporary) / "daemon.sock"
        daemon_server = create_server(socket_path, daemon_client)
        daemon_pid = daemonize(daemon_server)
        daemon_status, _ = socket_rpc(socket_path, {"op": "status"})
        assert daemon_status["session_established"] is True
        assert daemon_status["authentication_state"] == "last-known-authenticated"
        checks += 1
        daemon_stop, _ = socket_rpc(socket_path, {"op": "stop"})
        assert daemon_stop["stopping"] is True
        checks += 1
        deadline = time.monotonic() + 5
        child_status = None
        while time.monotonic() < deadline:
            waited_pid, child_status = os.waitpid(daemon_pid, os.WNOHANG)
            if waited_pid == daemon_pid:
                break
            time.sleep(0.05)
        else:
            os.kill(daemon_pid, signal.SIGTERM)
            os.waitpid(daemon_pid, 0)
            raise AssertionError("detached service did not stop")
        assert os.waitstatus_to_exitcode(child_status) == 0
        assert not os.path.lexists(socket_path)
        checks += 2

    parser = build_parser()
    subparser_action = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    start_parser = subparser_action.choices["start"]
    assert all(action.dest != "password" for action in start_parser._actions)
    checks += 1

    print_json({"passed": True, "checks": checks})
    return 0


def main() -> int:
    disable_core_dumps()
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "start":
            return run_start(args)
        if args.command == "status":
            return run_status(args)
        if args.command == "fetch":
            return run_fetch(args)
        if args.command == "stop":
            return run_stop(args)
        if args.command == "self-test":
            return run_self_test()
        raise ProtocolError("Unsupported command.")
    except KeyboardInterrupt:
        print_json({"ok": False, "error": "Cancelled."}, stream=sys.stderr)
        return 130
    except DaemonNotRunning as error:
        print_json(
            {"ok": False, "running": False, "error": str(error)},
            stream=sys.stderr,
        )
        return 3
    except LearnUsError as error:
        print_json({"ok": False, "error": str(error)}, stream=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
