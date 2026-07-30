#!/usr/bin/env python3
"""Loopback ReportX compatibility agent for macOS and Linux.

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


def build_yonsei_font_map(
    title_font: Path | None,
    body_font: Path | None,
) -> dict[str, Path]:
    """Validate the two member-supplied Yonsei faces and map FP3 names."""

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
    coverage_probe = "연세대학교 성적증명서 ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789"
    if not title.supports(coverage_probe) or not body.supports(coverage_probe):
        raise ValueError("Yonsei font lacks required Korean, Latin, or digit glyphs")
    return {
        name.casefold(): title.path
        for name in YONSEI_TITLE_FONT_NAMES
    } | {
        name.casefold(): body.path
        for name in YONSEI_BODY_FONT_NAMES
    }


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
    os.chmod(path, 0o700)


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
                os.chmod(entry, 0o600)


def _atomic_write(path: Path, data: bytes) -> None:
    secure_mkdir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
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
    verification: str = "not_performed"
    print_attempted: bool = False
    printed: bool = False
    print_status: str = "not_requested"
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
            "source": self.source,
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
                "completion_notified": False,
            },
            "verification": self.verification,
            "print": {
                "attempted": self.print_attempted,
                "printed": self.printed,
                "status": self.print_status,
            },
            "messages": self.messages[-20:],
        }


class AgentState:
    def __init__(
        self,
        root: Path,
        *,
        allow_fetch: bool,
        allow_document_reservation: bool = False,
        token: str,
        font_map: dict[str, Path] | None = None,
        require_original_fonts: bool = False,
    ) -> None:
        self.root = root
        self.allow_fetch = allow_fetch
        self.allow_document_reservation = allow_document_reservation
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
        self.lock = threading.RLock()
        self.jobs: dict[str, Job] = {}
        self.events: list[str] = []
        self.pending_jobs = 0
        self.active_tickets: dict[str, str] = {}
        self.submission_times: deque[float] = deque()
        self.protocol_arm_deadline = 0.0
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="reportx-worker",
        )

    def begin_document_reservation(self, job: Job) -> bool:
        """Persist a no-retry reservation guard before the mutating GET."""

        if not job.ticket_sha256:
            return False
        path = self.reservations_dir / f"{job.ticket_sha256}.json"
        payload = json.dumps(
            {
                "schema": "yonsei-reportx-reservation-guard/v1",
                "job_id": job.id,
                "ticket_sha256": job.ticket_sha256,
                "status": "started_unknown_until_response",
                "started_at": utc_now(),
            },
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        try:
            fd = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            # The guard may already be durable.  Keep it fail-closed rather
            # than deleting it and permitting an ambiguous second request.
            raise
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

    def add_job(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.id] = job
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
            self.pending_jobs = max(0, self.pending_jobs - 1)
            if (
                job.ticket_sha256
                and self.active_tickets.get(job.ticket_sha256) == job.id
            ):
                self.active_tickets.pop(job.ticket_sha256, None)

    def write_artifact(self, path: Path, data: bytes) -> bool:
        with self.lock:
            if self._regular_file_bytes(self.out_dir) + len(data) > MAX_OUTPUT_BYTES:
                return False
            secure_write_bytes(path, data)
        return True

    def arm_protocol_once(self) -> int:
        """Authorize one originless official iframe handoff for a short window."""

        with self.lock:
            self.protocol_arm_deadline = (
                time.monotonic() + PROTOCOL_ARM_TTL_SECONDS
            )
        return PROTOCOL_ARM_TTL_SECONDS

    def consume_protocol_arm(self) -> bool:
        with self.lock:
            armed = time.monotonic() <= self.protocol_arm_deadline
            self.protocol_arm_deadline = 0.0
            return armed

    def clear_protocol_arm(self) -> None:
        with self.lock:
            self.protocol_arm_deadline = 0.0

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


def _finish_failure(job: Job, state: AgentState, status: str, code: str) -> None:
    job.status = status
    job.note(code)
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
    except (AssertionError, TypeError, ValueError) as error:
        _finish_failure(job, state, "decode_failed", type(error).__name__)
        return

    job.ticket_length = ticket.raw_length
    job.ticket_sha256 = ticket.raw_sha256
    context = SessionContext.from_mapping(
        "https://icert.yonsei.ac.kr",
        {},
    )
    opened = BundledDecoderRegistry().open(ticket, context)
    if isinstance(opened, Unsupported):
        _finish_failure(job, state, "unsupported_protocol", opened.reason)
        return
    if isinstance(opened, Failed):
        _finish_failure(job, state, "decode_failed", opened.code)
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
        _finish_failure(job, state, "protocol_failed", action.code)
        return
    if not isinstance(action, RequestAction):
        _finish_failure(job, state, "protocol_failed", "request_not_produced")
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
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as error:
        _finish_failure(job, state, "transport_failed", type(error).__name__)
        return
    job.response_length = len(response.body)
    job.response_sha256 = response.body_sha256
    result = broker.receive(response)
    if not isinstance(result, AcceptServerResponse) or broker.accepted_artifact is None:
        code = result.code if isinstance(result, Failed) else "response_not_accepted"
        _finish_failure(job, state, "protocol_failed", code)
        return

    artifact = broker.accepted_artifact
    rendered_pdf: bytes | None = None
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
                job.note("decoded ReportX document lacks parsed ticket context")
            elif runtime_profile_required is None:
                job.status = "server_report_decoded_unrendered"
                job.note("decoded ReportX FP3 failed structural inspection")
            elif state.require_original_fonts and not state.font_map:
                job.status = "server_report_fonts_required"
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
                except (TypeError, FP3RenderError) as error:
                    job.status = "server_report_decoded_unrendered"
                    job.note(
                        "decoded ReportX outer container; FP3 renderer "
                        f"rejected it ({type(error).__name__})"
                    )
                else:
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
                job.note(
                    "prepare the exact-hash official ReportX runtime assets "
                    "before rendering"
                )
            else:
                param_5 = parsed.get("Param_5")
                if param_5 not in {None, "", "0", "1"}:
                    job.status = "server_report_decoded_unrendered"
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
                        job.note(
                            "document serial requires one mutating URLCheck "
                            "reservation; no request was made"
                        )
                    else:
                        # Validate every local placeholder and official asset
                        # before crossing the one-shot reservation boundary.
                        try:
                            build_runtime_bindings(
                                bundle.primary,
                                state.official_assets,
                                ("0000000000000000",),
                                hide_logo=param_5 == "1",
                            )
                            reservation_action = build_document_number_action(
                                parsed
                            )
                        except (
                            TypeError,
                            ReportXProfileError,
                            TicketDecodeError,
                        ) as error:
                            job.status = "server_report_decoded_unrendered"
                            job.document_number_status = "preflight_rejected"
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
                    except (TypeError, FP3RenderError) as error:
                        job.status = "server_report_decoded_unrendered"
                        job.note(
                            "decoded ReportX outer container; FP3 renderer "
                            f"rejected it ({type(error).__name__})"
                        )
                    else:
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
                            "logo and reserved verification number; no "
                            "printcomplete request was made"
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
    finally:
        state.finish_job(job)


def schedule_job(job: Job, state: AgentState) -> tuple[str, str | None]:
    admission, existing_id = state.admit_job(job)
    if admission != "accepted":
        return admission, existing_id
    try:
        state.executor.submit(_process_job_guarded, job, state)
    except RuntimeError:
        state.finish_job(job)
        return "worker_unavailable", None
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
        os.chmod(path, 0o600)
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
) -> bool:
    """Authorize exact-origin requests or one explicitly armed originless handoff."""

    origin = handler.headers.get("Origin")
    if origin:
        if origin not in ALLOWED_PROTOCOL_ORIGINS:
            return False
        state.clear_protocol_arm()
        return True
    if _token_ok(state, _token(handler)):
        state.clear_protocol_arm()
        return True
    return state.consume_protocol_arm()


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
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
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
            if not _protocol_submission_authorized(self, STATE):
                self._send(401, html_message("HANDOFF NOT ARMED"), protocol=True)
                return
            job = Job(
                new_job_id(),
                utc_now(),
                "sso",
                param=param,
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

        if path in {"/health", "/status", "/jobs"}:
            if not self._control_authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            if path == "/health":
                self._json(
                    200,
                    {
                        "ok": True,
                        "agent": "reportx-mac",
                        "protocol": "cleanroom-v1",
                    },
                )
                return
            with STATE.lock:
                jobs = [public_job_view(job) for job in list(STATE.jobs.values())[-50:]]
            self._json(
                200,
                {
                    "ok": True,
                        "agent": "reportx-mac",
                        "allow_fetch": STATE.allow_fetch,
                        "allow_document_reservation": (
                            STATE.allow_document_reservation
                        ),
                        "official_assets": (
                            "ready"
                            if STATE.official_assets is not None
                            else "not_prepared"
                        ),
                        "output_dir": STATE.out_dir.name,
                    "jobs": jobs,
                    "printers": list_cups_printers() if path == "/status" else [],
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
            ttl = STATE.arm_protocol_once()
            self._json(
                200,
                {
                    "ok": True,
                    "armed": True,
                    "one_shot": True,
                    "ttl_seconds": ttl,
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
    server = ThreadingHTTPServer((host, port), ReportXHandler)
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


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument(
        "--title-font",
        type=Path,
        help="Member-supplied official Yonsei title TrueType font.",
    )
    parser.add_argument(
        "--body-font",
        type=Path,
        help="Member-supplied official Yonsei body TrueType font.",
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
