import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "check-yonsei-enrollment"
    / "scripts"
    / "check_enrollment.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class CheckYonseiEnrollmentSkillTests(unittest.TestCase):
    def test_normalizes_enrolled_status_and_whitelists_fields(self):
        result = run_script(
            {
                "captured_at": "2026-07-27T09:00:00+09:00",
                "term": "2026-1",
                "enrollment": {
                    "재학구분": "재학",
                    "등록여부": "등록완료",
                    "과정": "학사",
                    "소속전공": "컴퓨터과학",
                    "학년": 3,
                    "phone": "not-preserved",
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-academic-enrollment-status/v1")
        self.assertEqual(output["enrollment"]["status"], "enrolled")
        self.assertTrue(output["enrollment"]["registered_for_term"])
        self.assertTrue(output["complete"])
        self.assertFalse(output["interpretation"]["service_eligibility_inferred"])
        self.assertNotIn("not-preserved", result.stdout)

    def test_missing_term_registration_is_unknown_not_pass(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "enrollment": {"status": "재학"},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertIsNone(output["enrollment"]["registered_for_term"])
        self.assertEqual(output["unknowns"][0]["field"], "registered_for_term")

    def test_terminal_status_with_registration_is_flagged(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "enrollment": {
                    "status": "졸업",
                    "registered_for_term": True,
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(
            output["contradictions"][0]["type"],
            "status-registration-conflict",
        )

    def test_unknown_status_fails_closed(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "enrollment": {
                    "status": "확인필요",
                    "registered_for_term": False,
                },
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "unknown-academic-status")


if __name__ == "__main__":
    unittest.main()
