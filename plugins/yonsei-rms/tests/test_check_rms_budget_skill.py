import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "check-rms-budget"
    / "scripts"
    / "check_rms_budget.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class CheckRmsBudgetSkillTests(unittest.TestCase):
    def payload(self):
        return {
            "captured_at": "2026-07-27",
            "project_code": "R-001",
            "currency": "KRW",
            "budget_lines": [
                {
                    "category": "인건비",
                    "allocated": "1000.50",
                    "executed": "400.25",
                    "committed": "100.25",
                },
                {
                    "category": "재료비",
                    "allocated": 500,
                    "executed": 200,
                },
            ],
            "supplied_totals": {
                "allocated": "1500.50",
                "executed": "600.25",
                "committed": "100.25",
                "remaining": "800",
            },
        }

    def test_checks_exact_decimal_arithmetic(self):
        result = run_script(self.payload())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-rms-budget-check/v1")
        self.assertEqual(output["calculated_totals"]["remaining"], "800")
        self.assertTrue(output["complete"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertFalse(output["writes_performed"])

    def test_reports_line_overcommit_and_supplied_total_mismatch(self):
        payload = self.payload()
        payload["budget_lines"][0].update({
            "allocated": 100,
            "executed": 90,
            "committed": 20,
        })
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        codes = {issue["code"] for issue in output["issues"]}
        self.assertIn("line-overcommitted", codes)
        self.assertIn("supplied-total-mismatch", codes)

    def test_duplicate_category_fails_closed(self):
        payload = self.payload()
        payload["budget_lines"][1]["category"] = "인건비"
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["error"]["code"],
            "duplicate-category",
        )

    def test_rejects_card_number_without_echoing_value(self):
        payload = self.payload()
        payload["card_number"] = "do-not-echo"
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "sensitive-field-not-allowed")
        self.assertNotIn("do-not-echo", result.stdout)


if __name__ == "__main__":
    unittest.main()
