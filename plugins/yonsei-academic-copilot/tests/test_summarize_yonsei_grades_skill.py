import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "summarize-yonsei-grades"
    / "scripts"
    / "summarize_grades.py"
)


def run_script(payload, *, allow_nan=True):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False, allow_nan=allow_nan),
        text=True,
        capture_output=True,
        check=False,
    )


class SummarizeYonseiGradesSkillTests(unittest.TestCase):
    def test_calculates_term_gpa_and_earned_credits(self):
        result = run_script(
            {
                "captured_at": "2026-07-27T09:00:00+09:00",
                "term": "2026-1",
                "displayed_gpa": 3.8,
                "grades": [
                    {
                        "학정번호": "A",
                        "교과목명": "A",
                        "학점": 3,
                        "성적": "A+",
                    },
                    {
                        "학정번호": "B",
                        "교과목명": "B",
                        "학점": 3,
                        "성적": "B+",
                    },
                    {
                        "학정번호": "C",
                        "교과목명": "C",
                        "학점": 1,
                        "성적": "P",
                    },
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-academic-grade-summary/v1")
        self.assertEqual(output["calculated_gpa"], 3.8)
        self.assertEqual(output["gpa_credits"], 6.0)
        self.assertEqual(output["earned_credits"], 7.0)
        self.assertFalse(output["displayed_gpa_discrepancy"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertFalse(output["provenance"]["official_transcript_verified"])

    def test_pending_grade_makes_final_gpa_incomplete(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "grades": [
                    {
                        "course_code": "A",
                        "title": "A",
                        "credits": 3,
                        "grade": "A0",
                    },
                    {
                        "course_code": "B",
                        "title": "B",
                        "credits": 3,
                        "grade": "I",
                    },
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertIsNone(output["calculated_gpa"])
        self.assertEqual(output["known_final_gpa"], 4.0)
        self.assertEqual(output["pending_course_ids"], ["B"])

    def test_unknown_grade_fails_closed(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "grades": [
                    {
                        "course_code": "A",
                        "title": "A",
                        "credits": 3,
                        "grade": "PASS?",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "unknown-grade")

    def test_non_finite_credit_fails_closed(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "grades": [
                    {
                        "course_code": "A",
                        "title": "A",
                        "credits": float("nan"),
                        "grade": "A0",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "invalid-json-number")


if __name__ == "__main__":
    unittest.main()
