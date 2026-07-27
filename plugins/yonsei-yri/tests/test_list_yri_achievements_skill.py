import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "list-yri-achievements"
    / "scripts"
    / "list_yri_achievements.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class ListYriAchievementsSkillTests(unittest.TestCase):
    def test_normalizes_official_types_and_omits_unrecognized_fields(self):
        result = run_script({
            "captured_at": "2026-07-27T10:00:00+09:00",
            "owner_scope": "self",
            "source_format": "excel-transcribed",
            "achievements": [
                {
                    "record_id": "Y2",
                    "type": "수상",
                    "title": "Best Paper",
                    "year": 2025,
                    "approval_status": "승인",
                    "author_name": "must-not-be-preserved",
                },
                {
                    "record_id": "Y1",
                    "type": "논문",
                    "title": "A Study",
                    "year": 2026,
                    "approval_status": "검토중",
                    "doi": "10.1000/example",
                },
            ],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-yri-achievement-list/v1")
        self.assertEqual(
            [row["type"] for row in output["records"]],
            ["article", "award"],
        )
        self.assertEqual(output["summary"]["counts_by_type"]["article"], 1)
        self.assertTrue(output["complete"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertFalse(output["submitted"])
        self.assertNotIn("must-not-be-preserved", result.stdout)

    def test_article_without_identifier_is_explicitly_incomplete(self):
        result = run_script({
            "captured_at": "2026-07-27",
            "owner_scope": "self",
            "achievements": [{
                "type": "논문",
                "title": "No Identifier",
                "year": 2026,
                "approval_status": "승인",
            }],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(
            output["warnings"][0]["code"],
            "article-without-kri-issn-or-doi",
        )

    def test_rejects_non_self_scope(self):
        result = run_script({
            "captured_at": "2026-07-27",
            "owner_scope": "lab",
            "achievements": [],
        })
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "scope-not-self")

    def test_rejects_credentials_without_echoing_value(self):
        result = run_script({
            "captured_at": "2026-07-27",
            "owner_scope": "self",
            "achievements": [],
            "token": "do-not-echo",
        })
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "credential-field-not-allowed")
        self.assertNotIn("do-not-echo", result.stdout)


if __name__ == "__main__":
    unittest.main()
