import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "build-yonsei-timetable"
    / "scripts"
    / "build_timetable.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def course(course_id, code, day, start, end, campus="sinchon"):
    return {
        "id": course_id,
        "course_code": code,
        "title": code,
        "credits": 3,
        "meetings": [
            {"day": day, "start": start, "end": end, "campus": campus}
        ],
    }


class BuildYonseiTimetableSkillTests(unittest.TestCase):
    def test_selects_non_overlapping_section(self):
        result = run_script(
            {
                "courses": [
                    course("A-01", "A", "mon", "10:00", "11:00"),
                    course("A-02", "A", "tue", "10:00", "11:00"),
                    course("B-01", "B", "mon", "10:30", "12:00"),
                ],
                "requirements": [
                    {"id": "a", "course_ids": ["A-01", "A-02"]},
                    {"id": "b", "course_ids": ["B-01"]},
                ],
                "constraints": {"min_credits": 6, "max_credits": 6},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["feasible"])
        self.assertEqual(output["solutions"][0]["course_ids"], ["A-02", "B-01"])
        self.assertEqual(output["registration_mutation"], "disabled")

    def test_rejects_unknown_cross_campus_travel(self):
        result = run_script(
            {
                "courses": [
                    course("A-01", "A", "mon", "10:00", "11:00", "sinchon"),
                    course("B-01", "B", "mon", "12:00", "13:00", "international"),
                ],
                "requirements": [
                    {"id": "a", "course_ids": ["A-01"]},
                    {"id": "b", "course_ids": ["B-01"]},
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["feasible"])
        self.assertEqual(output["rejection_counts"]["missing-travel:sinchon->international"], 1)

    def test_rejects_non_finite_json_numbers(self):
        payload = {
            "courses": [
                course("A-01", "A", "mon", "10:00", "11:00"),
            ],
            "requirements": [{"id": "a", "course_ids": ["A-01"]}],
        }
        payload["courses"][0]["credits"] = float("inf")
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "invalid-json-number")


if __name__ == "__main__":
    unittest.main()
