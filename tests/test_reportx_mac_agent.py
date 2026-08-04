from __future__ import annotations

import hashlib
import json
import os
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
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = (
    ROOT
    / "plugins"
    / "yonsei-certificate-assistant"
    / "skills"
    / "yonsei-certificate-assistant"
    / "scripts"
)
AGENT = SCRIPTS / "reportx_mac_agent.py"
FONT_DIR = SCRIPTS.parent / "assets" / "fonts"
TITLE_FONT = FONT_DIR / "연세제목.TTF"
BODY_FONT = FONT_DIR / "연세본문.TTF"
sys.path.insert(0, str(SCRIPTS))

import reportx_mac_agent as agent  # noqa: E402
import icert_print as cli  # noqa: E402
from reportx_protocol import NetworkResponse  # noqa: E402
from reportx_document_v1 import reportx_document_key  # noqa: E402
from reportx_protocol_v1 import reportx_aria_encrypt_block  # noqa: E402


CLEAR_URL = (
    "http://fixture.invalid/SHOWREPORT_PRINTAUTO?"
    "URLFile=uni.webminwon.com/servlet/WMINDEX"
    "|URLPost=post.invalid/print-completion"
    "|TPID=T-SYNTH"
    "|MINNO=M-SYNTH"
    "|GIWAN_NO=000000"
)
PLAIN_TICKET = "dzreportx:||" + CLEAR_URL
MINIMAL_FP3 = b"""\
<preparedreport>
  <previewpages><page0><m1 u="Rendered"/></page0></previewpages>
  <sourcepages>
    <TfrxReportPage Name="Page" PaperWidth="210" PaperHeight="297">
      <TfrxMemoView Name="Memo" Left="10" Top="10" Width="100"
        Height="20" Text="Source" Font.Name="Arial"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary><m1 name="Page0.Memo"/></dictionary>
</preparedreport>
"""


