import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "search_groupware_documents.py"


class SearchGroupwareDocumentsTests(unittest.TestCase):
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

    def base_payload(self):
        return {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "export_scope": "explicit_user_supplied_export",
            "records": [
                {
                    "document_id": "D-1",
                    "document_type": "official_document_inbound",
                    "title": "Research agreement notice",
                    "status": "received",
                    "originating_unit": "Research Office",
                    "keywords": ["agreement", "research"],
                    "summary": "Review deadline and responsible unit.",
                }
            ],
        }

    def test_searches_only_whitelisted_export(self):
        completed, result = self.run_script(self.base_payload(), "--query", "agreement")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["match_count"], 1)
        self.assertIn("title", result["matches"][0]["matched_fields"])
        self.assertFalse(result["live_data"])

    def test_requires_explicit_export_scope(self):
        payload = self.base_payload()
        del payload["export_scope"]
        completed, result = self.run_script(payload, "--query", "agreement")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "explicit_export_required")

    def test_rejects_message_body(self):
        payload = self.base_payload()
        payload["records"][0]["message_body"] = "unbounded sensitive content"
        completed, result = self.run_script(payload, "--query", "agreement")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_record_fields")


if __name__ == "__main__":
    unittest.main()
