import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "summarize-rms-project"
    / "scripts"
    / "summarize_rms_project.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class SummarizeRmsProjectSkillTests(unittest.TestCase):
    def payload(self):
        return {
            "captured_at": "2026-07-27T11:00:00+09:00",
            "source_format": "excel-transcribed",
            "project": {
                "project_code": "R-001",
                "title": "Research Project",
                "status": "진행",
                "period": {
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                },
                "budget": {
                    "currency": "KRW",
                    "total": "1000000",
                    "executed": "250000",
                    "committed": "100000",
                    "remaining": "650000",
                },
                "workflow": {"stage": "검토", "pending_action": "보완"},
                "participants": [
                    {
                        "participant_key": "P-A",
                        "role": "연구책임자",
                        "status": "참여",
                    },
                    {
                        "participant_key": "P-B",
                        "role": "연구원",
                        "status": "참여",
                    },
                ],
            },
        }

    def test_summarizes_all_documented_dimensions_without_participant_identity(self):
        result = run_script(self.payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-rms-project-summary/v1")
        self.assertEqual(output["period"]["calendar_days_inclusive"], 365)
        self.assertEqual(output["budget"]["calculated_remaining"], "650000")
        self.assertEqual(output["participants"]["count"], 2)
        self.assertEqual(output["participants"]["counts_by_role"]["연구원"], 1)
        self.assertTrue(output["complete"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertFalse(output["submitted"])
        self.assertNotIn("P-A", result.stdout)

    def test_reports_budget_overcommit_and_remaining_mismatch(self):
        payload = self.payload()
        payload["project"]["budget"].update({
            "total": "100",
            "executed": "90",
            "committed": "20",
            "remaining": "0",
        })
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(
            {issue["code"] for issue in output["issues"]},
            {"budget-overcommitted", "remaining-mismatch"},
        )

    def test_invalid_project_period_fails_closed(self):
        payload = self.payload()
        payload["project"]["period"] = {
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
        }
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["error"]["code"],
            "invalid-project-period",
        )

    def test_sensitive_field_is_rejected_without_value_echo(self):
        payload = self.payload()
        payload["project"]["participants"][0]["student_id"] = "do-not-echo"
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "sensitive-field-not-allowed")
        self.assertNotIn("do-not-echo", result.stdout)


if __name__ == "__main__":
    unittest.main()
