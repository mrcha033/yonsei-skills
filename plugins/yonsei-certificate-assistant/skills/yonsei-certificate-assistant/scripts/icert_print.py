#!/usr/bin/env python3
"""Operate the clean-room macOS/Linux ReportX compatibility agent.

Examples:
  python3 icert_print.py doctor
  python3 icert_print.py prepare-assets
  python3 icert_print.py agent
  python3 icert_print.py agent --allow-fetch --reserve-document-number
  python3 icert_print.py arm
  python3 icert_print.py status
  python3 icert_print.py wait-job
  python3 icert_print.py print-job JOB_ID --printer NAME --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from reportx_runtime_profile import (
    ReportXProfileError,
    prepare_official_assets,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 65432
DEFAULT_DIR = Path.home() / ".cache" / "yonsei-certificate-assistant"
PORTAL = "https://portal.yonsei.ac.kr/ui/index.html"
ICERT = "https://icert.yonsei.ac.kr/"
FONT_GUIDE = "https://www.yonsei.ac.kr/sc/337/subview.do"
SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_SCRIPT = SCRIPT_DIR / "reportx_mac_agent.py"
DIAGNOSE = SCRIPT_DIR / "diagnose_print_env.py"
YONSEI_FONT_FILENAMES = {
    "title": ("연세제목.TTF", "연세제목.ttf", "YonseiB.ttf"),
    "body": ("연세본문.TTF", "연세본문.ttf", "YonseiL.ttf"),
}
SUCCESS_STATES = frozenset(
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
    }
)
FAILURE_STATES = frozenset(
    {
        "unsupported_protocol",
        "decode_failed",
        "transport_failed",
        "protocol_failed",
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
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
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
    print("agent: DOWN")
    print(f"start with: python3 {AGENT_SCRIPT} --dir {cache}")
    return 1


def local_font_roots() -> tuple[Path, ...]:
    roots = [
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
        open_url(FONT_GUIDE)
        print(
            "연세 제목체와 본문체가 모두 필요합니다. 교내 구성원용 공식 "
            "연세체 안내를 열었습니다. 학교 계정으로 두 글꼴을 내려받은 "
            "뒤 파일을 선택해 주세요.",
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
            "(embedded from local authorized copies)",
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
    try:
        prepare_official_assets(cache, installer_path=installer)
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
                    "verified_local_installer"
                    if installer is not None
                    else "verified_official_download"
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


def open_url(url: str) -> bool:
    system = platform.system()
    command: list[str] | None = None
    if system == "Darwin" and shutil.which("open"):
        command = ["open", url]
    elif system == "Linux" and shutil.which("xdg-open"):
        command = ["xdg-open", url]
    if command is not None:
        return subprocess.run(command, check=False).returncode == 0
    if system == "Windows" and hasattr(os, "startfile"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except OSError:
            pass
    return bool(webbrowser.open(url, new=2))


def cmd_open(_: argparse.Namespace) -> int:
    for url in (PORTAL, ICERT):
        if not open_url(url):
            print(url)
    print(
        "\n다음 순서:\n"
        "1) 최초 1회: python3 icert_print.py prepare-assets\n"
        "2) 별도 터미널: python3 icert_print.py agent --allow-fetch "
        "--reserve-document-number\n"
        "3) 로그인하고 발급할 증명서를 선택\n"
        "4) 클릭 직전: python3 icert_print.py arm\n"
        "5) 120초 안에 프린터 출력을 선택\n"
        "6) 브라우저가 공식 /SSO handoff를 자동으로 로컬 agent에 전달\n"
        "7) python3 icert_print.py wait-job\n"
        "\nDevTools bridge나 캡처 스크립트는 사용하지 않습니다."
    )
    return 0


def cmd_wait_job(args: argparse.Namespace) -> int:
    token = read_token(Path(args.dir).expanduser())
    if not token:
        print(json.dumps({"ok": False, "error": "missing agent.token"}))
        return 1
    deadline = time.time() + args.timeout
    last_marker: tuple[str, str] | None = None
    last: dict | None = None
    while time.time() < deadline:
        try:
            status = http_json(
                f"{agent_base(args.port)}/status",
                token=token,
            )
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
        ):
            time.sleep(0.5)
            continue
        jobs = status.get("jobs") or []
        if jobs:
            last = jobs[-1]
            marker = (
                str(last.get("id")),
                str(last.get("status")),
            )
            if marker != last_marker:
                print(json.dumps(last, ensure_ascii=False, indent=2))
                last_marker = marker
            state = last.get("status")
            if state in SUCCESS_STATES:
                return 0
            if state in FAILURE_STATES:
                return 2
        time.sleep(0.5)
    print(
        json.dumps(
            {"ok": False, "error": "timeout", "last": last},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


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


def main() -> int:
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
    assets_parser = subparsers.add_parser(
        "prepare-assets",
        help="Extract pinned runtime assets from the official Yonsei installer",
    )
    assets_parser.add_argument(
        "--installer",
        help="Use an existing exact-hash installer instead of downloading it",
    )
    subparsers.add_parser("status", help="Show redacted job manifests")
    subparsers.add_parser(
        "arm",
        help="Authorize one originless browser /SSO handoff for 120 seconds",
    )
    subparsers.add_parser("open", help="Open the portal and icert")
    wait_parser = subparsers.add_parser("wait-job", help="Wait for a terminal job state")
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
        "arm": cmd_arm,
        "open": cmd_open,
        "wait-job": cmd_wait_job,
        "print-job": cmd_print_job,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
