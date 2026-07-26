from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "packages" / "yonsei-service-runtime" / "yonsei_service.py"


def load_runtime():
    spec = importlib.util.spec_from_file_location("yonsei_service_test", RUNTIME)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = load_runtime()

    def test_catalog_is_valid(self) -> None:
        catalog = json.loads(
            (ROOT / "packages" / "yonsei-service-runtime" / "services.json").read_text(
                encoding="utf-8"
            )
        )
        self.runtime.validate_catalog(catalog)

    def test_redaction_removes_query_and_fragment(self) -> None:
        self.assertEqual(
            "https://example.yonsei.ac.kr/path",
            self.runtime.redact_url(
                "https://example.yonsei.ac.kr/path?requestTimeStr=secret#fragment"
            ),
        )

    def test_redirect_allowlist(self) -> None:
        self.assertTrue(
            self.runtime.is_allowed_redirect(
                "https://infra.yonsei.ac.kr/sauth/SSOLegacy.do"
            )
        )
        self.assertFalse(
            self.runtime.is_allowed_redirect(
                "http://infra.yonsei.ac.kr/sauth/SSOLegacy.do"
            )
        )
        self.assertFalse(
            self.runtime.is_allowed_redirect("https://yonsei.example/steal")
        )

    def test_notice_parser_self_test(self) -> None:
        script = (
            ROOT
            / "plugins"
            / "yonsei-notice-monitor"
            / "skills"
            / "yonsei-notice-monitor"
            / "scripts"
            / "fetch_notices.py"
        )
        completed = subprocess.run(
            [sys.executable, str(script), "--self-test"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
