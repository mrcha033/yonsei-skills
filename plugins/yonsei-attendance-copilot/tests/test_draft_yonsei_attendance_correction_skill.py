import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "draft-yonsei-attendance-correction"
    / "scripts"
    / "draft_correction.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def valid_payload():
    return {
        "captured_at": "2026-07-27T09:00:00+09:00",
        "correction": {
            "course_code": "A",
            "course_title": "자료구조",
            "class_date": "2026-03-05",
            "recorded_status": "결석",
            "requested_status": "출석",
            "reason": "수업에 참석했으나 결석으로 표시됩니다.",
            "evidence": ["당일 수업 제출물"],
            "recipient": "담당 교강사",
        },
    }


class DraftYonseiAttendanceCorrectionSkillTests(unittest.TestCase):
    def test_creates_deterministic_unsent_draft(self):
        first = run_script(valid_payload())
        second = run_script(valid_payload())
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        output = json.loads(first.stdout)
        self.assertEqual(
            output["schema"],
            "yonsei-attendance-correction-draft/v1",
        )
        self.assertEqual(output["draft_id"], json.loads(second.stdout)["draft_id"])
        self.assertTrue(output["draft_only"])
        self.assertFalse(output["submitted"])
        self.assertTrue(output["ready_for_user_review"])
        self.assertIn("전송되지 않은 검토용 초안", output["draft"]["message"])
        self.assertFalse(output["actions"]["official_record_changed"])
        self.assertFalse(output["provenance"]["live_system_queried"])

    def test_missing_evidence_and_recipient_remain_review_items(self):
        payload = valid_payload()
        payload["correction"]["evidence"] = []
        payload["correction"].pop("recipient")
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["ready_for_user_review"])
        self.assertEqual(
            set(output["missing_items"]),
            {"official-recipient-or-submission-path", "evidence-description"},
        )
        self.assertFalse(output["submitted"])

    def test_same_recorded_and_requested_status_fails_closed(self):
        payload = valid_payload()
        payload["correction"]["requested_status"] = "결석"
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "status-not-changed")

    def test_submission_flag_is_rejected(self):
        payload = valid_payload()
        payload["submit"] = True
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "submission-not-supported")
        self.assertNotIn("official_record_changed\": true", result.stdout)


if __name__ == "__main__":
    unittest.main()
