import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "find-yonsei-attendance-discrepancies"
    / "scripts"
    / "find_discrepancies.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class FindYonseiAttendanceDiscrepanciesSkillTests(unittest.TestCase):
    def test_finds_explicit_mismatch_and_draft_readiness(self):
        result = run_script(
            {
                "captured_at": "2026-07-27T09:00:00+09:00",
                "records": [
                    {
                        "course_code": "A",
                        "course_title": "자료구조",
                        "class_date": "2026-03-05",
                        "recorded_status": "결석",
                        "expected_status": "출석",
                        "reason": "수업에 참석했으나 결석으로 표시됩니다.",
                        "evidence": ["당일 수업 제출물"],
                    },
                    {
                        "course_code": "B",
                        "course_title": "알고리즘",
                        "class_date": "2026-03-06",
                        "recorded_status": "출석",
                        "reviewed": True,
                    },
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["schema"],
            "yonsei-attendance-discrepancy-report/v1",
        )
        self.assertEqual(output["discrepancy_count"], 1)
        self.assertEqual(output["ready_for_draft_count"], 1)
        self.assertTrue(output["review_complete"])
        self.assertFalse(output["no_discrepancies_found"])
        self.assertFalse(output["actions"]["presence_inferred"])

    def test_unreviewed_rows_prevent_clean_verdict(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "records": [
                    {
                        "course_code": "A",
                        "course_title": "자료구조",
                        "class_date": "2026-03-05",
                        "recorded_status": "출석",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["review_complete"])
        self.assertFalse(output["no_discrepancies_found"])
        self.assertEqual(len(output["unknowns"]), 1)

    def test_user_dispute_without_requested_status_is_not_draft_ready(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "records": [
                    {
                        "course_code": "A",
                        "course_title": "자료구조",
                        "class_date": "2026-03-05",
                        "recorded_status": "결석",
                        "user_disputed": True,
                        "reason": "검토가 필요합니다.",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["discrepancy_count"], 1)
        self.assertEqual(output["ready_for_draft_count"], 0)
        self.assertFalse(output["discrepancies"][0]["ready_for_draft"])

    def test_rejects_location_evidence_as_presence_inference(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "records": [],
                "location": {"latitude": 37.0, "longitude": 126.0},
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["error"]["code"],
            "credential-or-presence-field-not-allowed",
        )


if __name__ == "__main__":
    unittest.main()
