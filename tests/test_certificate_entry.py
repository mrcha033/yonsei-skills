import argparse
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE_SCRIPT_DIR = (
    ROOT
    / "plugins"
    / "yonsei-certificate-assistant"
    / "skills"
    / "yonsei-certificate-assistant"
    / "scripts"
)
BRIDGE_ROOT = (
    ROOT
    / "plugins"
    / "yonsei-student-companion"
    / "runtime"
)
sys.path.insert(0, str(CERTIFICATE_SCRIPT_DIR))
sys.path.insert(0, str(BRIDGE_ROOT))

from yonsei_bridge.bridge import BridgeError, PageSnapshot, YonseiBridge  # noqa: E402


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CERTIFICATE_SCRIPT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


icert_print = load_script("icert_print_entry_test", "icert_print.py")
diagnose_print_env = load_script("diagnose_print_env_entry_test", "diagnose_print_env.py")


class FakeRuntime:
    def target_ids(self):
        return {"portal"}


class FakeCertificatePage:
    def __init__(self, *, connected: bool = True, verification: bool = False):
        self.connected = connected
        self.verification = verification
        self.url = "https://portal.yonsei.ac.kr/ui/index.html"
        self.clicked = []
        self.navigated = []
        self.href_clicked = []
        self.login_waits = 0

    def navigate(self, url, wait=0):
        self.navigated.append(url)
        self.url = url

    def login_state(self):
        return "connected" if self.connected else "login_required"

    def wait_for_login_state(self, **_arguments):
        self.login_waits += 1
        return self.login_state()

    def click_href_fragment(self, fragment):
        self.href_clicked.append(fragment)
        return True

    def click_text(self, text, exact=True):
        self.clicked.append((text, exact))
        if text == "인터넷증명서":
            self.url = (
                "https://icert.yonsei.ac.kr/servlet/YSID?COMMAND=VERIFYOK"
                if self.verification
                else "https://icert.yonsei.ac.kr/servlet/YSID?COMMAND=ISSUE"
            )
        return True

    def fill_label(self, label, value):
        return True

    def snapshot(self):
        return PageSnapshot(
            url=self.url,
            title="원본대조확인" if self.verification else "인터넷즉시발급",
            text=(
                "증명서 원본확인 문서번호"
                if self.verification
                else "인터넷즉시발급 재학증명서"
            ),
            grids=[],
            buttons=[],
            inputs=[],
            links=[],
        )


