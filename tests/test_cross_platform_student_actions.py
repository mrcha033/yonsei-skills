from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHUTTLE = load(
    "shuttle_platform_support",
    ROOT
    / "plugins/yonsei-shuttle-booking/skills/book-yonsei-shuttle/scripts"
    / "platform_support.py",
)
SPACE = load(
    "space_platform_support",
    ROOT
    / "plugins/yonsei-space-reservation/skills/submit-yonsei-space-request/scripts"
    / "platform_support.py",
)
CERTIFICATE = load(
    "certificate_issue_platform",
    ROOT
    / "plugins/yonsei-certificate-assistant/skills/issue-yonsei-certificate/scripts"
    / "prepare_certificate_issue.py",
)
DIAGNOSE = load(
    "certificate_environment_platform",
    ROOT
    / "plugins/yonsei-certificate-assistant/skills/yonsei-certificate-assistant/scripts"
    / "diagnose_print_env.py",
)


class CrossPlatformStudentActionTests(unittest.TestCase):
    def test_browser_actions_support_three_desktop_platforms(self) -> None:
        for system in ("windows", "macos", "linux"):
            with self.subTest(system=system):
                for module in (SHUTTLE, SPACE):
                    result = module.capabilities(system)
                    self.assertTrue(result["supported"])
                    self.assertEqual(
                        "persistent-desktop-browser",
                        result["execution"],
                    )
                    self.assertFalse(result["student_cli_required"])

    def test_certificate_selects_native_windows_path_for_physical_print(self) -> None:
        result = CERTIFICATE.run(
            {
                "certificate_type": "재학증명서",
                "purpose": "제출",
                "desired_result": "physical_print",
                "printer": "Campus Printer",
                "login_state": "connected",
            },
            system="windows",
        )
        self.assertEqual(
            "official-windows-reportx-physical-print",
            result["issuance_path"],
        )
        self.assertEqual("free-print-physical-print", result["result_scope"])
        self.assertFalse(result["student_cli_required"])

    def test_certificate_pdf_uses_local_path_on_all_platforms(self) -> None:
        for system in ("windows", "macos", "linux"):
            with self.subTest(system=system):
                result = CERTIFICATE.run(
                    {
                        "certificate_type": "성적증명서",
                        "purpose": "제출",
                        "include_rank": False,
                        "include_conversion": False,
                        "login_state": "connected",
                    },
                    system=system,
                )
                self.assertEqual(
                    "local-reportx-compatible-virtual-pdf-print",
                    result["issuance_path"],
                )
                self.assertEqual(
                    "free-print-pdf-virtual-print",
                    result["result_scope"],
                )

    def test_certificate_diagnostic_names_linux_local_agent(self) -> None:
        result = DIAGNOSE.recommended_path(
            system="Linux",
            reportx_listening=False,
            physical=[],
            virtual=[],
        )
        self.assertEqual("start-local-agent", result["id"])
        self.assertIn("Linux", result["summary"])

    def test_certificate_pdf_diagnostic_skips_slow_printer_enumeration(self) -> None:
        with mock.patch.object(
            DIAGNOSE,
            "list_printers",
            side_effect=AssertionError("printer discovery must be opt-in"),
        ):
            result = DIAGNOSE.diagnose()
        self.assertFalse(result["printers"]["checked"])
        self.assertEqual([], result["printers"]["all"])


if __name__ == "__main__":
    unittest.main()
