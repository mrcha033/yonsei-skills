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

    def navigate(self, url, wait=0):
        self.navigated.append(url)
        self.url = url

    def login_state(self):
        return "connected" if self.connected else "login_required"

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
        opened = []
        with mock.patch.object(icert_print, "open_url", side_effect=lambda url: opened.append(url) or True):
            self.assertEqual(icert_print.cmd_open(argparse.Namespace()), 0)
        self.assertEqual(opened, [icert_print.PORTAL])
        self.assertNotIn("https://icert.yonsei.ac.kr/", opened)

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


if __name__ == "__main__":
    unittest.main()