class CertificateEntryTests(unittest.TestCase):
    def test_open_starts_only_from_authenticated_portal_route(self):
        from io import StringIO

        output = StringIO()
        with mock.patch("sys.stdout", output):
            self.assertEqual(icert_print.cmd_open(argparse.Namespace()), 0)
        handoff = json.loads(output.getvalue())
        self.assertEqual(handoff["browser"]["entry_url"], icert_print.PORTAL)
        self.assertEqual(handoff["browser"]["controller"], "Codex Computer Use")
        self.assertFalse(handoff["browser"]["cli_browser_launch_performed"])

    def test_start_emits_computer_use_handoff_without_browser_launch(self):
        from io import StringIO

        output = StringIO()
        args = argparse.Namespace(dir=str(icert_print.DEFAULT_DIR), port=65432)
        with mock.patch.object(
            icert_print,
            "ensure_agent_ready",
            return_value={"mode": "reused"},
        ), mock.patch("sys.stdout", output):
            self.assertEqual(icert_print.cmd_start(args), 0)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[0]["browser"]["controller"], "Codex Computer Use")
        self.assertFalse(events[0]["browser"]["cli_browser_launch_performed"])
        self.assertEqual(events[-1]["state"], "prewarmed")

    def test_inline_request_json_is_not_misread_as_a_path(self):
        request = icert_print.read_json_input('{"certificate_type":"transcript"}')
        self.assertEqual(request["certificate_type"], "transcript")

    def test_issue_uses_one_command_start_deadline_for_correlated_wait(self):
        args = argparse.Namespace(
            request="{}",
            output_path="result.pdf",
            confirm=True,
            timeout=99.0,
            dir=str(icert_print.DEFAULT_DIR),
            port=65432,
        )
        plan = {
            "ready": True,
            "missing_user_fields": [],
            "output": "pdf",
            "computer_use_request": {},
        }
        arm_id = "a" * 24
        with mock.patch.object(
            icert_print, "prepare_issue_plan", return_value=plan
        ), mock.patch.object(
            icert_print, "require_prewarmed_agent", return_value={"mode": "reused"}
        ), mock.patch.object(
            icert_print, "job_list", return_value=[{"id": "old"}]
        ), mock.patch.object(
            icert_print, "read_token", return_value="token"
        ), mock.patch.object(
            icert_print, "http_json", return_value={"armed": True, "arm_id": arm_id}
        ), mock.patch.object(
            icert_print,
            "wait_for_correlated_job",
            return_value=(2, {"id": "ours", "status": "protocol_failed"}),
        ) as waited, mock.patch.object(
            icert_print, "emit_json"
        ), mock.patch.object(
            icert_print.time, "monotonic", side_effect=[100.0, 110.0, 111.0]
        ):
            self.assertEqual(icert_print.cmd_issue(args), 2)
        waited.assert_called_once_with(
            args,
            arm_id,
            {"old"},
            deadline=155.0,
        )

    def test_doctor_not_running_is_setup_ready_not_failure(self):
        from io import StringIO

        output = StringIO()
        args = argparse.Namespace(dir=str(icert_print.DEFAULT_DIR), port=65432)
        with mock.patch.object(icert_print.subprocess, "run"), mock.patch.object(
            icert_print, "agent_up", return_value=False
        ), mock.patch.object(icert_print, "read_token", return_value=None), mock.patch(
            "sys.stdout", output
        ):
            self.assertEqual(icert_print.cmd_doctor(args), 0)
        self.assertIn('"state": "not_running"', output.getvalue())
        self.assertIn("--notify-print-completion", output.getvalue())

    def test_waiter_follows_exact_id_and_rejects_non_pdf_terminal_state(self):
        rendered = {
            "id": "new-1",
            "status": "server_report_rendered_pdf_unverified",
            "document_number": {
                "status": "reserved",
                "completion_notified": True,
                "completion_status": "notified",
            },
        }
        self.assertEqual(icert_print.terminal_job_result(rendered), 0)
        self.assertEqual(
            icert_print.terminal_job_result(
                {"id": "new-2", "status": "server_report_decoded_unrendered"}
            ),
            2,
        )
        self.assertIsNone(
            icert_print.terminal_job_result(
                {"id": "new-3", "status": "requesting"}
            )
        )
        reused = {
            "id": "new-4",
            "status": "server_document_reused_unverified",
            "rendered_pdf": {"path": "reused.pdf", "sha256": "a" * 64},
            "document_number": {
                "status": "reserved",
                "completion_notified": True,
                "completion_status": "notified",
            },
        }
        self.assertEqual(icert_print.terminal_job_result(reused), 0)

    def test_wait_for_new_job_pins_first_id(self):
        args = argparse.Namespace()
        states = [
            [{"id": "old", "status": "server_report_rendered_pdf_unverified"}],
            [{"id": "old"}, {"id": "new", "status": "requesting"}],
            [
                {"id": "old"},
                {
                    "id": "new",
                    "status": "server_report_rendered_pdf_unverified",
                    "document_number": {
                        "status": "reserved",
                        "completion_notified": True,
                        "completion_status": "notified",
                    },
                },
            ],
        ]
        with mock.patch.object(icert_print, "job_list", side_effect=states), mock.patch.object(
            icert_print.time, "sleep"
        ):
            code, job = icert_print.wait_for_new_job(
                args,
                {"old"},
                deadline=icert_print.time.monotonic() + 2,
            )
        self.assertEqual(code, 0)
        self.assertEqual(job["id"], "new")

    def test_correlated_waiter_ignores_unrelated_new_jobs(self):
        args = argparse.Namespace()
        correlated = {
            "id": "ours",
            "correlation_id": "a" * 24,
            "status": "server_report_rendered_pdf_unverified",
            "document_number": {
                "status": "reserved",
                "completion_notified": True,
                "completion_status": "notified",
            },
        }
        with mock.patch.object(
            icert_print,
            "job_list",
            return_value=[correlated],
        ) as listed:
            code, job = icert_print.wait_for_correlated_job(
                args,
                "a" * 24,
                {"old", "unrelated-new"},
                deadline=icert_print.time.monotonic() + 1,
            )
        self.assertEqual(code, 0)
        self.assertEqual(job["id"], "ours")
        listed.assert_called_once_with(args, correlation_id="a" * 24)

    def test_export_refuses_different_existing_destination(self):
        import hashlib
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache"
            output = cache / "output"
            output.mkdir(parents=True)
            body = b"%PDF-1.4\n%%EOF\n"
            digest = hashlib.sha256(body).hexdigest()
            (output / "job.pdf").write_bytes(body)
            destination = Path(directory) / "result.pdf"
            destination.write_bytes(b"different")
            job = {
                "rendered_pdf": {"path": "job.pdf", "sha256": digest},
                "artifact": {},
            }
            with self.assertRaisesRegex(RuntimeError, "refusing overwrite"):
                icert_print.export_job_pdf(job, cache, destination)

    def test_diagnostic_names_portal_as_certificate_entry(self):
        self.assertEqual(
            diagnose_print_env.CERTIFICATE_ENTRY,
            "https://portal.yonsei.ac.kr/ui/index.html",
        )

    def test_catalog_does_not_advertise_broken_icert_root_as_entry(self):
        catalog = json.loads(
            (ROOT / "packages" / "yonsei-service-runtime" / "services.json").read_text()
        )
        certificate = catalog["services"]["certificate"]
        self.assertEqual(
            certificate["entry_url"],
            "https://portal.yonsei.ac.kr/ui/index.html",
        )
        self.assertNotIn("direct_url", certificate)
        self.assertIn("COMMAND=VERIFY", certificate["portal_catalog_url"])

    def test_bridge_uses_portal_menu_without_premature_document_selection(self):
        page = FakeCertificatePage()
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.runtime = FakeRuntime()
        bridge.page = page
        bridge.connection = None
        bridge.selections = {}
        result = bridge.documents(document_type="enrollment")
        self.assertEqual(
            page.navigated,
            ["https://portal.yonsei.ac.kr/ui/index.html"],
        )
        self.assertEqual(page.clicked[0], ("인터넷증명서", True))
        self.assertNotIn(("재학증명서", False), page.clicked)
        self.assertEqual(result["state"], "official_page_ready")

    def test_bridge_rejects_original_verification_as_issuance(self):
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.runtime = FakeRuntime()
        bridge.page = FakeCertificatePage(verification=True)
        bridge.connection = None
        bridge.selections = {}
        with self.assertRaisesRegex(BridgeError, "original verification"):
            bridge.documents(document_type="transcript")

    def test_bridge_stops_at_login_boundary(self):
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.runtime = FakeRuntime()
        bridge.page = FakeCertificatePage(connected=False)
        bridge.connection = None
        bridge.selections = {}
        with self.assertRaisesRegex(BridgeError, "login_required"):
            bridge.documents(document_type="enrollment")
        self.assertEqual(bridge.page.login_waits, 1)

    def test_confirmed_transcript_arms_and_clicks_print_exactly_once(self):
        page = FakeCertificatePage()
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.runtime = FakeRuntime()
        bridge.page = page
        bridge.connection = None
        bridge.selections = {}
        with mock.patch.object(
            bridge,
            "_start_reportx_agent",
            return_value={"live_issue_ready": True},
        ), mock.patch.object(
            bridge,
            "_select_certificate_for_free_print",
            return_value={"selected": True, "source": "existing_exact_basket"},
        ), mock.patch.object(
            bridge,
            "_arm_reportx_agent",
            return_value="a" * 24,
        ) as armed, mock.patch.object(
            bridge,
            "_wait_reportx_result",
            return_value={"verified": True, "status": "completed"},
        ) as waited, mock.patch("yonsei_bridge.bridge.time.sleep"):
            result = bridge.documents(
                document_type="transcript",
                action="issue",
                output_format="pdf",
                language="en",
                copies=1,
                include_rank=False,
                gpa_conversion=True,
                gpa_scale="4.5",
                confirmed=True,
            )
        armed.assert_called_once_with()
        waited.assert_called_once_with("a" * 24)
        self.assertEqual(page.href_clicked.count("goPrint"), 1)
        self.assertEqual(result["official_output_clicks"], 1)
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(page.login_waits, 1)


if __name__ == "__main__":
    unittest.main()
