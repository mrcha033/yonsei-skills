import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "audit-yonsei-course-plan"
    / "scripts"
    / "audit_course_plan.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


class AuditYonseiCoursePlanSkillTests(unittest.TestCase):
    def test_reports_credit_and_day_off_violations(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "credits": 3,
                        "campus": "sinchon",
                        "meetings": [{"day": "fri", "start": "10:00", "end": "11:00"}],
                    }
                ],
                "constraints": {"min_credits": 6, "days_off": ["fri"]},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-course-plan-audit/v1")
        self.assertEqual(output["total_credits"], 3.0)
        self.assertEqual(
            {item["type"] for item in output["violations"]},
            {"below-min-credits", "day-off-violation"},
        )
        self.assertFalse(output["constraints_met"])

    def test_missing_credits_makes_summary_incomplete(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "credits": None,
                        "campus": "sinchon",
                        "meetings": [{"day": "mon", "start": "10:00", "end": "11:00"}],
                    }
                ]
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertFalse(output["constraints_met"])
        self.assertEqual(output["unknowns"][0]["type"], "missing-credits")

    def test_rejects_non_finite_json_numbers(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "credits": float("nan"),
                        "campus": "sinchon",
                        "meetings": [
                            {"day": "mon", "start": "10:00", "end": "11:00"}
                        ],
                    }
                ]
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "invalid-json-number")

    def test_meeting_campus_override_is_checked(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "credits": 3,
                        "campus": "sinchon",
                        "meetings": [
                            {
                                "day": "mon",
                                "start": "10:00",
                                "end": "11:00",
                                "campus": "international",
                            }
                        ],
                    }
                ],
                "constraints": {"allowed_campuses": ["sinchon"]},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["constraints_met"])
        self.assertEqual(output["violations"][0]["type"], "campus-not-allowed")
        self.assertEqual(output["violations"][0]["campus"], "international")


if __name__ == "__main__":
    unittest.main()
