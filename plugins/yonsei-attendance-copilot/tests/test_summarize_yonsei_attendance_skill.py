import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "summarize-yonsei-attendance"
    / "scripts"
    / "summarize_attendance.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class SummarizeYonseiAttendanceSkillTests(unittest.TestCase):
    def test_summarizes_overall_and_per_course_totals(self):
        result = run_script(
            {
                "captured_at": "2026-07-27T09:00:00+09:00",
                "records": [
                    {
                        "학정번호": "A",
                        "교과목명": "자료구조",
                        "수업일": "2026-03-05",
                        "출결상태": "출석",
                    },
                    {
                        "학정번호": "A",
                        "교과목명": "자료구조",
                        "수업일": "2026-03-12",
                        "출결상태": "지각",
                    },
                    {
                        "course_code": "B",
                        "course_title": "알고리즘",
                        "class_date": "2026-03-06",
                        "status": "absent",
                    },
                ],
                "student_number": "not-preserved",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-attendance-summary/v1")
        self.assertEqual(output["totals"]["present"], 1)
        self.assertEqual(output["totals"]["late"], 1)
        self.assertEqual(output["totals"]["absent"], 1)
        self.assertEqual(output["attention_count"], 2)
        self.assertEqual(output["by_course"][0]["record_count"], 2)
        self.assertFalse(output["actions"]["checkin_performed"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertNotIn("not-preserved", result.stdout)

    def test_unknown_status_fails_closed(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "records": [
                    {
                        "course_code": "A",
                        "course_title": "자료구조",
                        "class_date": "2026-03-05",
                        "status": "확인필요",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "unknown-attendance-status")

    def test_duplicate_course_date_session_fails_closed(self):
        row = {
            "course_code": "A",
            "course_title": "자료구조",
            "class_date": "2026-03-05",
            "status": "출석",
        }
        result = run_script(
            {"captured_at": "2026-07-27", "records": [row, row]}
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "duplicate-attendance-record")

    def test_rejects_checkin_field_without_echoing_value(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "records": [],
                "attendance_code": "123456",
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["error"]["code"],
            "credential-or-checkin-field-not-allowed",
        )
        self.assertNotIn("123456", result.stdout)


if __name__ == "__main__":
    unittest.main()
