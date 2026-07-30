import importlib.util
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

from yonsei_bridge.bridge import PageSnapshot, YonseiBridge  # noqa: E402
from yonsei_bridge.mcp_server import TOOLS  # noqa: E402


class YonseiBridgeTests(unittest.TestCase):
    def test_all_eight_student_commands_are_exposed(self):
        names = {tool["name"] for tool in TOOLS}
        self.assertTrue(
            {
                "yonsei_today",
                "yonsei_academic_applications",
                "yonsei_mileage_history",
                "yonsei_graduation_teaching",
                "yonsei_shuttle",
                "yonsei_space_dorm",
                "yonsei_documents",
                "yonsei_learnus_attendance",
            }.issubset(names)
        )

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
            self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.3.0")
            self.assertEqual(len(listed["result"]["tools"]), 9)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()


if __name__ == "__main__":
    unittest.main()
