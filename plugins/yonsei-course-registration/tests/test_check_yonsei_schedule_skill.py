import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "check-yonsei-schedule"
    / "scripts"
    / "check_schedule.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


class CheckYonseiScheduleSkillTests(unittest.TestCase):
    def test_finds_overlap(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "meetings": [
                            {"day": "mon", "start": "10:00", "end": "11:00", "campus": "sinchon"}
                        ],
                    },
                    {
                        "id": "B-01",
                        "course_code": "B",
                        "meetings": [
                            {"day": "mon", "start": "10:30", "end": "12:00", "campus": "sinchon"}
                        ],
                    },
                ]
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["conflict_free"])
        self.assertEqual(output["conflicts"][0]["type"], "time-overlap")

    def test_cross_campus_without_duration_is_unknown_not_pass(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "meetings": [
                            {"day": "mon", "start": "10:00", "end": "11:00", "campus": "sinchon"}
                        ],
                    },
                    {
                        "id": "B-01",
                        "course_code": "B",
                        "meetings": [
                            {
                                "day": "mon",
                                "start": "12:00",
                                "end": "13:00",
                                "campus": "international",
                            }
                        ],
                    },
                ]
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNone(output["conflict_free"])
        self.assertTrue(output["no_detected_conflicts"])
        self.assertFalse(output["complete"])
        self.assertEqual(output["unknowns"][0]["type"], "travel-duration-missing")

    def test_rejects_boolean_clock_minutes(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "meetings": [
                            {
                                "day": "mon",
                                "start_minute": True,
                                "end_minute": 60,
                                "campus": "sinchon",
                            }
                        ],
                    }
                ]
            }
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid-clock")

    def test_reads_travel_from_normalized_constraints_envelope(self):
        result = run_script(
            {
                "courses": [
                    {
                        "id": "A-01",
                        "course_code": "A",
                        "meetings": [
                            {
                                "day": "mon",
                                "start": "10:00",
                                "end": "11:00",
                                "campus": "sinchon",
                            }
                        ],
                    },
                    {
                        "id": "B-01",
                        "course_code": "B",
                        "meetings": [
                            {
                                "day": "mon",
                                "start": "12:30",
                                "end": "13:30",
                                "campus": "international",
                            }
                        ],
                    },
                ],
                "constraints": {
                    "travel_minutes": {"sinchon->international": 90}
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["conflict_free"])
        self.assertTrue(output["complete"])


if __name__ == "__main__":
    unittest.main()
