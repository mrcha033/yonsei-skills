import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_groupware_approvals.py"


class ListGroupwareApprovalsTests(unittest.TestCase):
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

    def test_lists_action_required_approval_without_mutation(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "excel_transcribed_json",
            "records": [
                {
                    "approval_id": "GA-1",
                    "workflow_type": "electronic_approval",
                    "document_type": "expense_report",
                    "title": "Travel expense",
                    "status": "pending",
                    "my_action_required": True,
                },
                {
                    "approval_id": "GA-2",
                    "workflow_type": "e_sop",
                    "document_type": "procedure",
                    "title": "Lab procedure",
                    "status": "completed",
                    "my_action_required": False,
                },
            ],
        }
        completed, result = self.run_script(payload, "--action-required-only")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual([record["approval_id"] for record in result["records"]], ["GA-1"])
        self.assertEqual(result["mutations_performed"], [])

    def test_rejects_recipient_address(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "records": [
                {
                    "approval_id": "GA-1",
                    "workflow_type": "official_document_outbound",
                    "document_type": "official_letter",
                    "title": "Notice",
                    "status": "pending",
                    "my_action_required": True,
                    "recipient_email": "private@example.invalid",
                }
            ],
        }
        completed, result = self.run_script(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_record_fields")


if __name__ == "__main__":
    unittest.main()
