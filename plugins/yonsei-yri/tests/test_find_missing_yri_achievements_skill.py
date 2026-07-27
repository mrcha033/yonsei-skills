import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "find-missing-yri-achievements"
    / "scripts"
    / "find_missing_yri_achievements.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class FindMissingYriAchievementsSkillTests(unittest.TestCase):
    def base_payload(self):
        return {
            "captured_at": "2026-07-27",
            "owner_scope": "self",
            "reference_achievements": [],
            "yri_achievements": [],
        }

    def test_matches_doi_and_returns_review_only_missing_candidate(self):
        payload = self.base_payload()
        payload["reference_achievements"] = [
            {"type": "논문", "title": "Present", "year": 2025, "doi": "doi:10.1/ABC"},
            {"type": "보고서", "title": "Missing", "year": 2026},
        ]
        payload["yri_achievements"] = [
            {
                "record_id": "Y1",
                "type": "article",
                "title": "Different transcription",
                "year": 2025,
                "doi": "https://doi.org/10.1/abc",
            }
        ]
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["summary"]["matched_count"], 1)
        self.assertEqual(output["summary"]["missing_candidate_count"], 1)
        self.assertEqual(
            output["missing_candidates"][0]["reference"]["title"],
            "Missing",
        )
        self.assertTrue(output["complete"])
        self.assertFalse(output["submitted"])

    def test_duplicate_yri_identity_is_ambiguous_and_incomplete(self):
        payload = self.base_payload()
        payload["reference_achievements"] = [
            {"type": "논문", "title": "Paper", "year": 2025, "doi": "10.1/x"}
        ]
        payload["yri_achievements"] = [
            {"type": "논문", "title": "Paper A", "year": 2025, "doi": "10.1/x"},
            {"type": "논문", "title": "Paper B", "year": 2025, "doi": "10.1/x"},
        ]
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(len(output["ambiguous_matches"]), 1)
        self.assertEqual(len(output["possible_duplicates"]), 1)

    def test_reference_without_stable_key_stays_unresolved(self):
        payload = self.base_payload()
        payload["reference_achievements"] = [
            {"type": "수상", "title": "Award"}
        ]
        result = run_script(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(len(output["unresolved_references"]), 1)
        self.assertEqual(len(output["missing_candidates"]), 0)

    def test_unknown_type_fails_closed(self):
        payload = self.base_payload()
        payload["reference_achievements"] = [
            {"type": "unknown-live-code", "title": "X", "year": 2026}
        ]
        result = run_script(payload)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout)["error"]["code"],
            "unknown-achievement-type",
        )


if __name__ == "__main__":
    unittest.main()
