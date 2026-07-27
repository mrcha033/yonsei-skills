import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "check-rms-participants"
    / "scripts"
    / "check_rms_participants.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class CheckRmsParticipantsSkillTests(unittest.TestCase):
    def payload(self):
        return {
            "captured_at": "2026-07-27",
            "project_code": "R-001",
            "project_period": {
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
            "participants": [
                {
                    "participant_key": "P-A",
                    "role": "연구책임자",
                    "status": "참여",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "allocation_percent": "50",
                },
                {
                    "participant_key": "P-A",
                    "role": "연구원",
                    "status": "참여",
                    "start_date": "2026-07-01",
                    "end_date": "2026-12-31",
                    "allocation_percent": "40",
                },
            ],
        }

    def test_accepts_bounded_assignments_and_safe_overlap(self):
        result = run_script(self.payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-rms-participant-check/v1")
        self.assertTrue(output["complete"])
        self.assertEqual(output["issues"], [])
        self.assertEqual(output["assignments"][0]["participant_ref"], "P-A")
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertFalse(output["submitted"])

    def test_flags_out_of_period_and_overlapping_allocation(self):
        payload = self.payload()
        payload["participants"][1].update({
            "start_date": "2025-12-01",
            "allocation_percent": "60",
        })
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        codes = {issue["code"] for issue in output["issues"]}
        self.assertIn("assignment-outside-project-period", codes)
        self.assertIn("overlapping-allocation-over-100", codes)

    def test_missing_allocation_remains_unknown(self):
        payload = self.payload()
        del payload["participants"][0]["allocation_percent"]
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(output["unknowns"][0]["code"], "missing-allocation")

    def test_direct_identifier_is_rejected_without_value_echo(self):
        payload = self.payload()
        payload["participants"][0]["student_id"] = "do-not-echo"
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "sensitive-field-not-allowed")
        self.assertNotIn("do-not-echo", result.stdout)


if __name__ == "__main__":
    unittest.main()
