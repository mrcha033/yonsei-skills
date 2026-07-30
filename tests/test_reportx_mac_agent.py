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

    def _arm(self) -> None:
        code, raw, _ = http(
            self.base + "/arm",
            method="POST",
            data={},
            headers={"X-Agent-Token": self.token},
        )
        self.assertEqual(200, code)
        self.assertTrue(json.loads(raw)["armed"])

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

    def test_exact_icert_origin_can_submit_without_arm(self) -> None:
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
        self.assertEqual(0o600, stat.S_IMODE(guard.stat().st_mode))
        self.assertEqual(
            "reserved",
            json.loads(guard.read_text(encoding="utf-8"))["status"],
        )

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
