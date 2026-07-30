import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "skills"
CALCULATE = ROOT / "calculate-yonsei-graduation-progress" / "scripts" / "calculate_graduation_progress.py"
PLAN = ROOT / "plan-yonsei-graduation-path" / "scripts" / "plan_graduation_path.py"


def run(script, payload):
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def progress_payload():
    return {
        "profile": {
            "campus": "sinchon",
            "college": "example-college",
            "major": "example-major",
            "admission_year": "2024",
        },
        "sources": [
            {
                "id": "catalog",
                "url": "https://www.yonsei.ac.kr/example",
                "checked_on": "2026-07-30",
            }
        ],
        "courses": [
            {
                "course_code": "MAJ1001",
                "title": "기초",
                "credits": 3,
                "status": "completed",
                "categories": ["major_required"],
            },
            {
                "course_code": "MAJ2001",
                "title": "심화",
                "credits": 3,
                "status": "in_progress",
                "categories": ["major_required"],
            },
        ],
        "facts": {"chapel_passes": 4},
        "requirements": [
            {
                "id": "total",
                "label": "총학점",
                "type": "total_credits",
                "minimum": 6,
                "source_id": "catalog",
            },
            {
                "id": "major",
                "label": "전공필수",
                "type": "category_credits",
                "category": "major_required",
                "minimum": 6,
                "source_id": "catalog",
            },
            {
                "id": "chapel",
                "label": "채플",
                "type": "fact",
                "key": "chapel_passes",
                "expected": 4,
                "source_id": "catalog",
            },
        ],
    }


class GraduationSkillTests(unittest.TestCase):
    def test_calculates_completed_and_projected_progress(self):
        result = run(CALCULATE, progress_payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        total = next(item for item in output["requirements"] if item["id"] == "total")
        self.assertEqual(total["completed"], 3.0)
        self.assertEqual(total["projected_remaining"], 0.0)
        self.assertFalse(output["all_requirements_satisfied"])
        self.assertTrue(output["complete"])
        self.assertTrue(output["advisory_only"])

    def test_missing_source_keeps_calculation_incomplete(self):
        payload = progress_payload()
        payload["requirements"][0]["source_id"] = "missing"
        result = run(CALCULATE, payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(output["unknowns"][0]["type"], "missing-official-source")

    def test_plans_remaining_requirement(self):
        progress = json.loads(run(CALCULATE, progress_payload()).stdout)
        result = run(
            PLAN,
            {
                "progress": progress,
                "terms": ["2026-2", "2027-1"],
                "max_credits_per_term": 3,
                "completed_course_codes": ["MAJ1001"],
                "courses": [
                    {
                        "course_code": "MAJ2001",
                        "title": "심화",
                        "credits": 3,
                        "requirement_ids": ["total", "major"],
                        "prerequisites": ["MAJ1001"],
                        "offered_terms": ["2026-2"],
                        "required": True,
                        "priority": 5,
                    }
                ],
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["feasible_with_supplied_courses"])
        self.assertEqual(output["planned_terms"][0]["courses"][0]["course_code"], "MAJ2001")
        self.assertFalse(output["registration_performed"])

    def test_schedules_unmapped_prerequisite_before_required_course(self):
        progress = json.loads(run(CALCULATE, progress_payload()).stdout)
        result = run(
            PLAN,
            {
                "progress": progress,
                "terms": ["2026-2", "2027-1"],
                "max_credits_per_term": 3,
                "completed_course_codes": [],
                "courses": [
                    {
                        "course_code": "PRE1000",
                        "title": "선수과목",
                        "credits": 3,
                        "requirement_ids": [],
                        "prerequisites": [],
                        "offered_terms": ["2026-2"],
                    },
                    {
                        "course_code": "MAJ2001",
                        "title": "전공필수",
                        "credits": 3,
                        "requirement_ids": ["total", "major"],
                        "prerequisites": ["PRE1000"],
                        "offered_terms": ["2027-1"],
                        "required": True,
                    },
                ],
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["planned_terms"][0]["courses"][0]["course_code"], "PRE1000")
        self.assertEqual(output["planned_terms"][1]["courses"][0]["course_code"], "MAJ2001")


if __name__ == "__main__":
    unittest.main()
