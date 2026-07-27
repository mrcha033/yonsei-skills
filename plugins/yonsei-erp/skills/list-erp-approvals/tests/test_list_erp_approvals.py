import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_erp_approvals.py"


class ListErpApprovalsTests(unittest.TestCase):
    def run_script(self, payload, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", handle.name, *args],
                check=False,
                capture_output=True,
                text=True,
            )
        return completed, json.loads(completed.stdout)

    def test_lists_only_action_required_records(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "records": [
                {
                    "approval_id": "A-1",
                    "category": "budget",
                    "title": "Budget transfer",
                    "status": "pending",
                    "my_action_required": True,
                },
                {
                    "approval_id": "A-2",
                    "category": "purchasing",
                    "title": "Purchase request",
                    "status": "approved",
                    "my_action_required": False,
                },
            ],
        }
        completed, result = self.run_script(payload, "--action-required-only")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual([record["approval_id"] for record in result["records"]], ["A-1"])
        self.assertEqual(result["mutations_performed"], [])

    def test_rejects_comments_outside_whitelist(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "excel_transcribed_json",
            "records": [
                {
                    "approval_id": "A-1",
                    "category": "personnel",
                    "title": "Personnel action",
                    "status": "pending",
                    "my_action_required": True,
                    "private_comment": "sensitive",
                }
            ],
        }
        completed, result = self.run_script(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_record_fields")


if __name__ == "__main__":
    unittest.main()
