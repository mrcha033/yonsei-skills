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
            }
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "certificate-content-not-accepted")


if __name__ == "__main__":
    unittest.main()
