import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "plan-yonsei-mileage-strategy" / "scripts" / "plan_mileage_strategy.py"


class MileageStrategyTests(unittest.TestCase):
    def run_script(self, payload):
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_prioritizes_required_high_cutoff_course(self):
        result = self.run_script(
            {
                "total_mileage": 30,
                "courses": [
                    {
                        "course_id": "REQ-01",
                        "title": "필수",
                        "capacity": 30,
                        "applicants": 60,
                        "past_cutoff": 18,
                        "mileage_cap": 30,
                        "importance": 5,
                        "required_for_graduation": True,
                        "alternatives": [],
                    },
                    {
                        "course_id": "OPT-01",
                        "title": "선택",
                        "capacity": 50,
                        "applicants": 30,
                        "past_cutoff": 2,
                        "mileage_cap": 30,
                        "importance": 2,
                        "alternatives": ["OPT-02"],
                    },
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        bids = {item["course_id"]: item["recommended_mileage"] for item in output["recommendations"]}
        self.assertGreater(bids["REQ-01"], bids["OPT-01"])
        self.assertLessEqual(output["allocated_mileage"], 30)
        self.assertFalse(output["guaranteed"])
        self.assertFalse(output["registration_performed"])

    def test_rejects_duplicate_course(self):
        result = self.run_script(
            {
                "total_mileage": 10,
                "courses": [
                    {"course_id": "A", "mileage_cap": 10},
                    {"course_id": "A", "mileage_cap": 10},
                ],
            }
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "duplicate-course")


if __name__ == "__main__":
    unittest.main()
