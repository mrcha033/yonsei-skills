#!/usr/bin/env python3
"""Operate the clean-room Windows/macOS/Linux ReportX compatibility agent.

Examples:
  python3 icert_print.py start
  python3 icert_print.py issue --request request.json --output result.pdf --confirm
  python3 icert_print.py wait-job JOB_ID
  python3 icert_print.py print-job JOB_ID --printer NAME --confirm
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from reportx_runtime_profile import (
    ReportXProfileError,
    prepare_official_assets,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65432
DEFAULT_DIR = Path.home() / ".cache" / "yonsei-certificate-assistant"
PORTAL = "https://portal.yonsei.ac.kr/ui/index.html"
SCRIPT_DIR = Path(__file__).resolve().parent
PREPARE_ISSUE = (
    SCRIPT_DIR.parent.parent
    / "issue-yonsei-certificate"
    / "scripts"
    / "prepare_certificate_issue.py"
)
AGENT_SCRIPT = SCRIPT_DIR / "reportx_mac_agent.py"
DIAGNOSE = SCRIPT_DIR / "diagnose_print_env.py"
YONSEI_FONT_FILENAMES = {
    "title": ("연세제목.TTF", "연세제목.ttf", "YonseiB.ttf"),
    "body": ("연세본문.TTF", "연세본문.ttf", "YonseiL.ttf"),
}
SUCCESS_STATES = frozenset(
    {
        "server_pdf_saved_unverified",
        "server_report_rendered_pdf_unverified",
        "server_document_reused_unverified",
    }
)
FAILURE_STATES = frozenset(
    {
        "decoded_network_disabled",
        "server_report_decoded_unrendered",
        "server_report_document_number_required",
        "server_report_fonts_required",
        "server_report_official_assets_required",
        "server_report_saved_unrendered",
        "document_number_reservation_unknown",
        "unsupported_protocol",
        "decode_failed",
        "transport_failed",
        "protocol_failed",
        "duplicate_server_document",
    }
)
TRANSIENT_STATES = frozenset(
    {
        "received",
        "decoding",
        "requesting",
        "reserving_document_number",
    }
)


def agent_base(port: int = DEFAULT_PORT) -> str:
    return f"http://{DEFAULT_HOST}:{port}"


def read_token(cache_dir: Path) -> str | None:
    path = cache_dir / "agent.token"
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
        return None
    return path.read_text(encoding="utf-8").strip() or None


def build_control_opener() -> urllib.request.OpenerDirector:
    """Build a direct-only opener so the loopback control token stays local."""

    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(
    url: str,
    *,
    token: str | None = None,
    timeout: float = 3.0,
    data: dict | None = None,
) -> dict:
    headers = {"User-Agent": "icert-print/0.4"}
    if token:
        headers["X-Agent-Token"] = token
    body = None
    method = "GET"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    with build_control_opener().open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def agent_up(port: int, token: str | None) -> bool:
    try:
        if token:
            return bool(
                http_json(f"{agent_base(port)}/health", token=token).get("ok")
            )
        with build_control_opener().open(
            f"{agent_base(port)}/SSO_ETC",
            timeout=2,
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return False


def status_payload(args: argparse.Namespace) -> dict:
    token = read_token(Path(args.dir).expanduser())
    if not token:
        raise RuntimeError("missing agent.token; start the agent first")
    return http_json(f"{agent_base(args.port)}/status", token=token)


def emit_json(payload: dict) -> None:
    """Emit one complete event so a computer-use caller can act immediately."""

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def read_json_input(source: str) -> dict:
    if source == "-":
        value = json.load(sys.stdin)
    elif source.lstrip().startswith("{"):
        value = json.loads(source)
    else:
        value = json.loads(Path(source).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def prepare_issue_plan(request: dict) -> dict:
    """Run the single source of truth for intake validation."""

    completed = subprocess.run(
        [sys.executable, str(PREPARE_ISSUE)],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        timeout=10,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("certificate request validator returned invalid JSON") from error
    if completed.returncode != 0:
        detail = payload.get("error") if isinstance(payload, dict) else payload
        raise ValueError(json.dumps(detail, ensure_ascii=False))
    if not isinstance(payload, dict):
        raise RuntimeError("certificate request validator returned a non-object")
    return payload


def _agent_command(args: argparse.Namespace) -> list[str]:
    title_font = find_local_yonsei_font("title")
    body_font = find_local_yonsei_font("body")
    if title_font is None or body_font is None:
        raise RuntimeError(
            "authorized bundled Yonsei title/body fonts are missing; reinstall the plugin"
        )
    return [
        sys.executable,
        str(AGENT_SCRIPT),
        "--port",
        str(args.port),
        "--dir",
        str(Path(args.dir).expanduser()),
        "--allow-fetch",
        "--reserve-document-number",
        "--notify-print-completion",
        "--title-font",
        str(title_font),
        "--body-font",
        str(body_font),
    ]


def _agent_ready_status(args: argparse.Namespace) -> dict | None:
    cache = Path(args.dir).expanduser()
    token = read_token(cache)
    if not token or not agent_up(args.port, token):
        return None
    status = http_json(f"{agent_base(args.port)}/jobs", token=token)
    capabilities = (
        status.get("allow_fetch") is True
        and status.get("allow_document_reservation") is True
        and status.get("allow_completion_notification") is True
        and status.get("official_assets") == "ready"
        and (status.get("readiness") or {}).get("live_issue_ready") is True
    )
    if not capabilities:
        raise RuntimeError(
            "running agent lacks the full PDF capabilities; stop that listener before retrying"
        )
    return status


def ensure_agent_ready(args: argparse.Namespace) -> dict:
    """Reuse the prepared agent, or perform cold setup once."""

    existing = _agent_ready_status(args)
    if existing is not None:
        return {"mode": "reused", "status": existing}

    cache = Path(args.dir).expanduser()
    try:
        prepare_official_assets(cache)
    except (OSError, ReportXProfileError) as error:
        raise RuntimeError(f"official asset preparation failed: {error}") from error

    log_path = cache / "agent.log"
    cache.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    process = subprocess.Popen(
        _agent_command(args),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline and process.poll() is None:
        try:
            ready = _agent_ready_status(args)
        except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
            ready = None
        if ready is not None:
            return {
                "mode": "started",
                "pid": process.pid,
                "log": str(log_path),
                "status": ready,
            }
        time.sleep(0.15)
    if process.poll() is not None:
        raise RuntimeError(f"certificate agent exited during startup; review {log_path}")
    raise RuntimeError("certificate agent did not become ready within 12 seconds")


def require_prewarmed_agent(args: argparse.Namespace) -> dict:
    """Keep cold downloads outside the post-confirmation time budget."""

    status = _agent_ready_status(args)
    if status is None:
        raise RuntimeError("agent is not prewarmed; run start during intake/login")
    return {"mode": "reused", "status": status}


def hot_path_deadline(started: float, requested_timeout: float) -> float:
    if requested_timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    return started + min(requested_timeout, 55.0)


def job_list(
    args: argparse.Namespace,
    *,
    correlation_id: str | None = None,
) -> list[dict]:
    token = read_token(Path(args.dir).expanduser())
    if not token:
        raise RuntimeError("missing agent.token; start the agent first")
    url = f"{agent_base(args.port)}/jobs"
    if correlation_id is not None:
        url += f"?correlation_id={correlation_id}"
    payload = http_json(url, token=token)
    return [job for job in payload.get("jobs", []) if isinstance(job, dict)]


def terminal_job_result(job: dict) -> int | None:
    state = str(job.get("status") or "")
    if state in TRANSIENT_STATES or not state:
        return None
    if state in SUCCESS_STATES:
        if state == "server_document_reused_unverified":
            rendered = job.get("rendered_pdf") or {}
            artifact = job.get("artifact") or {}
            if not (
                (rendered.get("path") and rendered.get("sha256"))
                or (artifact.get("path") and artifact.get("sha256"))
            ):
                return 2
        document_number = job.get("document_number") or {}
        if document_number.get("status") == "reserved":
            if document_number.get("completion_notified") is True:
                return 0
            if document_number.get("completion_status") in {
                "not_requested",
                "request_started_unknown",
            }:
                return None
            return 2
        return 0
    if state in FAILURE_STATES:
        return 2
    return None


def wait_for_job_id(
    args: argparse.Namespace,
    job_id: str,
    *,
    deadline: float,
) -> tuple[int, dict | None]:
    last: dict | None = None
    while time.monotonic() < deadline:
        try:
            last = next(
                (job for job in job_list(args) if str(job.get("id")) == job_id),
                None,
            )
        except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(0.2)
            continue
        if last is not None:
            result = terminal_job_result(last)
            if result is not None:
                return result, last
        time.sleep(0.2)
    return 1, last


def wait_for_new_job(
    args: argparse.Namespace,
    baseline_ids: set[str],
    *,
    deadline: float,
) -> tuple[int, dict | None]:
    """Pin the first post-arm ID, then follow only that exact job."""

    target_id: str | None = None
    last: dict | None = None
    while time.monotonic() < deadline:
        try:
            jobs = job_list(args)
        except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(0.2)
            continue
        if target_id is None:
            new_jobs = [
                job
                for job in jobs
                if str(job.get("id") or "") not in baseline_ids
            ]
            if len(new_jobs) > 1:
                return 2, {
                    "status": "ambiguous_new_jobs",
                    "job_ids": [str(job.get("id")) for job in new_jobs],
                }
            if new_jobs:
                target_id = str(new_jobs[0].get("id"))
                last = new_jobs[0]
        else:
            last = next(
                (job for job in jobs if str(job.get("id")) == target_id),
                last,
            )
        if target_id is not None and last is not None:
            result = terminal_job_result(last)
            if result is not None:
                return result, last
        time.sleep(0.2)
    return 1, last


def wait_for_correlated_job(
    args: argparse.Namespace,
    arm_id: str,
    baseline_ids: set[str],
    *,
    deadline: float,
) -> tuple[int, dict | None]:
    """Follow only the job tagged by this exact one-shot arm."""

    target_id: str | None = None
    last: dict | None = None
    while time.monotonic() < deadline:
        try:
            jobs = job_list(args, correlation_id=arm_id)
        except (RuntimeError, urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(0.2)
            continue
        if len(jobs) > 1:
            return 2, {
                "status": "ambiguous_correlated_jobs",
                "correlation_id": arm_id,
                "job_ids": [str(job.get("id")) for job in jobs],
            }
        if jobs:
            correlated = jobs[0]
            correlated_id = str(correlated.get("id") or "")
            if not correlated_id or correlated_id in baseline_ids:
                return 2, {
                    "status": "invalid_correlated_job",
                    "correlation_id": arm_id,
                    "job_id": correlated_id or None,
                }
            if target_id is None:
                target_id = correlated_id
            elif correlated_id != target_id:
                return 2, {
                    "status": "correlated_job_changed",
                    "correlation_id": arm_id,
                    "job_ids": [target_id, correlated_id],
                }
            last = correlated
            result = terminal_job_result(last)
            if result is not None:
                return result, last
        time.sleep(0.2)
    return 1, last


def cmd_doctor(args: argparse.Namespace) -> int:
    subprocess.run([sys.executable, str(DIAGNOSE), "--text"], check=False)
    cache = Path(args.dir).expanduser()
    token = read_token(cache)
    print("\n== clean-room ReportX agent ==")
    if agent_up(args.port, token):
        if token:
            print(
                json.dumps(
                    http_json(f"{agent_base(args.port)}/status", token=token),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("agent: UP (protocol liveness only)")
        return 0
    print(
        json.dumps(
            {
                "ok": True,
                "state": "not_running",
                "ready_for_setup": True,
                "start": (
                    f"python3 {Path(__file__).resolve()} --dir {cache} agent "
                    "--allow-fetch --reserve-document-number "
                    "--notify-print-completion"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def local_font_roots() -> tuple[Path, ...]:
    roots = [
        SCRIPT_DIR.parent / "assets" / "fonts",
        Path.home() / "Downloads",
        Path.home() / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path.home() / ".local" / "share" / "fonts",
        Path.home() / ".fonts",
        Path("/usr/share/fonts"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    windows_dir = os.environ.get("WINDIR")
    if local_app_data:
        roots.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
    if windows_dir:
        roots.append(Path(windows_dir) / "Fonts")
    return tuple(roots)


def find_local_yonsei_font(kind: str) -> Path | None:
    filenames = {name.casefold() for name in YONSEI_FONT_FILENAMES[kind]}
    for root in local_font_roots():
        if not root.is_dir():
            continue
        if root == Path("/usr/share/fonts"):
            paths = root.rglob("*.ttf")
        else:
            paths = root.glob("*")
        for path in paths:
            try:
                if path.is_file() and path.name.casefold() in filenames:
                    return path.resolve()
            except OSError:
                continue
    return None


def cmd_agent(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(AGENT_SCRIPT),
        "--port",
        str(args.port),
        "--dir",
        str(Path(args.dir).expanduser()),
    ]
    if args.allow_fetch:
        command.append("--allow-fetch")
    if args.reserve_document_number:
        command.append("--reserve-document-number")
    if args.notify_print_completion:
        command.append("--notify-print-completion")
    title_font = (
        Path(args.title_font).expanduser().resolve()
        if args.title_font
        else find_local_yonsei_font("title")
    )
    body_font = (
        Path(args.body_font).expanduser().resolve()
        if args.body_font
        else find_local_yonsei_font("body")
    )
    if args.allow_fetch and (
        title_font is None or body_font is None
    ):
        print(
            "번들된 연세 제목체 또는 본문체가 누락되었습니다. 플러그인을 "
            "다시 설치해 주세요. 다른 글꼴로 발급하지 않습니다.",
            file=sys.stderr,
        )
        return 2
    if title_font is not None and body_font is not None:
        command.extend(
            [
                "--title-font",
                str(title_font),
                "--body-font",
                str(body_font),
            ]
        )
        print(
            "fonts:",
            title_font.name,
            body_font.name,
            "(embedded from authorized bundled copies)",
            flush=True,
        )
    print("exec:", " ".join(command), flush=True)
    os.execvp(command[0], command)
    return 0


def cmd_prepare_assets(args: argparse.Namespace) -> int:
    cache = Path(args.dir).expanduser()
    installer = (
        Path(args.installer).expanduser()
        if args.installer is not None
        else None
    )
    reportx_exe = (
        Path(args.reportx_exe).expanduser()
        if args.reportx_exe is not None
        else None
    )
    try:
        prepare_official_assets(
            cache,
            installer_path=installer,
            reportx_exe_path=reportx_exe,
        )
    except (OSError, ReportXProfileError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(error).__name__,
                    "detail": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "status": "official_assets_ready",
                "source": (
                    "verified_installed_reportx"
                    if reportx_exe is not None
                    else (
                        "verified_local_installer"
                        if installer is not None
                        else "verified_installed_runtime_or_official_download"
                    )
                ),
                "vendor_bytes_bundled": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        payload = status_payload(args)
    except (
        RuntimeError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"ok": False, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_arm(args: argparse.Namespace) -> int:
    cache = Path(args.dir).expanduser()
    token = read_token(cache)
    if not token:
        print(
            json.dumps(
                {"ok": False, "error": "missing_or_insecure_agent_token"},
                ensure_ascii=False,
            )
        )
        return 1
    try:
        payload = http_json(
            f"{agent_base(args.port)}/arm",
            token=token,
            data={},
        )
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("armed") else 1


def cmd_open(_: argparse.Namespace) -> int:
    emit_json(
        {
            "ok": True,
            "state": "computer_use_required",
            "browser": {
                "controller": "Codex Computer Use",
                "entry_url": PORTAL,
                "reuse_current_user_browser": True,
                "cli_browser_launch_performed": False,
            },
            "official_route": ["인터넷증명서", "인터넷즉시발급"],
            "login_action": "complete_once_if_the_visible_official_page_requests_it",
        }
    )
    return 0


def startup_handoff() -> dict:
    return {
        "schema": "yonsei-certificate-start/v1",
        "state": "intake_and_login",
        "browser": {
            "controller": "Codex Computer Use",
            "entry_url": PORTAL,
            "reuse_current_user_browser": True,
            "cli_browser_launch_performed": False,
        },
        "login": {
            "inspect_visible_page_with": "Codex Computer Use",
            "action": "ask_the_student_once_to_complete_login_if_required",
            "never_collect": ["password", "otp", "cookie"],
        },
        "ask_once": {
            "certificate_type": list(
                (
                    "enrollment",
                    "transcript",
                    "graduation",
                    "expected_graduation",
                    "leave",
                    "completion",
                )
            ),
            "language": ["ko", "en"],
            "copies": 1,
            "output": ["pdf", "physical_print"],
            "transcript_only": {
                "include_rank": [True, False],
                "include_conversion": [True, False],
                "conversion_scale_when_included": ["4.5"],
            },
            "purpose": "optional",
            "authorization": (
                "capture_in_this_initial_batch_unless_the_fully_specified_"
                "original_prompt_already_commands_issuance"
            ),
        },
        "background_setup": {
            "cache": str(DEFAULT_DIR),
            "state": "preparing_official_assets_and_agent",
        },
    }


def cmd_start(args: argparse.Namespace) -> int:
    """Request Computer Use login immediately, then prewarm during intake."""

    handoff = startup_handoff()
    handoff["background_setup"]["cache"] = str(Path(args.dir).expanduser())
    emit_json(handoff)
    try:
        runtime = ensure_agent_ready(args)
    except RuntimeError as error:
        emit_json({"ok": False, "state": "prewarm_failed", "error": str(error)})
        return 1
    emit_json(
        {
            "ok": True,
            "state": "prewarmed",
            "cache": str(Path(args.dir).expanduser()),
            "agent": runtime["mode"],
            "next": "one_confirmed_issue_command_after_visible_login_is_connected",
        }
    )
    return 0


def computer_use_handoff(
    *,
    plan: dict,
    baseline_ids: set[str],
    arm_id: str,
    timeout: float,
) -> dict:
    request = plan["computer_use_request"]
    return {
        "schema": "yonsei-certificate-computer-use-handoff/v1",
        "state": "armed_and_waiting_for_one_official_print_click",
        "browser": {
            "controller": "Codex Computer Use",
            "entry_url": PORTAL,
            "reuse_current_user_browser": True,
            "cli_browser_launch_performed": False,
        },
        "official_route": {
            "start": PORTAL,
            "visible_labels": ["인터넷증명서", "인터넷즉시발급"],
            "success_page": "신청증명서함",
        },
        "request": request,
        "actions": [
            {
                "action": "verify_visible_authenticated_official_page",
                "on_login_required": "stop_without_clicking_and_report_login_required",
            },
            {
                "action": "select_or_reuse_exact_request_row",
                "match_fields": [
                    "certificate_label",
                    "language_label",
                    "copies",
                    "rank",
                    "conversion",
                ],
            },
            {
                "action": "click_once",
                "visible_text": "프린터 출력",
                "maximum_clicks": 1,
            },
        ],
        "prohibited": [
            "paid_electronic_certificate",
            "coordinate_clicks",
            "AppleScript",
            "Orca",
            "retry_after_uncertain_click",
        ],
        "job_tracking": {
            "arm_id": arm_id,
            "baseline_job_ids": sorted(baseline_ids),
            "correlation": "correlation_id_equals_arm_id_then_exact_job_id_only",
            "waiter": "this_same_process",
            "timeout_seconds": timeout,
        },
    }


def export_job_pdf(job: dict, cache_dir: Path, destination: Path) -> dict:
    rendered = job.get("rendered_pdf") or {}
    artifact = job.get("artifact") or {}
    source = rendered if rendered.get("path") and rendered.get("sha256") else artifact
    filename = Path(str(source.get("path") or "")).name
    expected = str(source.get("sha256") or "")
    if not filename or not expected:
        raise RuntimeError("completed job has no PDF path and digest")
    output_root = (cache_dir / "output").resolve()
    candidate = (output_root / filename).resolve()
    try:
        candidate.relative_to(output_root)
        body = candidate.read_bytes()
    except (OSError, ValueError) as error:
        raise RuntimeError("private source PDF is missing or outside its cache") from error
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected or not body.startswith(b"%PDF-") or b"%%EOF" not in body[-4096:]:
        raise RuntimeError("private source PDF failed digest or structure verification")

    destination = destination.expanduser().resolve()
    if destination.suffix.casefold() != ".pdf":
        raise RuntimeError("output destination must end in .pdf")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        info = destination.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("output destination exists but is not a regular file")
        existing = destination.read_bytes()
    except FileNotFoundError:
        existing = None
    except OSError as error:
        raise RuntimeError(f"cannot inspect output destination: {destination}") from error
    if existing is not None:
        if hashlib.sha256(existing).hexdigest() != expected:
            raise RuntimeError(
                "output destination already exists with different bytes; refusing overwrite"
            )
        return {"path": str(destination), "sha256": expected, "reused": True}
    try:
        with destination.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise RuntimeError("output destination appeared during export; refusing overwrite") from error
    exported = destination.read_bytes()
    if hashlib.sha256(exported).hexdigest() != expected:
        raise RuntimeError("exported PDF digest did not match the private source")
    return {"path": str(destination), "sha256": expected, "reused": False}


def cmd_issue(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        deadline = hot_path_deadline(started, args.timeout)
    except ValueError as error:
        emit_json({"ok": False, "state": "invalid_timeout", "error": str(error)})
        return 2
    try:
        request = read_json_input(args.request)
        plan = prepare_issue_plan(request)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        emit_json({"ok": False, "state": "invalid_request", "error": str(error)})
        return 2
    if not args.confirm:
        emit_json(
            {
                "ok": False,
                "state": "confirmation_required",
                "review": plan.get("review"),
                "next": "run_this_same_issue_command_once_with_--confirm",
            }
        )
        return 2
    if plan.get("missing_user_fields"):
        emit_json(
            {
                "ok": False,
                "state": "intake_incomplete",
                "missing_user_fields": plan.get("missing_user_fields"),
                "action": "ask_all_listed_fields_together_before_authorization",
            }
        )
        return 2
    if not plan.get("ready"):
        emit_json(
            {
                "ok": False,
                "state": "login_required",
                "browser": {
                    "controller": "Codex Computer Use",
                    "entry_url": PORTAL,
                    "reuse_current_user_browser": True,
                    "cli_browser_launch_performed": False,
                },
                "action": "complete_the_visible_official_login_once_then_recheck_before_authorization",
            }
        )
        return 3
    if plan.get("output") == "physical_print" and platform.system() == "Windows":
        emit_json(
            {
                "ok": False,
                "state": "native_windows_physical_print_required",
                "review": plan.get("review"),
            }
        )
        return 2

    try:
        runtime = require_prewarmed_agent(args)
        baseline = {
            str(job.get("id"))
            for job in job_list(args)
            if job.get("id")
        }
        token = read_token(Path(args.dir).expanduser())
        if not token:
            raise RuntimeError("agent token disappeared before arm")
        armed = http_json(f"{agent_base(args.port)}/arm", token=token, data={})
        if not armed.get("armed"):
            raise RuntimeError("agent did not accept the one-shot arm")
        arm_id = str(armed.get("arm_id") or "")
        if len(arm_id) != 24 or any(character not in "0123456789abcdef" for character in arm_id):
            raise RuntimeError("agent returned an invalid arm correlation ID")
    except (
        RuntimeError,
        OSError,
        urllib.error.URLError,
        TimeoutError,
        ValueError,
    ) as error:
        emit_json({"ok": False, "state": "startup_failed", "error": str(error)})
        return 1

    remaining = max(0.0, deadline - time.monotonic())
    if remaining <= 0:
        emit_json({"ok": False, "state": "hot_path_deadline_exhausted_before_browser_handoff"})
        return 1
    emit_json(
        computer_use_handoff(
            plan=plan,
            baseline_ids=baseline,
            arm_id=arm_id,
            timeout=round(remaining, 3),
        )
    )
    code, job = wait_for_correlated_job(
        args,
        arm_id,
        baseline,
        deadline=deadline,
    )
    if code != 0 or job is None:
        emit_json(
            {
                "ok": False,
                "state": (
                    "job_failed" if code == 2 else "timeout_unknown_do_not_retry"
                ),
                "job": job,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        )
        return code
    try:
        exported = export_job_pdf(
            job,
            Path(args.dir).expanduser(),
            Path(args.output_path),
        )
    except RuntimeError as error:
        emit_json(
            {
                "ok": False,
                "state": "pdf_export_failed",
                "job_id": job.get("id"),
                "error": str(error),
            }
        )
        return 2

    physical = None
    if plan.get("output") == "physical_print":
        try:
            token = read_token(Path(args.dir).expanduser())
            if not token:
                raise RuntimeError("agent token missing before physical print")
            physical = http_json(
                f"{agent_base(args.port)}/print-job",
                token=token,
                timeout=65,
                data={
                    "job_id": job.get("id"),
                    "printer": plan.get("printer"),
                    "expected_sha256": exported["sha256"],
                    "confirm": True,
                },
            )
            if not physical.get("ok"):
                raise RuntimeError("named physical printer did not accept the job")
        except (
            RuntimeError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ValueError,
        ) as error:
            emit_json(
                {
                    "ok": False,
                    "state": "physical_print_unknown_do_not_retry",
                    "job_id": job.get("id"),
                    "pdf": exported,
                    "error": str(error),
                }
            )
            return 2
    emit_json(
        {
            "ok": True,
            "state": "completed",
            "job_id": job.get("id"),
            "status": job.get("status"),
            "pdf": exported,
            "physical_print": physical,
            "completion_notified": (job.get("document_number") or {}).get(
                "completion_notified"
            ),
            "agent": runtime["mode"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "verification": "not_performed",
        }
    )
    return 0


def cmd_wait_job(args: argparse.Namespace) -> int:
    code, job = wait_for_job_id(
        args,
        args.job_id,
        deadline=time.monotonic() + args.timeout,
    )
    emit_json(
        {
            "ok": code == 0,
            "state": (
                "completed"
                if code == 0
                else ("job_failed" if code == 2 else "timeout")
            ),
            "job_id": args.job_id,
            "job": job,
        }
    )
    return code


def cmd_print_job(args: argparse.Namespace) -> int:
    if not args.confirm:
        print(
            "refusing print without --confirm; review status and choose a printer",
            file=sys.stderr,
        )
        return 2
    cache = Path(args.dir).expanduser()
    token = read_token(cache)
    if not token:
        print("missing agent.token", file=sys.stderr)
        return 1
    try:
        status = http_json(
            f"{agent_base(args.port)}/status",
            token=token,
        )
        job = next(
            item
            for item in status.get("jobs", [])
            if item.get("id") == args.job_id
        )
        digest = str(
            job.get("rendered_pdf", {}).get("sha256")
            or job.get("artifact", {}).get("sha256")
            or ""
        )
        if not digest:
            raise ValueError("job has no printable artifact digest")
        result = http_json(
            f"{agent_base(args.port)}/print-job",
            token=token,
            timeout=65,
            data={
                "job_id": args.job_id,
                "printer": args.printer,
                "expected_sha256": digest,
                "confirm": True,
            },
        )
    except (
        StopIteration,
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {"ok": False, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def configure_utf8_stdio() -> None:
    """Keep Korean certificate status and errors lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("doctor", help="Check environment and agent health")
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run the loopback compatibility agent in the foreground",
    )
    agent_parser.add_argument(
        "--allow-fetch",
        action="store_true",
        help="Opt in to the decoded allowlisted HTTPS URLFile request",
    )
    agent_parser.add_argument(
        "--title-font",
        help="Official Yonsei title TTF selected by the student.",
    )
    agent_parser.add_argument(
        "--body-font",
        help="Official Yonsei body TTF selected by the student.",
    )
    agent_parser.add_argument(
        "--reserve-document-number",
        action="store_true",
        help=(
            "Permit one URLCheck number reservation; never retries after "
            "the request starts"
        ),
    )
    agent_parser.add_argument(
        "--notify-print-completion",
        action="store_true",
        help=(
            "After a durable verified PDF save, notify the official "
            "print-completion endpoint once"
        ),
    )
    assets_parser = subparsers.add_parser(
        "prepare-assets",
        help="Extract pinned runtime assets from the official Yonsei installer",
    )
    assets_parser.add_argument(
        "--installer",
        help="Use an existing exact-hash installer instead of downloading it",
    )
    assets_parser.add_argument(
        "--reportx-exe",
        help=(
            "Use an installed official REPORTX.exe after its pinned hash is "
            "verified; useful on Windows without innoextract"
        ),
    )
    subparsers.add_parser("status", help="Show redacted job manifests")
    subparsers.add_parser(
        "start",
        help="Emit the Computer Use login handoff and prewarm during intake",
    )
    issue_parser = subparsers.add_parser(
        "issue",
        help="Run the one-command post-login issuance and export the exact new PDF",
    )
    issue_parser.add_argument(
        "--request",
        required=True,
        help="Complete inline JSON, a JSON file, or - for stdin",
    )
    issue_parser.add_argument(
        "--output",
        dest="output_path",
        required=True,
        help="New PDF destination; an existing different file is never overwritten",
    )
    issue_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Apply the one reviewed authorization for issuance and requested output",
    )
    issue_parser.add_argument(
        "--timeout",
        type=float,
        default=55.0,
        help="Overall warm-path budget, capped at 55 seconds to leave export margin",
    )
    subparsers.add_parser(
        "arm",
        help="Authorize one live browser /SSO handoff for 120 seconds",
    )
    subparsers.add_parser("open", help="Emit the official Portal Computer Use handoff")
    wait_parser = subparsers.add_parser("wait-job", help="Wait for a terminal job state")
    wait_parser.add_argument("job_id", help="Exact job ID to follow")
    wait_parser.add_argument("--timeout", type=float, default=120.0)
    print_parser = subparsers.add_parser(
        "print-job",
        help="Explicitly submit one saved PDF to one named CUPS printer",
    )
    print_parser.add_argument("job_id")
    print_parser.add_argument("--printer", required=True)
    print_parser.add_argument("--confirm", action="store_true")

    args = parser.parse_args()
    handlers = {
        "doctor": cmd_doctor,
        "prepare-assets": cmd_prepare_assets,
        "agent": cmd_agent,
        "status": cmd_status,
        "start": cmd_start,
        "issue": cmd_issue,
        "arm": cmd_arm,
        "open": cmd_open,
        "wait-job": cmd_wait_job,
        "print-job": cmd_print_job,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
