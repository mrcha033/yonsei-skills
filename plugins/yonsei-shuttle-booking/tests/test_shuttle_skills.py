from __future__ import annotations

import importlib.util
import tempfile
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


LIST = load("skills/list-yonsei-shuttle-options/scripts/list_shuttle_options.py")
SEATS = load("skills/check-yonsei-shuttle-seats/scripts/check_shuttle_seats.py")
DIAGNOSE = load("skills/diagnose-yonsei-shuttle-access/scripts/diagnose_shuttle_access.py")
BOOK = load("skills/book-yonsei-shuttle/scripts/prepare_shuttle_booking.py")


class ShuttleSkillTests(unittest.TestCase):
    def test_booking_shortlist_prefers_live_seat_near_time(self) -> None:
        result = BOOK.run(
            {
                "query": {
                    "origin": "신촌",
                    "destination": "국제캠퍼스",
                    "date": "2026-08-03",
                    "preferred_time": "09:00",
                    "allow_waitlist": True,
                },
                "trips": [
                    {
                        "areaDivCd": "S",
                        "busCd": "B1",
                        "busNm": "1호차",
                        "stdrDt": "20260803",
                        "beginTm": "0900",
                        "endTm": "1000",
                        "thrstNm": "신촌→국제",
                        "remndSeat": 2,
                        "resveYn": "Y",
                        "resveWaitYn": "Y",
                    },
                    {
                        "areaDivCd": "S",
                        "busCd": "B2",
                        "busNm": "2호차",
                        "stdrDt": "20260803",
                        "beginTm": "0830",
                        "endTm": "0930",
                        "thrstNm": "신촌→국제",
                        "remndSeat": 0,
                        "resveYn": "N",
                        "resveWaitYn": "Y",
                    },
                ],
            }
        )
        self.assertEqual(result["candidates"][0]["bus_code"], "B1")
        self.assertEqual(result["candidates"][0]["mode"], "reserve")
        self.assertFalse(result["reservation_performed"])
        self.assertEqual(len(result["candidates"][0]["selector"]), 16)

    def test_list_filters_official_fields_and_reports_unknown(self) -> None:
        result = LIST.run(
            {
                "options": [
                    {
                        "busCd": "B2",
                        "stdrDt": "20260728",
                        "beginTm": "1030",
                        "thrstNm": "신촌",
                        "remndSeat": 0,
                    },
                    {
                        "busCd": "B1",
                        "stdrDt": "20260728",
                        "beginTm": "0830",
                        "thrstNm": "신촌",
                        "remndSeat": 3,
                    },
                    {"busCd": "B3", "stdrDt": "20260728", "beginTm": "0900"},
                ],
                "filters": {
                    "date": "2026-07-28",
                    "origin": "신촌",
                    "minimum_remaining_seats": 1,
                },
            }
        )
        self.assertEqual(["B1"], [row["trip_id"] for row in result["options"]])
        self.assertEqual("user-supplied-snapshot", result["source_scope"])
        self.assertEqual("B3", result["excluded_unknown"][0]["trip_id"])

    def test_seat_verdicts_are_conservative(self) -> None:
        available = SEATS.run(
            {"trip": {"remndSeat": 2, "resveYn": "Y", "resveWaitYn": "N"}}
        )
        self.assertEqual("seats-available", available["verdict"])
        waitlist = SEATS.run(
            {"trip": {"remndSeat": 0, "resveYn": "N", "resveWaitYn": "Y"}}
        )
        self.assertEqual("waitlist-only", waitlist["verdict"])
        unknown = SEATS.run({"trip": {"remndSeat": 1}})
        self.assertEqual("unknown", unknown["verdict"])
        self.assertFalse(unknown["reservation_performed"])

    def test_diagnostic_separates_read_and_write_contracts(self) -> None:
        module = {
            "reachable": True,
            "body": (
                'url:"/sch/shtl/ShtlrmCtr/findShtlbusResveList.do";'
                'url:"/sch/shtl/ShtlrmCtr/saveShtlbusResveList.do";'
                'columns:[{name:"busCd"},{name:"remndSeat"}]'
            ),
        }
        result = DIAGNOSE.analyze({"reachable": True}, module)
        self.assertTrue(result["direct_connectivity"])
        self.assertEqual(["findShtlbusResveList.do"], result["observed_contract"]["read_endpoints"])
        self.assertEqual(
            ["saveShtlbusResveList.do"],
            result["observed_contract"]["write_endpoints_not_invoked"],
        )
        self.assertIsNone(result["vpn_required"])
        self.assertFalse(result["mutations_performed"])


if __name__ == "__main__":
    unittest.main()
