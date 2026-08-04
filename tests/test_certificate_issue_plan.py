import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "plugins" / "yonsei-certificate-assistant" / "skills" / "issue-yonsei-certificate" / "scripts" / "prepare_certificate_issue.py"


class CertificateIssuePlanTests(unittest.TestCase):
    def run_script(self, payload, platform="macos"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--platform", platform],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_prepares_single_copy_free_print(self):
        result = self.run_script(
            {
                "certificate_type": "재학증명서",
                "language": "ko",
                "copies": 1,
                "purpose": "제출",
                "desired_result": "reviewed_pdf",
                "login_state": "connected",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["ready"])
        self.assertEqual(output["platform"], "macos")
        self.assertEqual(
            output["issuance_path"],
            "local-reportx-compatible-virtual-pdf-print",
        )
        self.assertEqual(output["print_target"], "pdf-virtual-printer")
        self.assertEqual(output["result_scope"], "free-print-pdf-virtual-print")
        self.assertEqual(output["document_number_reservation"], "one-shot-after-confirmation")
        self.assertFalse(output["paid_electronic_certificate"])

    def test_windows_physical_print_uses_official_native_reportx(self):
        result = self.run_script(
            {
                "certificate_type": "재학증명서",
                "language": "ko",
                "copies": 1,
                "purpose": "제출",
                "desired_result": "physical_print",
                "printer": "Campus Printer",
                "login_state": "connected",
            },
            platform="windows",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["issuance_path"],
            "official-windows-reportx-physical-print",
        )
        self.assertEqual(output["result_scope"], "free-print-physical-print")

    def test_windows_pdf_uses_local_compatibility_printer(self):
        result = self.run_script(
            {
                "certificate_type": "재학증명서",
                "language": "ko",
                "copies": 1,
                "purpose": "개인 보관",
                "desired_result": "reviewed_pdf",
                "login_state": "connected",
            },
            platform="windows",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["issuance_path"],
            "local-reportx-compatible-virtual-pdf-print",
        )
        self.assertEqual(output["result_scope"], "free-print-pdf-virtual-print")

    def test_rejects_user_supplied_certificate_identity(self):
        result = self.run_script(
            {
                "certificate_type": "재학증명서",
                "purpose": "제출",
                "student_name": "수정값",
                "login_state": "connected",
            }
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "certificate-content-not-accepted")

    def test_transcript_collects_all_options_and_purpose_is_optional(self):
        result = self.run_script(
            {
                "certificate_type": "transcript",
                "language": "en",
                "copies": 1,
                "output": "pdf",
                "include_rank": False,
                "include_conversion": True,
                "conversion_scale": "4.5",
                "login_state": "connected",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-certificate-issue-plan/v2")
        self.assertTrue(output["ready"])
        self.assertIsNone(output["purpose"])
        self.assertEqual(output["review"]["certificate_label"], "성적증명서")
        self.assertFalse(output["review"]["include_rank"])
        self.assertEqual(output["review"]["conversion_scale"], "4.5")
        self.assertEqual(output["missing_user_fields"], [])

    def test_transcript_reports_missing_choices_in_one_batch(self):
        result = self.run_script(
            {
                "certificate_type": "성적증명서",
                "language": "en",
                "login_state": "unknown",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["ready"])
        self.assertEqual(
            output["missing_user_fields"],
            ["include_rank", "include_conversion"],
        )
        self.assertEqual(output["runtime_checks"]["login_state"], "unknown")

    def test_rejects_unobserved_conversion_scale_before_browser_work(self):
        result = self.run_script(
            {
                "certificate_type": "transcript",
                "language": "en",
                "include_rank": False,
                "include_conversion": True,
                "conversion_scale": "4.3",
                "login_state": "connected",
            }
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["error"]["code"],
            "unsupported-conversion-scale",
        )


if __name__ == "__main__":
    unittest.main()
