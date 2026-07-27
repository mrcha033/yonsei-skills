import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "check_erp_payment_status.py"


class CheckErpPaymentStatusTests(unittest.TestCase):
    def run_script(self, payload, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", handle.name, *args],
                check=False,
                capture_output=True,
                text=True,
            )
        return completed, json.loads(completed.stdout)

    def base_payload(self):
        return {
            "schema_version": "yonsei-offline-snapshot/v1",
            "source_kind": "user_supplied_json",
            "records": [
                {
                    "payment_id": "P-1",
                    "request_id": "R-1",
                    "category": "finance",
                    "payment_kind": "reimbursement",
                    "status": "scheduled",
                    "amount": 30000,
                    "currency": "KRW",
                    "scheduled_date": "2026-07-31",
                }
            ],
        }

    def test_checks_exact_payment_without_settlement_claim(self):
        completed, result = self.run_script(self.base_payload(), "--payment-id", "P-1")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["payment"]["status"], "scheduled")
        self.assertFalse(result["settlement_verified"])
        self.assertEqual(result["mutations_performed"], [])

    def test_fails_when_payment_is_not_found(self):
        completed, result = self.run_script(self.base_payload(), "--payment-id", "missing")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "payment_not_found")

    def test_rejects_bank_account_field(self):
        payload = self.base_payload()
        payload["records"][0]["bank_account"] = "secret"
        completed, result = self.run_script(payload, "--payment-id", "P-1")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(result["error"]["code"], "unknown_record_fields")


if __name__ == "__main__":
    unittest.main()
