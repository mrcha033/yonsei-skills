import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "draft-yri-change"
    / "scripts"
    / "draft_yri_change.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class DraftYriChangeSkillTests(unittest.TestCase):
    def payload(self):
        return {
            "captured_at": "2026-07-27",
            "owner_scope": "self",
            "change": {
                "requested_action": "request-modification",
                "record": {
                    "record_id": "YRI-1",
                    "type": "논문",
                    "title": "Old title",
                },
                "before": {"title": "Old title", "issn": None},
                "after": {"title": "Correct title", "issn": "1234-5678"},
                "reason": "원문 메타데이터와 일치하도록 정정 요청",
                "attachments": ["publisher-metadata.pdf"],
            },
        }

    def test_builds_reviewable_draft_without_submission(self):
        result = run_script(self.payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-yri-change-draft/v1")
        self.assertEqual(
            [change["field"] for change in output["changes"]],
            ["issn", "title"],
        )
        self.assertTrue(output["draft_only"])
        self.assertTrue(output["requires_user_review"])
        self.assertFalse(output["writes_performed"])
        self.assertFalse(output["submitted"])

    def test_no_difference_fails_closed(self):
        payload = self.payload()
        payload["change"]["after"] = payload["change"]["before"]
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "no-change")

    def test_system_controlled_or_unknown_field_is_rejected(self):
        payload = self.payload()
        payload["change"]["before"] = {"approval_status": "검토중"}
        payload["change"]["after"] = {"approval_status": "승인"}
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["error"]["code"],
            "unsupported-change-field",
        )

    def test_submission_directive_is_rejected(self):
        payload = self.payload()
        payload["change"]["submit"] = True
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "execution-directive-not-allowed")
        self.assertFalse(output["submitted"])


if __name__ == "__main__":
    unittest.main()
