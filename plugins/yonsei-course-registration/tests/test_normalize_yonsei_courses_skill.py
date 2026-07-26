import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "normalize-yonsei-courses"
    / "scripts"
    / "normalize_courses.py"
)
BUILD_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "build-yonsei-timetable"
    / "scripts"
    / "build_timetable.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class NormalizeYonseiCoursesSkillTests(unittest.TestCase):
    def test_normalizes_korean_fields_days_and_campus(self):
        result = run_script(
            {
                "courses": [
                    {
                        "학정번호": "yca1001",
                        "분반": "01",
                        "교과목명": "글쓰기",
                        "학점": "3",
                        "강의시간": "월수 10:00-11:15",
                        "캠퍼스": "신촌",
                    }
                ]
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        course = output["courses"][0]
        self.assertEqual(course["id"], "YCA1001-01")
        self.assertEqual(course["campus"], "sinchon")
        self.assertEqual([item["day"] for item in course["meetings"]], ["mon", "wed"])
        self.assertFalse(output["provenance"]["official_catalogue_fetched"])

    def test_rejects_unmapped_period_notation_with_json_error(self):
        result = run_script(
            {
                "courses": [
                    {
                        "course_code": "YCA1001",
                        "title": "글쓰기",
                        "meetings": "월1,2",
                    }
                ]
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "unsupported-period-notation")

    def test_rejects_non_finite_credit_strings(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                result = run_script(
                    {
                        "courses": [
                            {
                                "course_code": "YCA1001",
                                "title": "글쓰기",
                                "credits": value,
                                "meetings": "월 10:00-11:00",
                                "campus": "신촌",
                            }
                        ]
                    }
                )
                self.assertEqual(result.returncode, 2)
                output = json.loads(result.stdout)
                self.assertEqual(output["error"]["code"], "invalid-credits")
                self.assertNotIn(value, result.stdout)

    def test_preserves_planning_envelope_for_direct_build(self):
        result = run_script(
            {
                "courses": [
                    {
                        "학정번호": "A",
                        "분반": "01",
                        "교과목명": "A",
                        "학점": 3,
                        "강의시간": "월 10:00-11:00",
                        "캠퍼스": "신촌",
                    },
                    {
                        "학정번호": "B",
                        "분반": "01",
                        "교과목명": "B",
                        "학점": 3,
                        "강의시간": "화 10:00-11:00",
                        "캠퍼스": "신촌",
                    },
                ],
                "requirements": [
                    {"id": "b", "course_ids": ["B-01"], "required": True}
                ],
                "fixed_course_ids": ["A-01"],
                "constraints": {"min_credits": 6, "max_credits": 6},
                "preferences": {"course_weights": {"B-01": 1}},
                "max_solutions": 2,
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        normalized = json.loads(result.stdout)
        self.assertEqual(normalized["fixed_course_ids"], ["A-01"])
        built = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            input=json.dumps(normalized),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        output = json.loads(built.stdout)
        self.assertTrue(output["feasible"])
        self.assertEqual(output["solutions"][0]["course_ids"], ["A-01", "B-01"])


if __name__ == "__main__":
    unittest.main()
