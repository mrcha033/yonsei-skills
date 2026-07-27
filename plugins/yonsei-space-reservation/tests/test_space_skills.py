from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEARCH = load("skills/search-yonsei-spaces/scripts/search_spaces.py")
RULES = load("skills/check-yonsei-space-rules/scripts/check_space_rules.py")
PREPARE = load("skills/prepare-yonsei-space-request/scripts/prepare_space_request.py")


class SpaceSkillTests(unittest.TestCase):
    def test_search_requires_evaluable_snapshot_fields(self) -> None:
        result = SEARCH.run(
            {
                "spaces": [
                    {
                        "id": "good",
                        "name": "세미나실",
                        "date": "2026-07-30",
                        "available_start": "13:00",
                        "available_end": "17:00",
                        "capacity": 20,
                        "equipment": ["projector"],
                        "available": True,
                    },
                    {
                        "id": "unknown",
                        "date": "2026-07-30",
                        "available_start": "13:00",
                        "available_end": "17:00",
                        "available": True,
                    },
                ],
                "query": {
                    "date": "2026-07-30",
                    "start": "14:00",
                    "end": "16:00",
                    "minimum_capacity": 12,
                    "required_equipment": ["projector"],
                },
            }
        )
        self.assertEqual(["good"], [row["id"] for row in result["spaces"]])
        self.assertEqual("unknown", result["excluded_unknown"][0]["id"])
        self.assertFalse(result["live_availability"])

    def test_explicit_empty_equipment_is_a_mismatch_not_unknown(self) -> None:
        result = SEARCH.run(
            {
                "spaces": [
                    {
                        "id": "known-empty",
                        "available": True,
                        "equipment": [],
                    }
                ],
                "query": {"required_equipment": ["projector"]},
            }
        )
        self.assertEqual([], result["spaces"])
        self.assertEqual([], result["excluded_unknown"])

    def test_rules_pass_fail_and_unknown(self) -> None:
        base = {
            "requested_on": "2026-07-27T13:30:00+09:00",
            "date": "2026-07-30",
            "start": "14:00",
            "end": "16:00",
            "applicant_type": "student",
            "bookings_in_same_7_day_window": 0,
            "restricted_period": False,
        }
        self.assertTrue(RULES.run(base)["eligible"])
        too_long = {**base, "end": "19:00"}
        self.assertFalse(RULES.run(too_long)["eligible"])
        unknown = {**base, "restricted_period": "unknown"}
        self.assertIsNone(RULES.run(unknown)["eligible"])

    def test_prepare_never_submits(self) -> None:
        report = RULES.run(
            {
                "requested_on": "2026-07-27T13:30:00+09:00",
                "date": "2026-07-30",
                "start": "14:00",
                "end": "16:00",
                "applicant_type": "student",
                "bookings_in_same_7_day_window": 0,
                "restricted_period": False,
            }
        )
        result = PREPARE.run(
            {
                "applicant_type": "student",
                "organizer": "동아리",
                "contact": "local-only",
                "space_id": "room-1",
                "space_name": "세미나실",
                "date": "2026-07-30",
                "start": "14:00",
                "end": "16:00",
                "headcount": 12,
                "purpose": "회의",
                "rule_report": report,
            }
        )
        self.assertTrue(result["ready_for_user_review"])
        self.assertFalse(result["submission_performed"])
        self.assertEqual("not-requested", result["approval_status"])


if __name__ == "__main__":
    unittest.main()
