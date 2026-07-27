import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_erp_requests.py"


class ListErpRequestsTests(unittest.TestCase):
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

    def test_filters_and_marks_result_offline(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "excel_transcribed_json",
            "exported_at": "2026-07-27T10:00:00+09:00",
            "records": [
                {
                    "request_id": "R-1",
                    "category": "finance",
                    "title": "Travel reimbursement",
                    "status": "submitted",
                    "requesting_unit": "Research Unit",
                    "amount": 120000,
                    "currency": "KRW",
                },
                {
                    "request_id": "R-2",
                    "category": "facilities",
                    "title": "Room repair",
                    "status": "completed",
                },
            ],
        }
        completed, result = self.run_script(payload, "--category", "finance")
        self.assertEqual(completed.returncode, 0)
        self.assertFalse(result["live_data"])
        self.assertEqual([record["request_id"] for record in result["records"]], ["R-1"])
        self.assertEqual(result["mutations_performed"], [])

    def test_rejects_non_whitelisted_sensitive_field(self):
        payload = {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "records": [
                {
                    "request_id": "R-1",
                    "category": "personnel",
                    "title": "Personnel request",
                    "status": "in_review",
                    "employee_id": "secret",
                }
            ],
        }
        completed, result = self.run_script(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_record_fields")


if __name__ == "__main__":
    unittest.main()