def minimal_pdf() -> bytes:
    header = b"%PDF-1.4\n"
    catalog = b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    xref_offset = len(header) + len(catalog)
    xref = (
        b"xref\n"
        b"0 2\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"trailer\n"
        b"<< /Size 2 /Root 1 0 R >>\n"
        b"startxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    return header + catalog + xref


def synthetic_document_response(
    primary: bytes,
    additional: tuple[bytes, ...],
    *,
    min_no: str = "M-SYNTH",
) -> bytes:
    parts = [
        len(primary).to_bytes(4, "little"),
        primary,
        len(additional).to_bytes(4, "little"),
    ]
    for item in additional:
        parts.extend((len(item).to_bytes(4, "little"), item))
    compressed = zlib.compress(b"".join(parts))
    framed = len(compressed).to_bytes(4, "little") + compressed
    padded = framed + b"\0" * (-len(framed) % 16)
    key = reportx_document_key(min_no)
    return b"".join(
        reportx_aria_encrypt_block(padded[offset : offset + 16], key)
        for offset in range(0, len(padded), 16)
    )


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def http(
    url: str,
    *,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    timeout: float = 3.0,
) -> tuple[int, bytes, dict]:
    body = None
    request_headers = {"User-Agent": "test-reportx-mac-agent"}
    if headers:
        request_headers.update(headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        payload = error.read()
        response_headers = dict(error.headers)
        error.close()
        return error.code, payload, response_headers


class LoopbackServerStartupTests(unittest.TestCase):
    def test_startup_never_depends_on_reverse_dns(self) -> None:
        with mock.patch(
            "socket.getfqdn",
            side_effect=AssertionError("reverse DNS must not run"),
        ):
            server = agent.LoopbackHTTPServer(
                ("127.0.0.1", 0),
                agent.ReportXHandler,
            )
        try:
            self.assertEqual("127.0.0.1", server.server_name)
            self.assertGreater(server.server_port, 0)
        finally:
            server.server_close()


class ReportXMacAgentHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="yonsei-agent-")
        self.cache = Path(self.tmp.name)
        self.port = free_port()
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(AGENT),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--dir",
                str(self.cache),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.base = f"http://127.0.0.1:{self.port}"
        self.token = self._wait_token_and_up()

    def tearDown(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.tmp.cleanup()

    def _wait_token_and_up(self) -> str:
        deadline = time.time() + 8
        last_error: Exception | None = None
        while time.time() < deadline:
            token_path = self.cache / "agent.token"
            if token_path.exists():
                token = token_path.read_text(encoding="utf-8").strip()
                try:
                    code, raw, _ = http(
                        self.base + "/health",
                        headers={"X-Agent-Token": token},
                        timeout=1,
                    )
                    if code == 200 and json.loads(raw).get("ok"):
                        return token
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                    last_error = error
            time.sleep(0.1)
        self.fail(f"agent did not start: {last_error}")

    def _jobs(self) -> list[dict]:
        code, raw, _ = http(
            self.base + "/jobs",
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)
        return json.loads(raw)["jobs"]

    def _arm(self) -> dict:
        code, raw, _ = http(
            self.base + "/arm",
            method="POST",
            data={},
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)
        result = json.loads(raw)
        self.assertTrue(result["armed"])
        return result

    def test_sso_decodes_without_capture_or_network(self) -> None:
        code, body, _ = http(self.base + "/SSO_ETC")
        self.assertEqual(200, code)
        self.assertIn(b"READY", body)

        self._arm()
        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, body, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(200, code)
        self.assertIn(b"JOB", body)
        deadline = time.time() + 3
        jobs: list[dict] = []
        while time.time() < deadline:
            jobs = self._jobs()
            if jobs and jobs[-1]["status"] == "decoded_network_disabled":
                break
            time.sleep(0.05)
        self.assertEqual("decoded_network_disabled", jobs[-1]["status"])
        self.assertEqual("reportx-1.0-cleanroom", jobs[-1]["decoder"]["id"])
        self.assertEqual("SHOWREPORT_PRINTAUTO", jobs[-1]["command"])
        self.assertEqual("not_performed", jobs[-1]["verification"])
        self.assertIsNone(jobs[-1]["artifact"]["path"])

    def test_missing_param_bad_origin_and_bad_host_do_not_create_jobs(self) -> None:
        before = len(self._jobs())
        code, _, _ = http(self.base + "/SSO")
        self.assertEqual(401, code)
        self.assertEqual(before, len(self._jobs()))

        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(401, code)
        self.assertEqual(before, len(self._jobs()))

        code, _, _ = http(
            self.base + "/SSO?PARAM=" + encoded,
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(403, code)
        self.assertEqual(before, len(self._jobs()))

        code, _, _ = http(
            self.base + "/SSO?PARAM=" + encoded,
            headers={"Host": "evil.example"},
        )
        self.assertEqual(421, code)
        self.assertEqual(before, len(self._jobs()))

    def test_originless_handoff_requires_one_shot_arm(self) -> None:
        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        self._arm()
        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(200, code)

        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(401, code)

    def test_arm_id_correlates_exact_job_and_wait_endpoint(self) -> None:
        armed = self._arm()
        self.assertRegex(armed["arm_id"], r"^[0-9a-f]{24}$")
        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(200, code)

        deadline = time.time() + 3
        correlated: list[dict] = []
        while time.time() < deadline:
            code, raw, _ = http(
                self.base + "/jobs?correlation_id=" + armed["arm_id"],
                headers={"X-Agent-Token": self.token},
            )
            self.assertEqual(200, code)
            correlated = json.loads(raw)["jobs"]
            if correlated:
                break
            time.sleep(0.02)
        self.assertEqual(1, len(correlated))
        self.assertEqual(armed["arm_id"], correlated[0]["correlation_id"])

        job_id = correlated[0]["id"]
        code, raw, _ = http(
            self.base + f"/jobs/{job_id}?wait=3",
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)
        result = json.loads(raw)
        self.assertTrue(result["terminal"])
        self.assertEqual(job_id, result["job"]["id"])

    def test_cli_arm_authorizes_originless_handoff(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "icert_print.py"),
                "--dir",
                str(self.cache),
                "--port",
                str(self.port),
                "arm",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["armed"])

        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(200, code)

    def test_decode_only_exact_icert_origin_can_submit_without_arm(self) -> None:
        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, _, headers = http(
            self.base + "/SSO?PARAM=" + encoded,
            headers={"Origin": "https://icert.yonsei.ac.kr"},
        )
        self.assertEqual(200, code)
        self.assertEqual(
            "https://icert.yonsei.ac.kr",
            headers.get("Access-Control-Allow-Origin"),
        )

    def test_control_plane_is_cli_only_and_token_required(self) -> None:
        code, raw, _ = http(self.base + "/status")
        self.assertEqual(401, code)
        self.assertFalse(json.loads(raw)["ok"])

        code, _, _ = http(
            self.base + "/status",
            headers={
                "X-Agent-Token": self.token,
                "Origin": "https://icert.yonsei.ac.kr",
            },
        )
        self.assertEqual(401, code)

        code, raw, _ = http(
            self.base + "/status",
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)
        status = json.loads(raw)
        self.assertFalse(status["allow_fetch"])
        self.assertEqual("output", status["output_dir"])
        self.assertNotIn("printers", status)
        self.assertIn("readiness", status)
        self.assertNotIn(str(self.cache), raw.decode("utf-8"))

    def test_capture_bridge_and_fake_crypto_route_are_removed(self) -> None:
        for path, expected in (
            ("/bridge.js", 410),
            ("/intercept", 410),
            ("/cookies", 410),
            ("/GETCRYPTARIA", 404),
        ):
            with self.subTest(path=path):
                code, body, _ = http(self.base + path)
                self.assertEqual(expected, code)
                self.assertNotIn(self.token.encode("ascii"), body)

        for path in ("/intercept", "/cookies"):
            with self.subTest(path=path, method="POST"):
                code, body, _ = http(
                    self.base + path,
                    method="POST",
                    data={"audit": "redacted"},
                )
                self.assertEqual(410, code)
                self.assertNotIn(self.token.encode("ascii"), body)

        code, _, _ = http(
            self.base + "/status",
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)

    def test_private_manifest_contains_no_raw_or_clear_ticket(self) -> None:
        self._arm()
        encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
        code, _, _ = http(self.base + "/SSO?PARAM=" + encoded)
        self.assertEqual(200, code)
        deadline = time.time() + 3
        files: list[Path] = []
        while time.time() < deadline:
            files = list((self.cache / "jobs").glob("*.json"))
            if files and "decoded_network_disabled" in files[-1].read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        self.assertTrue(files)
        manifest = files[-1]
        if os.name != "nt":
            self.assertEqual(0o600, stat.S_IMODE(manifest.stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE(self.cache.stat().st_mode))
        text = manifest.read_text(encoding="utf-8")
        self.assertNotIn(PLAIN_TICKET, text)
        self.assertNotIn("T-SYNTH", text)
        self.assertNotIn("M-SYNTH", text)
        self.assertIn(hashlib.sha256(PLAIN_TICKET.encode("ascii")).hexdigest(), text)
        public = self._jobs()[-1]
        self.assertNotIn("messages", public)
        self.assertNotIn("sha256", public["ticket"])
        self.assertNotIn("sha256", public["response"])
        self.assertNotIn("primary_sha256", public["reportx_container"])
        self.assertNotIn("additional_sha256", public["reportx_container"])
        self.assertNotIn("sha256", public["document_number"])

    def test_no_wildcard_cors(self) -> None:
        code, _, headers = http(
            self.base + "/SSO_ETC",
            headers={"Origin": "https://icert.yonsei.ac.kr"},
        )
        self.assertEqual(200, code)
        acao = headers.get("Access-Control-Allow-Origin")
        self.assertEqual("https://icert.yonsei.ac.kr", acao)

        code, _, headers = http(
            self.base + "/SSO_ETC",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(403, code)
        self.assertNotEqual("*", headers.get("Access-Control-Allow-Origin"))


class ReportXMacAgentWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="yonsei-worker-")
        self.root = Path(self.tmp.name)
        self.state = agent.AgentState(
            self.root,
            allow_fetch=True,
            token="test-token",
        )

    def tearDown(self) -> None:
        self.state.close()
        self.tmp.cleanup()

    def test_live_render_requires_both_yonsei_font_faces(self) -> None:
        with self.assertRaises(ValueError):
            agent.build_yonsei_font_map(
                Path("/missing/title.ttf"),
                None,
            )

    def test_bundled_yonsei_fonts_are_selected_and_hash_pinned(self) -> None:
        mapping = agent.build_yonsei_font_map(TITLE_FONT, BODY_FONT)
        self.assertEqual(TITLE_FONT.resolve(), mapping["*:bold"])
        self.assertEqual(BODY_FONT.resolve(), mapping["*:regular"])
        self.assertEqual(
            agent.BUNDLED_FONT_SHA256["YonseiB"],
            hashlib.sha256(TITLE_FONT.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            agent.BUNDLED_FONT_SHA256["YonseiL"],
            hashlib.sha256(BODY_FONT.read_bytes()).hexdigest(),
        )
        self.assertEqual(TITLE_FONT.resolve(), cli.find_local_yonsei_font("title"))
        self.assertEqual(BODY_FONT.resolve(), cli.find_local_yonsei_font("body"))

    def test_generic_fp3_uses_only_bundled_yonsei_fonts(self) -> None:
        mapping = agent.build_yonsei_font_map(TITLE_FONT, BODY_FONT)
        source = """\
<preparedreport>
  <previewpages><page0><title u="연세대학교"/><body u="성적증명서"/></page0></previewpages>
  <sourcepages>
    <TfrxReportPage Name="Page" PaperWidth="210" PaperHeight="297">
      <TfrxMemoView Name="Title" Left="10" Top="10" Width="100"
        Height="20" Font.Name="Arial" Font.Style="1"/>
      <TfrxMemoView Name="Body" Left="10" Top="40" Width="100"
        Height="20" Font.Name="바탕체"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary>
    <title name="Page0.Title"/><body name="Page0.Body"/>
  </dictionary>
</preparedreport>
""".encode("utf-8")
        rendered = agent.render_fp3_pdf(source, font_map=mapping)
        agent.validate_rendered_font_set(rendered.font_files, mapping)
        self.assertEqual(
            set(agent.BUNDLED_FONT_SHA256.values()),
            {digest for _, digest in rendered.font_files},
        )

    def test_rendered_font_validation_rejects_other_fonts(self) -> None:
        mapping = agent.build_yonsei_font_map(TITLE_FONT, BODY_FONT)
        with self.assertRaises(agent.FP3RenderError):
            agent.validate_rendered_font_set(
                (("Other.ttf", "0" * 64),),
                mapping,
            )

    def test_job_manifest_reports_embedded_font_hashes_without_paths(self) -> None:
        job = agent.Job("font-job", agent.utc_now(), "fixture")
        job.rendered_fonts = (
            ("연세제목.TTF", "a" * 64),
            ("연세본문.TTF", "b" * 64),
        )
        public = agent.public_job_view(job)
        self.assertEqual(
            [
                {"file": "연세제목.TTF", "sha256": "a" * 64},
                {"file": "연세본문.TTF", "sha256": "b" * 64},
            ],
            public["rendered_pdf"]["fonts"],
        )

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not Windows ACLs")
    def test_existing_private_tree_permissions_are_repaired(self) -> None:
        with tempfile.TemporaryDirectory(prefix="yonsei-permissions-") as tmp:
            root = Path(tmp) / "cache"
            jobs = root / "jobs"
            output = root / "output"
            jobs.mkdir(parents=True)
            output.mkdir()
            manifest = jobs / "legacy.json"
            artifact = output / "legacy.reportx"
            token = root / "agent.token"
            manifest.write_text("{}", encoding="utf-8")
            artifact.write_bytes(b"opaque")
            token.write_text("legacy-token", encoding="utf-8")
            for directory in (root, jobs, output):
                os.chmod(directory, 0o755)
            for path in (manifest, artifact, token):
                os.chmod(path, 0o644)

            state = agent.AgentState(
                root,
                allow_fetch=False,
                token="test-token",
            )
            try:
                for directory in (root, jobs, output):
                    self.assertEqual(
                        0o700,
                        stat.S_IMODE(directory.stat().st_mode),
                    )
                for path in (manifest, artifact, token):
                    self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            finally:
                state.close()

    @unittest.skipIf(os.name == "nt", "POSIX mode bits are not Windows ACLs")
    def test_cli_refuses_insecure_or_nonregular_token_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="yonsei-token-") as tmp:
            root = Path(tmp)
            token = root / "agent.token"
            token.write_text("test-token", encoding="utf-8")
            os.chmod(token, 0o644)
            self.assertIsNone(cli.read_token(root))

            os.chmod(token, 0o600)
            self.assertEqual("test-token", cli.read_token(root))

            token.unlink()
            token.symlink_to(root / "missing-target")
            self.assertIsNone(cli.read_token(root))

    def test_cli_reads_regular_token_on_windows_without_posix_mode_bits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="yonsei-windows-token-") as tmp:
            root = Path(tmp)
            token = root / "agent.token"
            token.write_text("test-token", encoding="utf-8")
            with mock.patch.object(cli.os, "name", "nt"):
                self.assertEqual("test-token", cli.read_token(root))

    def test_public_job_view_redacts_private_path_and_fingerprints(self) -> None:
        job = agent.Job(
            "job-public",
            agent.utc_now(),
            "test",
            ticket_sha256="a" * 64,
            response_sha256="b" * 64,
            artifact_path="/private/cache/output/job-public.pdf",
            artifact_sha256="c" * 64,
            bundle_primary_sha256="d" * 64,
            bundle_additional_sha256=("e" * 64,),
        )
        view = agent.public_job_view(job)
        self.assertEqual("job-public.pdf", view["artifact"]["path"])
        self.assertEqual("c" * 64, view["artifact"]["sha256"])
        self.assertEqual("not_available", view["rendered_pdf"]["status"])
        self.assertNotIn("sha256", view["ticket"])
        self.assertNotIn("sha256", view["response"])
        self.assertNotIn("primary_sha256", view["reportx_container"])
        self.assertNotIn("additional_sha256", view["reportx_container"])
        self.assertNotIn("messages", view)

    def test_public_reason_code_is_controlled_and_contains_no_exception_text(self) -> None:
        job = agent.Job("job-reason", agent.utc_now(), "test")
        agent.set_job_reason(job, "secret value from remote response")
        view = agent.public_job_view(job)
        self.assertEqual("protocol_failed", view["reason_code"])
        self.assertNotIn("secret", json.dumps(view))

    def test_readiness_requires_assets_fonts_and_all_live_mutation_flags(self) -> None:
        mapping = agent.build_yonsei_font_map(TITLE_FONT, BODY_FONT)
        with tempfile.TemporaryDirectory(prefix="yonsei-ready-") as tmp:
            state = agent.AgentState(
                Path(tmp),
                allow_fetch=True,
                allow_document_reservation=True,
                allow_completion_notification=False,
                token="test-token",
                font_map=mapping,
                require_original_fonts=True,
            )
            try:
                self.assertTrue(
                    state.readiness()["bundled_font_hashes_verified"]
                )
                self.assertFalse(state.readiness()["live_issue_ready"])
                state.official_assets = mock.sentinel.official_assets
                self.assertFalse(state.readiness()["live_issue_ready"])
                state.allow_completion_notification = True
                self.assertTrue(state.readiness()["live_issue_ready"])
            finally:
                state.close()

    def test_live_arm_is_rejected_before_full_readiness(self) -> None:
        server = agent.LoopbackHTTPServer(
            ("127.0.0.1", 0),
            agent.ReportXHandler,
        )
        previous_state = agent.STATE
        agent.STATE = self.state
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            code, raw, _ = http(
                f"http://127.0.0.1:{server.server_port}/arm",
                method="POST",
                data={},
                headers={"X-Agent-Token": self.state.token},
            )
            self.assertEqual(409, code)
            result = json.loads(raw)
            self.assertEqual("live_issue_not_ready", result["error"])
            self.assertFalse(result["readiness"]["live_issue_ready"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            agent.STATE = previous_state

    def test_live_origin_requires_one_shot_arm_and_preserves_correlation(self) -> None:
        mapping = agent.build_yonsei_font_map(TITLE_FONT, BODY_FONT)
        with tempfile.TemporaryDirectory(prefix="yonsei-live-arm-") as tmp:
            state = agent.AgentState(
                Path(tmp),
                allow_fetch=True,
                allow_document_reservation=True,
                allow_completion_notification=True,
                token="live-token",
                font_map=mapping,
                require_original_fonts=True,
            )
            state.official_assets = mock.sentinel.official_assets
            server = agent.LoopbackHTTPServer(
                ("127.0.0.1", 0),
                agent.ReportXHandler,
            )
            previous_state = agent.STATE
            agent.STATE = state
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            captured: list[agent.Job] = []

            def accept_without_worker(job, current_state):  # noqa: ANN001, ANN202
                captured.append(job)
                current_state.add_job(job)
                return "accepted", None

            encoded = urllib.parse.quote(PLAIN_TICKET, safe="")
            origin = {"Origin": "https://icert.yonsei.ac.kr"}
            try:
                with mock.patch.object(
                    agent,
                    "schedule_job",
                    side_effect=accept_without_worker,
                ):
                    code, _, _ = http(
                        f"http://127.0.0.1:{server.server_port}/SSO?PARAM={encoded}",
                        headers=origin,
                    )
                    self.assertEqual(401, code)

                    code, raw, _ = http(
                        f"http://127.0.0.1:{server.server_port}/arm",
                        method="POST",
                        data={},
                        headers={"X-Agent-Token": state.token},
                    )
                    self.assertEqual(200, code)
                    arm_id = json.loads(raw)["arm_id"]

                    code, _, _ = http(
                        f"http://127.0.0.1:{server.server_port}/SSO?PARAM={encoded}",
                        headers=origin,
                    )
                    self.assertEqual(200, code)
                    self.assertEqual(arm_id, captured[-1].correlation_id)

                    code, _, _ = http(
                        f"http://127.0.0.1:{server.server_port}/SSO?PARAM={encoded}",
                        headers=origin,
                    )
                    self.assertEqual(401, code)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
                state.close()
                agent.STATE = previous_state

    def test_exact_pdf_response_is_saved_unverified_and_never_auto_printed(self) -> None:
        pdf = minimal_pdf()

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/pdf"),),
                body=pdf,
            )

        job = agent.Job("job-pdf", agent.utc_now(), "test", param=PLAIN_TICKET)
        self.state.add_job(job)
        with (
            mock.patch.object(agent, "perform_request", side_effect=fake_request),
            mock.patch.object(agent, "cups_print") as print_mock,
        ):
            agent.process_job(job, self.state)
        print_mock.assert_not_called()
        self.assertEqual("server_pdf_saved_unverified", job.status)
        self.assertEqual("not_performed", job.verification)
        self.assertEqual(hashlib.sha256(pdf).hexdigest(), job.artifact_sha256)
        assert job.artifact_path is not None
        self.assertEqual(pdf, Path(job.artifact_path).read_bytes())
        self.assertFalse(job.printed)

    def test_recent_identical_pdf_job_reports_reused_success(self) -> None:
        pdf = minimal_pdf()
        digest = hashlib.sha256(pdf).hexdigest()
        destination = self.state.out_dir / "existing-identical.pdf"
        agent.secure_write_bytes(destination, pdf)
        existing = agent.Job(
            "existing-identical",
            agent.utc_now(),
            "test",
            finished_at=agent.utc_now(),
            status="server_pdf_saved_unverified",
            response_sha256=digest,
            artifact_path=str(destination),
            artifact_sha256=digest,
            artifact_kind="server_pdf_unverified",
        )
        self.state.add_job(existing)

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/pdf"),),
                body=pdf,
            )

        reused = agent.Job(
            "reused-identical",
            agent.utc_now(),
            "test",
            param=PLAIN_TICKET,
        )
        self.state.add_job(reused)
        with mock.patch.object(agent, "perform_request", side_effect=fake_request):
            agent.process_job(reused, self.state)
        self.assertEqual("server_document_reused_unverified", reused.status)
        self.assertIsNone(reused.reason_code)
        self.assertEqual(existing.id, reused.duplicate_of_job_id)
        self.assertEqual(existing.artifact_path, reused.artifact_path)
        self.assertTrue(agent.job_is_settled(reused))

    def test_opaque_server_report_is_not_mislabeled_pdf(self) -> None:
        report = b"REPORTX-OPAQUE-SERVER-BYTES"

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/octet-stream"),),
                body=report,
            )

        job = agent.Job("job-report", agent.utc_now(), "test", param=PLAIN_TICKET)
        self.state.add_job(job)
        with mock.patch.object(agent, "perform_request", side_effect=fake_request):
            agent.process_job(job, self.state)
        self.assertEqual("server_report_saved_unrendered", job.status)
        self.assertEqual("server_report_unrendered", job.artifact_kind)
        assert job.artifact_path is not None
        self.assertTrue(job.artifact_path.endswith(".reportx"))
        self.assertEqual(report, Path(job.artifact_path).read_bytes())

    def test_recovered_report_container_is_decoded_in_memory_only(self) -> None:
        primary = b"PRIMARY-RENDERER-STREAM"
        additional = (b"PART-ONE", b"PART-TWO")
        response_body = synthetic_document_response(primary, additional)

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/octet-stream"),),
                body=response_body,
            )

        job = agent.Job("job-container", agent.utc_now(), "test", param=PLAIN_TICKET)
        self.state.add_job(job)
        with mock.patch.object(agent, "perform_request", side_effect=fake_request):
            agent.process_job(job, self.state)

        self.assertEqual("server_report_decoded_unrendered", job.status)
        self.assertEqual("server_report_decoded_unrendered", job.artifact_kind)
        self.assertEqual(len(primary), job.bundle_primary_length)
        self.assertEqual(hashlib.sha256(primary).hexdigest(), job.bundle_primary_sha256)
        self.assertEqual(
            tuple(hashlib.sha256(item).hexdigest() for item in additional),
            job.bundle_additional_sha256,
        )
        assert job.artifact_path is not None
        self.assertEqual(response_body, Path(job.artifact_path).read_bytes())
        self.assertEqual(
            [Path(job.artifact_path).name],
            [path.name for path in self.state.out_dir.iterdir()],
        )

    def test_recovered_fp3_is_rendered_to_separate_unverified_pdf(self) -> None:
        response_body = synthetic_document_response(MINIMAL_FP3, ())

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/octet-stream"),),
                body=response_body,
            )

        job = agent.Job("job-rendered", agent.utc_now(), "test", param=PLAIN_TICKET)
        self.state.add_job(job)
        with (
            mock.patch.object(agent, "perform_request", side_effect=fake_request),
            mock.patch.object(agent, "cups_print") as print_mock,
        ):
            agent.process_job(job, self.state)

        print_mock.assert_not_called()
        self.assertEqual(
            "server_report_rendered_pdf_unverified",
            job.status,
        )
        self.assertEqual("server_report_response", job.artifact_kind)
        self.assertEqual(1, job.rendered_page_count)
        self.assertEqual(1, job.rendered_object_count)
        self.assertIsNotNone(job.rendered_pdf_path)
        self.assertIsNotNone(job.rendered_pdf_sha256)
        assert job.rendered_pdf_path is not None
        rendered = Path(job.rendered_pdf_path).read_bytes()
        self.assertTrue(agent.is_pdf_container(rendered))
        self.assertEqual(
            hashlib.sha256(rendered).hexdigest(),
            job.rendered_pdf_sha256,
        )
        self.assertEqual("not_performed", job.verification)
        self.assertFalse(job.print_attempted)
        self.assertTrue(job.rendered_replay_verified)

    def test_full_render_preflight_rejects_before_document_number_request(
        self,
    ) -> None:
        response_body = synthetic_document_response(MINIMAL_FP3, ())

        def fake_request(action, **_kwargs):  # noqa: ANN001, ANN202
            return NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/octet-stream"),),
                body=response_body,
            )

        self.state.allow_document_reservation = True
        self.state.official_assets = mock.sentinel.official_assets
        bindings = mock.Mock(
            pictures={},
            text={},
            official_empty_pictures=(),
        )
        job = agent.Job(
            "job-preflight-render",
            agent.utc_now(),
            "test",
            param=PLAIN_TICKET,
        )
        self.state.add_job(job)
        with (
            mock.patch.object(agent, "perform_request", side_effect=fake_request) as request,
            mock.patch.object(agent, "_runtime_profile_required", return_value=True),
            mock.patch.object(
                agent,
                "build_runtime_bindings",
                side_effect=(
                    agent.DocumentNumberRequired("serial required"),
                    bindings,
                ),
            ),
            mock.patch.object(
                agent,
                "_render_fp3_pdf_replayed",
                side_effect=agent.FP3RenderError("duplicate page object"),
            ),
            mock.patch.object(
                self.state,
                "begin_document_reservation",
                wraps=self.state.begin_document_reservation,
            ) as reserve,
        ):
            agent.process_job(job, self.state)

        self.assertEqual(1, request.call_count)
        reserve.assert_not_called()
        self.assertEqual("preflight_rejected", job.document_number_status)
        self.assertEqual(
            "document_number_preflight_render_rejected",
            job.reason_code,
        )
        self.assertFalse(list(self.state.reservations_dir.iterdir()))

    def test_document_number_reservation_guard_is_durable_and_no_retry(
        self,
    ) -> None:
        digest = hashlib.sha256(b"one-ticket").hexdigest()
        first = agent.Job(
            "job-reserve-first",
            agent.utc_now(),
            "test",
            ticket_sha256=digest,
        )
        second = agent.Job(
            "job-reserve-second",
            agent.utc_now(),
            "test",
            ticket_sha256=digest,
        )
        self.assertTrue(self.state.begin_document_reservation(first))
        self.state.finish_document_reservation(first, "reserved")
        self.assertFalse(self.state.begin_document_reservation(second))
        guard = self.state.reservations_dir / f"{digest}.json"
        if os.name != "nt":
            self.assertEqual(0o600, stat.S_IMODE(guard.stat().st_mode))
        self.assertEqual(
            "reserved",
            json.loads(guard.read_text(encoding="utf-8"))["status"],
        )

    def test_semantic_guard_collision_leaves_no_false_ticket_guard(self) -> None:
        response_digest = hashlib.sha256(b"same-server-document").hexdigest()
        ticket_digest = hashlib.sha256(b"new-ticket").hexdigest()
        semantic = self.state.reservations_dir / f"response-{response_digest}.json"
        agent.secure_write_text(
            semantic,
            json.dumps(
                {
                    "schema": "yonsei-reportx-reservation-guard/v1",
                    "job_id": "existing-job",
                    "status": "started_unknown_until_response",
                }
            ),
        )
        job = agent.Job(
            "new-job",
            agent.utc_now(),
            "test",
            ticket_sha256=ticket_digest,
            response_sha256=response_digest,
        )
        self.assertFalse(self.state.begin_document_reservation(job))
        self.assertFalse(
            (self.state.reservations_dir / f"{ticket_digest}.json").exists()
        )
        self.assertTrue(semantic.exists())

    def test_prepared_guards_are_recoverable_but_started_guard_is_not(self) -> None:
        response_digest = hashlib.sha256(b"recoverable-response").hexdigest()
        ticket_digest = hashlib.sha256(b"recoverable-ticket").hexdigest()
        job = agent.Job(
            "recoverable-job",
            agent.utc_now(),
            "test",
            ticket_sha256=ticket_digest,
            response_sha256=response_digest,
        )
        prepared = json.dumps(
            {
                "schema": "yonsei-reportx-reservation-guard/v1",
                "job_id": "crashed-before-request",
                "status": "prepared_not_requested",
            }
        )
        ticket_path = self.state.reservations_dir / f"{ticket_digest}.json"
        response_path = (
            self.state.reservations_dir / f"response-{response_digest}.json"
        )
        agent.secure_write_text(ticket_path, prepared)
        agent.secure_write_text(response_path, prepared)

        self.assertTrue(self.state.begin_document_reservation(job))
        self.assertEqual(
            "started_unknown_until_response",
            json.loads(ticket_path.read_text(encoding="utf-8"))["status"],
        )
        self.assertEqual(
            "started_unknown_until_response",
            json.loads(response_path.read_text(encoding="utf-8"))["status"],
        )
        second = agent.Job(
            "started-guard-job",
            agent.utc_now(),
            "test",
            ticket_sha256=ticket_digest,
            response_sha256=response_digest,
        )
        self.assertFalse(self.state.begin_document_reservation(second))

    def test_completed_semantic_guard_expires_for_later_explicit_issue(self) -> None:
        response_digest = hashlib.sha256(b"completed-response").hexdigest()
        first = agent.Job(
            "completed-first",
            agent.utc_now(),
            "test",
            ticket_sha256=hashlib.sha256(b"first-ticket").hexdigest(),
            response_sha256=response_digest,
        )
        self.assertEqual((True, None), self.state.claim_server_response(first))
        self.assertTrue(self.state.begin_document_reservation(first))
        self.state.finish_document_reservation(first, "completion_notified")
        semantic = (
            self.state.reservations_dir / f"response-{response_digest}.json"
        )
        guard = json.loads(semantic.read_text(encoding="utf-8"))
        self.assertEqual("completion_notified", guard["status"])
        guard["updated_at"] = (
            datetime.now(timezone.utc)
            - timedelta(seconds=agent.SEMANTIC_DUPLICATE_TTL_SECONDS + 1)
        ).isoformat()
        agent.secure_write_text(semantic, json.dumps(guard))
        self.state.response_claims.clear()

        later = agent.Job(
            "completed-later",
            agent.utc_now(),
            "test",
            ticket_sha256=hashlib.sha256(b"later-ticket").hexdigest(),
            response_sha256=response_digest,
        )
        self.assertEqual((True, None), self.state.claim_server_response(later))
        self.assertFalse(semantic.exists())
        self.assertTrue(self.state.begin_document_reservation(later))

    def test_active_duplicate_coalesces_and_recent_pdf_is_reused(self) -> None:
        digest = hashlib.sha256(b"stable-server-document").hexdigest()
        active = agent.Job(
            "active-response",
            agent.utc_now(),
            "test",
            response_sha256=digest,
        )
        duplicate = agent.Job(
            "duplicate-response",
            agent.utc_now(),
            "test",
            response_sha256=digest,
        )
        self.assertEqual((True, None), self.state.claim_server_response(active))
        self.assertEqual(
            (False, active.id),
            self.state.claim_server_response(duplicate),
        )

        self.state.response_claims.clear()
        pdf = minimal_pdf()
        destination = self.state.out_dir / "completed.pdf"
        agent.secure_write_bytes(destination, pdf)
        completed = agent.Job(
            "completed-response",
            agent.utc_now(),
            "test",
            finished_at=agent.utc_now(),
            status="server_pdf_saved_unverified",
            response_sha256=digest,
            artifact_path=str(destination),
            artifact_sha256=hashlib.sha256(pdf).hexdigest(),
            artifact_kind="server_pdf_unverified",
        )
        self.state.add_job(completed)
        recent = agent.Job(
            "recent-response",
            agent.utc_now(),
            "test",
            response_sha256=digest,
        )
        self.assertEqual(
            (False, completed.id),
            self.state.claim_server_response(recent),
        )
        self.assertTrue(self.state.reuse_completed_response(recent, completed.id))
        self.assertEqual(completed.artifact_path, recent.artifact_path)

        completed.finished_at = (
            datetime.now(timezone.utc)
            - timedelta(seconds=agent.SEMANTIC_DUPLICATE_TTL_SECONDS + 1)
        ).isoformat()
        later = agent.Job(
            "later-explicit-response",
            agent.utc_now(),
            "test",
            response_sha256=digest,
        )
        self.assertEqual((True, None), self.state.claim_server_response(later))

    def test_restart_restores_jobs_and_settles_interrupted_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="yonsei-restart-") as tmp:
            root = Path(tmp)
            first = agent.AgentState(root, allow_fetch=True, token="test-token")
            interrupted = agent.Job(
                "interrupted-job",
                agent.utc_now(),
                "test",
                status="requesting",
                ticket_sha256=hashlib.sha256(b"ticket").hexdigest(),
            )
            first.add_job(interrupted)
            first.close()

            restored = agent.AgentState(root, allow_fetch=True, token="test-token")
            try:
                loaded = restored.jobs[interrupted.id]
                self.assertEqual("protocol_failed", loaded.status)
                self.assertEqual(
                    "agent_restarted_during_job",
                    loaded.reason_code,
                )
                self.assertTrue(agent.job_is_settled(loaded))
            finally:
                restored.close()

    def test_unexpected_worker_error_settles_and_future_is_observed(self) -> None:
        ticket_hash = hashlib.sha256(PLAIN_TICKET.encode("ascii")).hexdigest()
        job = agent.Job(
            "job-worker-error",
            agent.utc_now(),
            "test",
            param=PLAIN_TICKET,
            ticket_sha256=ticket_hash,
        )
        with mock.patch.object(
            agent,
            "process_job",
            side_effect=RuntimeError("private worker detail"),
        ):
            admission, _ = agent.schedule_job(job, self.state)
            self.assertEqual("accepted", admission)
            settled = self.state.wait_for_job(job.id, 2)
        assert settled is not None
        self.assertEqual("protocol_failed", settled.status)
        self.assertEqual("unexpected_worker_error", settled.reason_code)
        self.assertNotIn("private worker detail", json.dumps(agent.public_job_view(settled)))
        deadline = time.time() + 1
        while time.time() < deadline and job.id in self.state.worker_futures:
            time.sleep(0.01)
        self.assertNotIn(job.id, self.state.worker_futures)

    def test_pdf_check_is_container_only(self) -> None:
        html = b"<!DOCTYPE html><html><body>login</body></html>"
        self.assertFalse(agent.is_pdf_container(html))
        self.assertFalse(
            agent.is_pdf_container(
                b"%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\n"
                b"startxref\n0\n%%EOF\n"
            )
        )
        pdf = minimal_pdf()
        self.assertTrue(agent.is_pdf_container(pdf))
        self.assertFalse(agent.is_pdf_container(pdf + b"\x00"))
        self.assertFalse(agent.is_pdf_container(pdf + b"<html>appended</html>"))

    def test_transport_opener_explicitly_disables_environment_proxy(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"HTTPS_PROXY": "http://proxy.invalid:9999"},
            clear=False,
        ):
            environment_opener = urllib.request.build_opener(
                agent.NoRedirectHandler()
            )
            opener = agent.build_transport_opener()
        environment_proxy_handlers = [
            handler
            for handler in environment_opener.handlers
            if isinstance(handler, urllib.request.ProxyHandler)
        ]
        direct_proxy_handlers = [
            handler
            for handler in opener.handlers
            if isinstance(handler, urllib.request.ProxyHandler)
        ]
        self.assertTrue(environment_proxy_handlers)
        self.assertEqual([], direct_proxy_handlers)

    def test_cli_control_opener_disables_proxy_before_adding_token(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://proxy.invalid:9999",
                "NO_PROXY": "",
            },
            clear=False,
        ):
            environment_opener = urllib.request.build_opener()
            opener = cli.build_control_opener()
        environment_proxy_handlers = [
            handler
            for handler in environment_opener.handlers
            if isinstance(handler, urllib.request.ProxyHandler)
        ]
        direct_proxy_handlers = [
            handler
            for handler in opener.handlers
            if isinstance(handler, urllib.request.ProxyHandler)
        ]
        self.assertTrue(environment_proxy_handlers)
        self.assertEqual([], direct_proxy_handlers)

    def _printable_job(self, job_id: str = "job-print") -> tuple[agent.Job, str]:
        pdf = minimal_pdf()
        destination = self.state.out_dir / f"{job_id}.pdf"
        agent.secure_write_bytes(destination, pdf)
        digest = hashlib.sha256(pdf).hexdigest()
        job = agent.Job(
            job_id,
            agent.utc_now(),
            "test",
            status="server_pdf_saved_unverified",
            artifact_path=str(destination),
            artifact_sha256=digest,
            artifact_kind="server_pdf_unverified",
        )
        self.state.add_job(job)
        return job, digest

    def test_concurrent_physical_print_is_reserved_exactly_once(self) -> None:
        job, digest = self._printable_job()
        entered = threading.Event()
        release = threading.Event()

        def slow_print(*_args):  # noqa: ANN002, ANN202
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            return True, "submitted"

        with (
            mock.patch.object(agent, "list_cups_printers", return_value=["TEST"]),
            mock.patch.object(agent, "cups_print", side_effect=slow_print) as print_mock,
        ):
            first_result: list[tuple[int, dict]] = []

            def first_submit() -> None:
                first_result.append(
                    agent.submit_print_job(
                        self.state,
                        job_id=job.id,
                        printer="TEST",
                        expected_sha256=digest,
                        confirmed=True,
                    )
                )

            worker = threading.Thread(target=first_submit)
            worker.start()
            self.assertTrue(entered.wait(timeout=2))
            second_status, second = agent.submit_print_job(
                self.state,
                job_id=job.id,
                printer="TEST",
                expected_sha256=digest,
                confirmed=True,
            )
            release.set()
            worker.join(timeout=2)

        self.assertEqual(409, second_status)
        self.assertEqual("print_already_attempted", second["error"])
        self.assertEqual([(200, {"ok": True, "status": "submitted"})], first_result)
        self.assertEqual(1, print_mock.call_count)
        self.assertTrue(job.print_attempted)
        self.assertTrue(job.printed)

    def test_ambiguous_print_result_is_not_retryable(self) -> None:
        job, digest = self._printable_job("job-unknown")
        with (
            mock.patch.object(agent, "list_cups_printers", return_value=["TEST"]),
            mock.patch.object(
                agent,
                "cups_print",
                return_value=(False, "unknown_timeout_after_submit"),
            ) as print_mock,
        ):
            first_status, first = agent.submit_print_job(
                self.state,
                job_id=job.id,
                printer="TEST",
                expected_sha256=digest,
                confirmed=True,
            )
            second_status, second = agent.submit_print_job(
                self.state,
                job_id=job.id,
                printer="TEST",
                expected_sha256=digest,
                confirmed=True,
            )

        self.assertEqual(409, first_status)
        self.assertEqual("unknown_timeout_after_submit", first["status"])
        self.assertEqual(409, second_status)
        self.assertEqual("print_already_attempted", second["error"])
        self.assertEqual(1, print_mock.call_count)
        self.assertTrue(job.print_attempted)
        self.assertFalse(job.printed)

    def test_rendered_compatibility_pdf_requires_explicit_print(self) -> None:
        pdf = minimal_pdf()
        destination = self.state.out_dir / "job-rendered-print.rendered.pdf"
        agent.secure_write_bytes(destination, pdf)
        digest = hashlib.sha256(pdf).hexdigest()
        job = agent.Job(
            "job-rendered-print",
            agent.utc_now(),
            "test",
            status="server_report_rendered_pdf_unverified",
            artifact_kind="server_report_response",
            rendered_pdf_path=str(destination),
            rendered_pdf_sha256=digest,
        )
        self.state.add_job(job)
        with (
            mock.patch.object(agent, "list_cups_printers", return_value=["TEST"]),
            mock.patch.object(
                agent,
                "cups_print",
                return_value=(True, "submitted"),
            ) as print_mock,
        ):
            rejected, _ = agent.submit_print_job(
                self.state,
                job_id=job.id,
                printer="TEST",
                expected_sha256=digest,
                confirmed=False,
            )
            accepted, result = agent.submit_print_job(
                self.state,
                job_id=job.id,
                printer="TEST",
                expected_sha256=digest,
                confirmed=True,
            )
        self.assertEqual(400, rejected)
        self.assertEqual(200, accepted)
        self.assertTrue(result["ok"])
        print_mock.assert_called_once_with(destination, "TEST")

    def test_submission_queue_is_bounded_before_job_persistence(self) -> None:
        ticket_hash = hashlib.sha256(PLAIN_TICKET.encode("ascii")).hexdigest()
        job = agent.Job(
            "job-busy",
            agent.utc_now(),
            "test",
            param=PLAIN_TICKET,
            ticket_length=len(PLAIN_TICKET),
            ticket_sha256=ticket_hash,
        )
        self.state.pending_jobs = agent.MAX_PENDING_JOBS
        admission, existing = agent.schedule_job(job, self.state)
        self.assertEqual("busy", admission)
        self.assertIsNone(existing)
        self.assertNotIn(job.id, self.state.jobs)
        self.assertFalse((self.state.jobs_dir / f"{job.id}.json").exists())


if __name__ == "__main__":
    unittest.main()
