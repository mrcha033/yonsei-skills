import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "draft_groupware_message.py"


class DraftGroupwareMessageTests(unittest.TestCase):
    def run_script(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", handle.name],
                check=False,
                capture_output=True,
                text=True,
            )
        return completed, json.loads(completed.stdout)

    def base_payload(self):
        return {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "draft": {
                "channel": "official_document",
                "recipient_label": "Research Office",
                "subject": "Request for review",
                "purpose": "Please review the supplied project summary.",
                "facts": ["The internal deadline is 2026-07-31.", "No attachment is included."],
                "requested_action": "Reply with corrections.",
                "deadline": "2026-07-30",
                "sender_unit": "Project Team",
            },
        }

    def test_creates_review_only_draft(self):
        completed, result = self.run_script(self.base_payload())
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(result["requires_human_review"])
        self.assertFalse(result["recipient_resolved"])
        self.assertFalse(result["send_performed"])
        self.assertFalse(result["submit_performed"])
        self.assertEqual(result["mutations_performed"], [])

    def test_rejects_phone_number_field(self):
        payload = self.base_payload()
        payload["draft"]["phone_number"] = "010-0000-0000"
        completed, result = self.run_script(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_draft_fields")

    def test_rejects_send_flag(self):
        payload = self.base_payload()
        payload["draft"]["send"] = True
        completed, result = self.run_script(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_draft_fields")


if __name__ == "__main__":
    unittest.main()
