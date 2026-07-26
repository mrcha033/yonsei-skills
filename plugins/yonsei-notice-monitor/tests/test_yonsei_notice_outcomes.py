from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN / "scripts" / "yonsei_notices.py"


def load_module():
    spec = importlib.util.spec_from_file_location("yonsei_notice_outcomes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


UNIVERSITY_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item><title>Older University Notice</title><link>/bbs/sc/58/1/artclView.do</link>
  <pubDate>2026-07-01 09:00:00.0</pubDate><author>Student Affairs</author>
  <description>Apply by 2026 July 30</description></item>
  <item><title>Newest University Notice</title><link>/bbs/sc/58/2/artclView.do</link>
  <pubDate>2026-07-24 14:26:45.0</pubDate><author>Finance</author>
  <description>Submission deadline: 2026-07-30</description></item>
</channel></rss>"""

IT_HTML = b"""
<div class="c-board-title-wrap">
  <a class="c-board-title" href="?mode=view&amp;articleNo=9&amp;article.offset=0">IT Middle</a>
  <div><span>Security Team</span><span>2026.07.20</span></div>
</div>
"""


class NoticeOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_cross_source_limit_is_applied_after_global_sort(self) -> None:
        items = [
            *self.module.university_items(UNIVERSITY_RSS),
            *self.module.it_items(IT_HTML),
        ]
        results = self.module.filter_notices(
            items,
            contains=None,
            date_from=None,
            date_to=None,
            limit=2,
        )
        self.assertEqual(
            ["Newest University Notice", "IT Middle"],
            [item["title"] for item in results],
        )

    def test_publication_date_filter_is_inclusive(self) -> None:
        items = self.module.university_items(UNIVERSITY_RSS)
        results = self.module.filter_notices(
            items,
            contains=None,
            date_from=date(2026, 7, 24),
            date_to=date(2026, 7, 24),
            limit=10,
        )
        self.assertEqual(["Newest University Notice"], [item["title"] for item in results])

    def test_malformed_rss_title_trailer_is_normalized(self) -> None:
        rss = b"""<rss><channel><item><title>Scholarship Notice}</title>
        <link>/bbs/sc/58/4/artclView.do</link>
        <pubDate>2026-07-24</pubDate><author>Office</author></item></channel></rss>"""
        self.assertEqual(
            "Scholarship Notice",
            self.module.university_items(rss)[0]["title"],
        )

    def test_deadline_extraction_is_structured_and_bounded_by_date(self) -> None:
        text = "제출기한: 2026년 7월 30일까지. 행사는 2026년 8월 3일 개최."
        mentions = self.module.extract_date_mentions(
            text,
            anchor=date(2026, 7, 24),
            as_of=date(2026, 7, 27),
            deadline_from=date(2026, 7, 27),
            deadline_to=date(2026, 7, 31),
        )
        self.assertEqual(1, len(mentions))
        self.assertEqual("2026-07-30", mentions[0]["date"])
        self.assertEqual("deadline", mentions[0]["kind"])
        self.assertEqual("upcoming", mentions[0]["status"])

    def test_yearless_deadline_uses_publication_year_not_as_of_year(self) -> None:
        notice = self.module.university_items(UNIVERSITY_RSS)[0]
        notice["published_at"] = "2025-07-24T14:26:45+09:00"
        notice["published_date"] = "2025-07-24"
        notice["excerpt"] = "신청기한: 8월 1일까지"
        base = {
            "query": {},
            "sources": [{"source": "university", "status": "ok", "items": 1}],
            "partial": False,
            "errors": [],
            "results": [notice],
        }
        args = Namespace(
            as_of="2026-07-27",
            deadline_from=None,
            deadline_to=None,
            limit=10,
            fetch_details=False,
            include_all_dates=False,
            include_empty=False,
        )
        with patch.object(self.module, "search_payload", return_value=base):
            payload = self.module.deadlines_payload(args)
        mention = payload["results"][0]["date_mentions"][0]
        self.assertEqual("2025-08-01", mention["date"])
        self.assertEqual("past", mention["status"])

    def test_abbreviated_range_end_inherits_explicit_start_year(self) -> None:
        text = (
            "신청기간: 2026. 9. 10.(목) 09:00 "
            "~ 9. 14.(월) 17:00까지"
        )
        mentions = self.module.extract_date_mentions(
            text,
            anchor=date(2025, 12, 1),
            as_of=date(2026, 9, 1),
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [
                ("2026-09-10", "09:00", "start"),
                ("2026-09-14", "17:00", "end"),
            ],
            [
                (item["date"], item["time"], item["range_role"])
                for item in mentions
            ],
        )

    def test_dotted_range_uses_publication_year_and_keeps_same_date_roles(self) -> None:
        text = "신청기간: 8. 21. 오전 9:00 ~ 8. 21. 오후 5:30까지"
        mentions = self.module.extract_date_mentions(
            text,
            anchor=date(2026, 7, 24),
            as_of=date(2026, 8, 1),
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [
                ("2026-08-21", "09:00", "오전 9:00", "start"),
                ("2026-08-21", "17:30", "오후 5:30", "end"),
            ],
            [
                (
                    item["date"],
                    item["time"],
                    item["time_text"],
                    item["range_role"],
                )
                for item in mentions
            ],
        )

    def test_same_date_single_mentions_keep_distinct_times(self) -> None:
        text = "면담 일시: 2026. 8. 21. 09:00, 2026. 8. 21. 17:00"
        mentions = self.module.extract_date_mentions(
            text,
            anchor=date(2026, 7, 24),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [("09:00", "single"), ("17:00", "single")],
            [(item["time"], item["range_role"]) for item in mentions],
        )

    def test_timed_duplicate_suppresses_only_matching_no_time_noise(self) -> None:
        text = (
            "신청기간: 2026. 8. 21. ~ 8. 27. "
            "신청기간: 2026. 8. 21. ~ 8. 27. 17:00"
        )
        mentions = self.module.extract_date_mentions(
            text,
            anchor=date(2026, 7, 24),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        range_ends = [
            item for item in mentions if item["range_role"] == "end"
        ]
        self.assertEqual(1, len(range_ends))
        self.assertEqual("17:00", range_ends[0]["time"])

    def test_compact_dotted_value_is_not_a_global_date(self) -> None:
        mentions = self.module.extract_date_mentions(
            "제품 버전 v8.21은 다음 배포에서도 유지됩니다.",
            anchor=date(2026, 7, 24),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual([], mentions)

    def test_publication_anchor_allows_december_to_january_rollover(self) -> None:
        mentions = self.module.extract_date_mentions(
            "신청 마감: 1월 5일까지",
            anchor=date(2026, 12, 20),
            as_of=date(2026, 12, 21),
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual("2027-01-05", mentions[0]["date"])
        self.assertEqual("upcoming", mentions[0]["status"])

    def test_abbreviated_range_end_rolls_into_next_year(self) -> None:
        mentions = self.module.extract_date_mentions(
            "신청기간: 2026. 12. 28. 09:00 ~ 1. 3. 17:00까지",
            anchor=date(2026, 12, 1),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [
                ("2026-12-28", "start"),
                ("2027-01-03", "end"),
            ],
            [(item["date"], item["range_role"]) for item in mentions],
        )

    def test_day_only_range_end_inherits_start_month_and_year(self) -> None:
        mentions = self.module.extract_date_mentions(
            "1차 납부기간: 2026. 8. 21.(금) 09:30 ~ 27.(목) 17:00",
            anchor=date(2026, 7, 24),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [
                ("2026-08-21", "09:30", "start"),
                ("2026-08-27", "17:00", "end"),
            ],
            [
                (item["date"], item["time"], item["range_role"])
                for item in mentions
            ],
        )

    def test_from_until_phrase_does_not_capture_next_schedule_date(self) -> None:
        mentions = self.module.extract_date_mentions(
            (
                "고지서 출력 2026. 8. 21.(금) 09:30부터 납부 시까지 "
                "추가등록 2026. 9. 10.(목) 09:30부터 납부 시까지"
            ),
            anchor=date(2026, 7, 24),
            as_of=None,
            deadline_from=None,
            deadline_to=None,
        )
        self.assertEqual(
            [
                ("2026-08-21", "single"),
                ("2026-09-10", "single"),
            ],
            [(item["date"], item["range_role"]) for item in mentions],
        )

    def test_article_parser_prefers_fr_view(self) -> None:
        body = b"""<nav>2020-01-01</nav><div class="fr-view">
        Apply by 2026-07-30</div><footer>2029-01-01</footer>"""
        self.assertEqual("Apply by 2026-07-30", self.module.article_text(body))

    def test_state_is_only_written_to_explicit_path_and_baseline_is_quiet(self) -> None:
        notice = self.module.university_items(UNIVERSITY_RSS)[0]
        args = Namespace(
            source="all",
            contains=None,
            date_from=None,
            date_to=None,
            timeout=1.0,
            state="",
            dry_run=False,
            reset=False,
        )
        base = {
            "query": {},
            "sources": [],
            "partial": False,
            "errors": [],
            "results": [notice],
        }
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            args.state = str(state)
            with patch.object(self.module, "search_payload", return_value=base):
                first = self.module.changes_payload(args)
                second = self.module.changes_payload(args)
            self.assertTrue(first["initialized"])
            self.assertEqual([], first["changes"]["added"])
            self.assertTrue(state.is_file())
            stored = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(self.module.STATE_SCHEMA, stored["schema"])
            self.assertFalse(second["initialized"])
            self.assertEqual([], second["changes"]["added"])

    def test_changed_state_query_is_rejected_without_reset(self) -> None:
        notice = self.module.university_items(UNIVERSITY_RSS)[0]
        base = {
            "query": {},
            "sources": [{"source": "university", "status": "ok"}],
            "partial": False,
            "errors": [],
            "results": [notice],
        }
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            self.module.write_state(
                state,
                {
                    "schema": self.module.STATE_SCHEMA,
                    "query": {
                        "source": "university",
                        "contains": "old",
                        "published_from": None,
                        "published_to": None,
                    },
                    "items": [],
                },
            )
            args = Namespace(
                source="university",
                contains="new",
                date_from=None,
                date_to=None,
                timeout=1.0,
                state=str(state),
                dry_run=False,
                reset=False,
            )
            with patch.object(self.module, "search_payload", return_value=base):
                with self.assertRaises(self.module.NoticeError):
                    self.module.changes_payload(args)

    def test_partial_fetch_does_not_replace_state(self) -> None:
        notice = self.module.university_items(UNIVERSITY_RSS)[0]
        args = Namespace(
            source="all",
            contains=None,
            date_from=None,
            date_to=None,
            timeout=1.0,
            state="",
            dry_run=False,
            reset=False,
        )
        base = {
            "query": {},
            "sources": [
                {"source": "university", "status": "ok"},
                {"source": "it", "status": "error"},
            ],
            "partial": True,
            "errors": ["IT source unavailable"],
            "results": [notice],
        }
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            args.state = str(state)
            with patch.object(self.module, "search_payload", return_value=base):
                result = self.module.changes_payload(args)
            self.assertFalse(result["state_written"])
            self.assertEqual("partial_fetch", result["state_write_blocked_reason"])
            self.assertFalse(state.exists())

    def test_zero_parse_after_healthy_baseline_fails_closed(self) -> None:
        notice = self.module.university_items(UNIVERSITY_RSS)[0]
        args = Namespace(
            source="all",
            contains=None,
            date_from=None,
            date_to=None,
            timeout=1.0,
            state="",
            dry_run=False,
            reset=False,
        )
        base = {
            "query": {},
            "sources": [
                {"source": "university", "status": "ok", "items": 0},
                {"source": "it", "status": "ok", "items": 0},
            ],
            "partial": False,
            "errors": [],
            "results": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            args.state = str(state)
            # This legacy-format state has no source snapshots. Its retained
            # university item still proves a prior healthy non-empty parse.
            self.module.write_state(
                state,
                {
                    "schema": self.module.STATE_SCHEMA,
                    "query": {
                        "source": "all",
                        "contains": None,
                        "published_from": None,
                        "published_to": None,
                    },
                    "items": [self.module.state_record(notice)],
                },
            )
            before = state.read_bytes()
            with patch.object(self.module, "search_payload", return_value=base):
                result = self.module.changes_payload(args)
            self.assertFalse(result["state_written"])
            self.assertEqual(
                "suspicious_empty_source",
                result["state_write_blocked_reason"],
            )
            self.assertEqual(
                [
                    {
                        "source": "university",
                        "previous_healthy_count": 1,
                        "current_count": 0,
                        "reason": "zero_items_after_healthy_nonempty_baseline",
                    }
                ],
                result["source_health_issues"],
            )
            self.assertEqual([], result["changes"]["missing_from_current_window"])
            self.assertEqual(before, state.read_bytes())

    def test_empty_first_run_can_establish_a_baseline(self) -> None:
        args = Namespace(
            source="university",
            contains=None,
            date_from=None,
            date_to=None,
            timeout=1.0,
            state="",
            dry_run=False,
            reset=False,
        )
        base = {
            "query": {},
            "sources": [
                {"source": "university", "status": "ok", "items": 0},
            ],
            "partial": False,
            "errors": [],
            "results": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            args.state = str(state)
            with patch.object(self.module, "search_payload", return_value=base):
                result = self.module.changes_payload(args)
            self.assertTrue(result["initialized"])
            self.assertTrue(result["state_written"])
            self.assertEqual([], result["source_health_issues"])
            stored = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(
                [{"source": "university", "status": "ok", "items": 0}],
                stored["sources"],
            )

    def test_state_write_rejects_missing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing" / "state.json"
            with self.assertRaises(self.module.NoticeError):
                self.module.write_state(
                    missing,
                    {"schema": self.module.STATE_SCHEMA, "items": []},
                )

    def test_official_https_allowlist(self) -> None:
        self.module.validate_official_url(
            "https://www.yonsei.ac.kr/bbs/sc/58/rssList.do"
        )
        with self.assertRaises(self.module.NoticeError):
            self.module.validate_official_url("http://www.yonsei.ac.kr/")
        with self.assertRaises(self.module.NoticeError):
            self.module.validate_official_url("https://yonsei.example/notices")
        with self.assertRaises(self.module.NoticeError):
            self.module.validate_official_url(
                "https://www.yonsei.ac.kr:444/notices"
            )
        with self.assertRaises(self.module.NoticeError):
            self.module.validate_official_url(
                "https://user:secret@www.yonsei.ac.kr/notices"
            )

    def test_external_redirect_is_rejected_before_following(self) -> None:
        handler = self.module.SafeRedirectHandler()
        with self.assertRaises(self.module.NoticeError):
            handler.redirect_request(
                self.module.urllib.request.Request(
                    "https://www.yonsei.ac.kr/notices"
                ),
                None,
                302,
                "Found",
                {},
                "https://attacker.example/collect",
            )

    def test_each_skill_local_entry_point_has_one_operation(self) -> None:
        wrappers = {
            "search-yonsei-notices/scripts/search_yonsei_notices.py": "metadata text filter",
            "list-yonsei-notice-deadlines/scripts/list_yonsei_notice_deadlines.py": "deadline-from",
            "watch-yonsei-notices/scripts/watch_yonsei_notices.py": "explicit json state path",
        }
        for relative, expected_help in wrappers.items():
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN / "skills" / relative),
                    "--help",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn(expected_help.casefold(), completed.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
