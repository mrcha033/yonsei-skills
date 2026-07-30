import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = (
    ROOT
    / "plugins"
    / "yonsei-student-companion"
    / "runtime"
    / "yonsei_bridge"
)
sys.path.insert(0, str(BRIDGE_DIR.parent))

from yonsei_bridge.bridge import (  # noqa: E402
    BrowserPage,
    PageSnapshot,
    SPACE_REQUEST_FIELDS,
    YonseiBridge,
)
from yonsei_bridge.mcp_server import TOOLS  # noqa: E402
from yonsei_bridge.router import INTENTS, StudentRouter, friendly_error  # noqa: E402


class YonseiBridgeTests(unittest.TestCase):
    def test_one_student_router_covers_all_student_intents(self):
        self.assertEqual(
            {tool["name"] for tool in TOOLS},
            {"yonsei_bridge_connect", "yonsei_student"},
        )
        self.assertEqual(
            set(INTENTS),
            {
                "today",
                "applications",
                "courses",
                "graduation",
                "shuttle",
                "space",
                "dorm",
                "documents",
                "learnus",
                "attendance",
            },
        )
        router = next(tool for tool in TOOLS if tool["name"] == "yonsei_student")
        request_properties = router["inputSchema"]["properties"]["request"]["properties"]
        self.assertIn("headcount", request_properties)
        self.assertIn("purpose", request_properties)
        self.assertNotIn("row_terms", request_properties)
        self.assertNotIn("fields", request_properties)

    def test_structured_rows_preserve_headers_and_unlabelled_rows(self):
        snapshot = PageSnapshot(
            url="https://underwood1.yonsei.ac.kr/",
            title="Underwood",
            text="",
            grids=[
                {
                    "headers": ["과목", "마일리지"],
                    "rows": [["컴퓨팅", "20"]],
                    "lines": [],
                },
                {
                    "headers": [],
                    "rows": [["신촌", "09:00", "3석"]],
                    "lines": [],
                },
            ],
            buttons=[],
            inputs=[],
            links=[],
        )
        rows = YonseiBridge._rows(snapshot)
        self.assertEqual(rows[0]["fields"], {"과목": "컴퓨팅", "마일리지": "20"})
        self.assertEqual(rows[1]["fields"]["column_2"], "09:00")

    def test_bundled_certificate_runtime_is_discoverable(self):
        script = YonseiBridge._find_script("icert_print.py")
        self.assertEqual(script.name, "icert_print.py")
        self.assertTrue((script.parent.parent / "assets" / "fonts" / "연세제목.TTF").is_file())
        self.assertTrue((script.parent.parent / "assets" / "fonts" / "연세본문.TTF").is_file())

    def test_candidates_get_opaque_selection_ids(self):
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        rows = [
            {
                "grid": 0,
                "row": 0,
                "fields": {"출발": "신촌", "시간": "09:00"},
                "text": "신촌 | 09:00",
            }
        ]
        remembered = bridge._remember_rows("shuttle", rows, context="2026-08-01")
        selection_id = remembered[0]["selection_id"]
        self.assertEqual(len(selection_id), 12)
        self.assertEqual(
            bridge._selection_terms(selection_id, "shuttle"),
            ["신촌", "09:00"],
        )

    def test_space_request_uses_student_language_keys(self):
        page = BrowserPage.__new__(BrowserPage)
        observed = []

        def fill(label, value):
            observed.append((label, value))
            return label in {"이용일자", "사용인원", "사용목적"}

        page.fill_label = fill
        result = page.fill_student_request(
            {
                "date": "2026-08-01",
                "headcount": 15,
                "purpose": "스터디",
            },
            SPACE_REQUEST_FIELDS,
        )
        self.assertEqual(set(result), {"date", "headcount", "purpose"})
        self.assertTrue(all(item["filled"] for item in result.values()))
        self.assertNotIn("aria-label", str(observed))

    def test_router_returns_one_primary_result(self):
        class FakeBridge:
            def shuttle(self, **arguments):
                self.arguments = arguments
                return {
                    "action": "search",
                    "candidates": [
                        {
                            "selection_id": "abc123",
                            "text": "신촌 | 09:00 | 3석",
                        }
                    ],
                    "reservation_performed": False,
                }

        fake = FakeBridge()
        result = StudentRouter(fake).run(
            intent="shuttle",
            action="search",
            request={
                "origin": "신촌",
                "destination": "국제캠퍼스",
                "date": "2026-08-01",
                "preferred_time": "09:00",
            },
        )
        self.assertEqual(result["schema"], "yonsei-student-result/v1")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            result["primary_result"]["candidates"][0]["selection_id"],
            "abc123",
        )
        self.assertNotIn("row_terms", fake.arguments)

    def test_errors_are_student_friendly(self):
        missing = friendly_error(ValueError("missing:origin,date"))
        self.assertEqual(missing["status"], "more_information_needed")
        self.assertEqual(missing["missing_information"], ["origin", "date"])
        timeout = friendly_error(ValueError("Timed out waiting for official page"))
        self.assertEqual(timeout["status"], "temporary_failure")
        self.assertNotIn("Timed out", timeout["message"])

    def test_mcp_initializes_and_lists_tools(self):
        process = subprocess.Popen(
            [sys.executable, str(BRIDGE_DIR / "mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        assert process.stdin is not None and process.stdout is not None
        try:
            for request in (
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ):
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
            initialized = json.loads(process.stdout.readline())
            listed = json.loads(process.stdout.readline())
            self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.4.0")
            self.assertEqual(len(listed["result"]["tools"]), 2)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
