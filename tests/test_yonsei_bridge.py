from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = (
    ROOT
    / "plugins"
    / "yonsei-student-companion"
    / "runtime"
    / "yonsei_bridge"
)
sys.path.insert(0, str(BRIDGE_DIR.parent))

from yonsei_bridge.bridge import (  # noqa: E402
    BridgeError,
    BrowserPage,
    MENU_ROUTES,
    PageSnapshot,
    SPACE_REQUEST_FIELDS,
    YonseiBridge,
    _redact,
)
from yonsei_bridge.mcp_server import TOOLS  # noqa: E402
from yonsei_bridge.cdp import CdpError, ChromeRuntime  # noqa: E402
from yonsei_bridge.router import INTENTS, StudentRouter, friendly_error  # noqa: E402


def page_snapshot(
    *,
    headers: list[str] | None = None,
    rows: list[list[str]] | None = None,
    text: str = "",
) -> PageSnapshot:
    grids = []
    if headers is not None:
        grids.append(
            {
                "headers": headers,
                "rows": rows or [],
                "lines": [],
            }
        )
    return PageSnapshot(
        url="https://underwood1.yonsei.ac.kr/",
        title="Official Yonsei page",
        text=text,
        grids=grids,
        buttons=[],
        inputs=[],
        links=[],
    )


class YonseiBridgeTests(unittest.TestCase):
    def test_portal_login_name_is_redacted(self):
        self.assertEqual(
            "[student] 로그인",
            _redact("홍길동 님이 로그인 하셨습니다."),
        )

    def test_one_student_router_covers_all_student_intents(self):
        self.assertEqual(
            {tool["name"] for tool in TOOLS},
            {"yonsei_bridge_connect", "yonsei_student"},
        )
        self.assertEqual(
            set(INTENTS),
            {
                "today",
                "applications",
                "courses",
                "graduation",
                "shuttle",
                "space",
                "dorm",
                "documents",
                "learnus",
                "attendance",
            },
        )
        router = next(tool for tool in TOOLS if tool["name"] == "yonsei_student")
        request_properties = router["inputSchema"]["properties"]["request"]["properties"]
        self.assertIn("headcount", request_properties)
        self.assertIn("purpose", request_properties)
        self.assertIn("keyword", request_properties)
        self.assertIn("semester", request_properties)
        self.assertNotIn("row_terms", request_properties)
        self.assertNotIn("fields", request_properties)
        self.assertIn("enrollment", request_properties["document_type"]["enum"])
        self.assertIn("include_rank", request_properties)
        self.assertIn("gpa_conversion", request_properties)
        self.assertEqual(request_properties["gpa_scale"]["enum"], ["4.5"])

    def test_document_print_action_defaults_to_physical_output(self):
        bridge = mock.Mock()
        bridge.documents.return_value = {
            "state": "official_reportx_physical_ready",
            "document_type": "enrollment",
            "output_format": "print",
        }
        result = StudentRouter(bridge).run(
            intent="documents",
            action="print",
            request={
                "document_type": "enrollment",
                "language": "en",
                "copies": 1,
                "output_format": "print",
            },
            confirmed=True,
        )
        bridge.documents.assert_called_once_with(
            document_type="enrollment",
            action="issue",
            output_format="print",
            language="en",
            copies=1,
            purpose=None,
            include_rank=None,
            gpa_conversion=None,
            gpa_scale=None,
            confirmed=True,
        )
        self.assertEqual("print", result["primary_result"]["output_format"])

    def test_completed_document_primary_result_exposes_saved_pdf(self):
        bridge = mock.Mock()
        bridge.documents.return_value = {
            "state": "completed",
            "document_type": "enrollment",
            "output_format": "pdf",
            "official_result_verified": True,
            "official_result": {
                "pdf_path": "/safe/output/enrollment.pdf",
                "sha256": "abc123",
                "page_count": 1,
                "completion_notified": True,
            },
            "next_step": "done",
        }
        result = StudentRouter(bridge).run(
            intent="documents",
            action="issue",
            request={
                "document_type": "enrollment",
                "language": "en",
                "copies": 1,
                "output_format": "pdf",
            },
            confirmed=True,
        )
        self.assertEqual("completed", result["status"])
        self.assertEqual(
            "/safe/output/enrollment.pdf",
            result["primary_result"]["pdf_path"],
        )
        self.assertTrue(result["primary_result"]["completion_notified"])

    def test_course_handbook_has_its_own_underwood_route(self):
        self.assertEqual(MENU_ROUTES["handbook"], ("수업", "수강편람"))

    def test_structured_rows_preserve_headers_and_unlabelled_rows(self):
        snapshot = PageSnapshot(
            url="https://underwood1.yonsei.ac.kr/",
            title="Underwood",
            text="",
            grids=[
                {
                    "headers": ["과목", "마일리지"],
                    "rows": [["컴퓨팅", "20"]],
                    "lines": [],
                },
                {
                    "headers": [],
                    "rows": [["신촌", "09:00", "3석"]],
                    "lines": [],
                },
            ],
            buttons=[],
            inputs=[],
            links=[],
        )
        rows = YonseiBridge._rows(snapshot)
        self.assertEqual(rows[0]["fields"], {"과목": "컴퓨팅", "마일리지": "20"})
        self.assertEqual(rows[1]["fields"]["column_2"], "09:00")

    def test_bundled_certificate_runtime_is_discoverable(self):
        script = YonseiBridge._find_script("icert_print.py")
        self.assertEqual(script.name, "icert_print.py")
        self.assertTrue((script.parent.parent / "assets" / "fonts" / "연세제목.TTF").is_file())
        self.assertTrue((script.parent.parent / "assets" / "fonts" / "연세본문.TTF").is_file())

    def test_browser_reuses_portal_first_and_retries_one_transient_connection(self):
        runtime = ChromeRuntime.__new__(ChromeRuntime)
        runtime.ensure = lambda: "http://127.0.0.1:9222"
        runtime.targets = lambda: [
            {
                "type": "page",
                "url": "https://underwood1.yonsei.ac.kr/",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/underwood",
            },
            {
                "type": "page",
                "url": "https://portal.yonsei.ac.kr/ui/index.html",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/portal",
            },
        ]
        with mock.patch(
            "yonsei_bridge.cdp.CdpConnection",
            side_effect=[CdpError("temporary"), mock.sentinel.connection],
        ) as connect:
            with mock.patch(
                "yonsei_bridge.cdp.time.sleep",
                return_value=None,
            ):
                result = runtime.open(
                    "https://portal.yonsei.ac.kr/ui/index.html",
                    reuse_hosts={
                        "portal.yonsei.ac.kr",
                        "underwood1.yonsei.ac.kr",
                    },
                )
        self.assertIs(result, mock.sentinel.connection)
        self.assertEqual(
            [call.args[0] for call in connect.call_args_list],
            [
                "ws://127.0.0.1:9222/portal",
                "ws://127.0.0.1:9222/portal",
            ],
        )

    def test_login_wait_tolerates_sso_frame_loading(self):
        page = BrowserPage.__new__(BrowserPage)
        states = iter(("unknown", "login_required", "connected"))
        page.login_state = lambda: next(states)
        with mock.patch("yonsei_bridge.bridge.time.sleep", return_value=None):
            self.assertEqual(page.wait_for_login_state(), "connected")

    def test_infra_login_page_is_not_misclassified_by_logout_header(self):
        page = BrowserPage.__new__(BrowserPage)
        page.snapshot = lambda: PageSnapshot(
            url="https://infra.yonsei.ac.kr/sso/PmSSOService",
            title="연세대학교 로그인",
            text="로그아웃 로그인",
            grids=[],
            buttons=[],
            inputs=[{"type": "password"}],
            links=[],
        )
        self.assertEqual(page.login_state(), "login_required")

    def test_blank_underwood_shell_is_session_expiry(self):
        page = BrowserPage.__new__(BrowserPage)
        page.snapshot = lambda: PageSnapshot(
            url=(
                "https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/"
                "initExtPageWork.do?link=handbList"
            ),
            title="연세대학교",
            text="",
            grids=[],
            buttons=[],
            inputs=[],
            links=[],
        )
        self.assertEqual(page.login_state(), "login_required")

    def test_certificate_count_clears_non_targets_instead_of_submitting_zeroes(self):
        class FakeConnection:
            def __init__(self):
                self.commands = []

            def command(self, method, parameters):
                self.commands.append((method, parameters))
                return {}

        page = BrowserPage.__new__(BrowserPage)
        page.connection = FakeConnection()
        expressions = []

        def evaluate_until_true(expression):
            expressions.append(expression)
            return True

        page._evaluate_until_true = evaluate_until_true
        self.assertTrue(
            page.set_certificate_count(
                document_label="재학증명서",
                language_label="국문",
                copies=1,
            )
        )
        self.assertEqual(
            page.connection.commands,
            [("Input.insertText", {"text": "1"})],
        )
        self.assertIn("setter.call(input, '')", expressions[0])
        self.assertNotIn("setter.call(input, '0')", expressions[0])
        self.assertIn("every(input => input.value === '')", expressions[1])

    def test_transcript_intake_passes_english_45_without_rank_once(self):
        bridge = mock.Mock()
        bridge.documents.return_value = {
            "state": "completed",
            "document_type": "transcript",
            "official_result_verified": True,
        }
        StudentRouter(bridge).run(
            intent="documents",
            action="issue",
            request={
                "document_type": "transcript",
                "language": "en",
                "copies": 1,
                "output_format": "pdf",
                "include_rank": False,
                "gpa_conversion": True,
                "gpa_scale": "4.5",
            },
            confirmed=True,
        )
        bridge.documents.assert_called_once_with(
            document_type="transcript",
            action="issue",
            output_format="pdf",
            language="en",
            copies=1,
            purpose=None,
            include_rank=False,
            gpa_conversion=True,
            gpa_scale="4.5",
            confirmed=True,
        )

    def test_transcript_intake_reports_all_known_missing_options_before_browser(self):
        bridge = mock.Mock()
        with self.assertRaisesRegex(
            BridgeError,
            "missing:language,copies,output_format,include_rank,gpa_conversion",
        ):
            StudentRouter(bridge).run(
                intent="documents",
                action="issue",
                request={"document_type": "transcript"},
                confirmed=True,
            )
        bridge.documents.assert_not_called()

    def test_transcript_options_are_scoped_to_the_owned_language_row(self):
        class FakeConnection:
            def __init__(self):
                self.commands = []

            def command(self, method, parameters):
                self.commands.append((method, parameters))
                return {}

        page = BrowserPage.__new__(BrowserPage)
        page.connection = FakeConnection()
        expressions = []
        page._evaluate_until_true = lambda expression: expressions.append(expression) or True
        self.assertTrue(
            page.configure_certificate_request(
                document_label="성적증명서",
                language_label="영문",
                copies=1,
                include_rank=False,
                gpa_conversion=True,
                gpa_scale="4.5",
            )
        )
        self.assertEqual(
            page.connection.commands,
            [("Input.insertText", {"text": "1"})],
        )
        combined = "\n".join(expressions)
        self.assertIn("owner?.rowSpan", combined)
        self.assertIn("const boxes = [...row.querySelectorAll", combined)
        self.assertIn("석차표기", combined)
        self.assertIn("4.5 환산 표기 추가", combined)
        self.assertIn("const includeRank = false", combined)
        self.assertIn("const includeConversion = true", combined)

    def test_exact_semantic_basket_row_is_reused_without_new_request(self):
        class FakePage:
            def __init__(self):
                self.selected = []
                self.href_clicks = []

            def snapshot(self):
                return page_snapshot(text="증명서 보관함")

            def select_radio(self, *_arguments, **_keywords):
                return False

            def certificate_basket_rows(self, **_arguments):
                return [{"portal_id": "opaque", "_portal_key": "ephemeral"}]

            def select_certificate_basket_row(self, **arguments):
                self.selected.append(arguments)
                return True

            def click_href_fragment(self, fragment):
                self.href_clicks.append(fragment)
                return True

        page = FakePage()
        with mock.patch.object(
            YonseiBridge,
            "_known_certificate_row",
            return_value="opaque",
        ), mock.patch.object(YonseiBridge, "_remember_certificate_row"):
            result = YonseiBridge._select_certificate_for_free_print(
                page,
                document_type="transcript",
                document_label="성적증명서",
                language_label="영문",
                copies=1,
                include_rank=False,
                gpa_conversion=True,
                gpa_scale="4.5",
            )
        self.assertEqual(result["source"], "existing_exact_basket")
        self.assertEqual(len(page.selected), 1)
        self.assertEqual(page.href_clicks, [])
        self.assertNotIn("portal_id", result)
        self.assertNotIn("ephemeral", str(result))

    def test_option_mismatch_never_creates_duplicate_basket_request(self):
        class FakePage:
            def __init__(self):
                self.href_clicks = []

            def snapshot(self):
                return page_snapshot(text="증명서 보관함")

            def select_radio(self, *_arguments, **_keywords):
                return False

            def certificate_basket_rows(self, **_arguments):
                return [{"portal_id": "old", "_portal_key": "private"}]

            def click_href_fragment(self, fragment):
                self.href_clicks.append(fragment)
                return True

        page = FakePage()
        with mock.patch.object(
            YonseiBridge,
            "_known_certificate_row",
            return_value=None,
        ), mock.patch.object(
            YonseiBridge,
            "_portal_id_has_other_semantics",
            return_value=True,
        ):
            with self.assertRaisesRegex(
                BridgeError,
                "option_mismatch_do_not_duplicate",
            ):
                YonseiBridge._select_certificate_for_free_print(
                    page,
                    document_type="transcript",
                    document_label="성적증명서",
                    language_label="영문",
                    copies=1,
                    include_rank=False,
                    gpa_conversion=True,
                    gpa_scale="4.5",
                )
        self.assertEqual(page.href_clicks, [])

    def test_reportx_waiter_pins_the_single_correlated_job_id(self):
        arm_id = "a" * 24
        calls = []

        def request(path, **_arguments):
            calls.append(path)
            if path.startswith("/jobs?correlation_id="):
                return {
                    "jobs": [
                        {
                            "id": "ours",
                            "correlation_id": arm_id,
                            "status": "requesting",
                        },
                        {
                            "id": "unrelated",
                            "correlation_id": "b" * 24,
                            "status": "requesting",
                        },
                    ]
                }
            self.assertEqual(path.split("?", 1)[0], "/jobs/ours")
            return {
                "ok": True,
                "terminal": True,
                "job": {
                    "id": "ours",
                    "correlation_id": arm_id,
                    "status": "server_report_rendered_pdf_unverified",
                },
            }

        with mock.patch.object(
            YonseiBridge,
            "_reportx_request",
            side_effect=request,
        ), mock.patch.object(
            YonseiBridge,
            "_verify_reportx_result",
            return_value={"verified": True, "job_id": "ours"},
        ):
            result = YonseiBridge._wait_reportx_result(arm_id, timeout=1)
        self.assertTrue(result["verified"])
        self.assertTrue(any(path.startswith("/jobs/ours?") for path in calls))
        self.assertFalse(any(path.startswith("/jobs/unrelated") for path in calls))

    def test_reportx_status_ignores_stale_pid_without_signalling_process(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            pid_file = cache / "bridge-agent.pid"
            pid_file.write_text("424242", encoding="utf-8")
            with mock.patch(
                "yonsei_bridge.bridge.certificate_cache",
                return_value=cache,
            ), mock.patch.object(
                YonseiBridge,
                "_reportx_request",
                side_effect=BridgeError("unauthenticated"),
            ), mock.patch("yonsei_bridge.bridge.os.kill") as signal_process:
                status = YonseiBridge._reportx_process_status()
            self.assertFalse(status["running"])
            self.assertFalse(status["health_verified"])
            self.assertFalse(pid_file.exists())
            signal_process.assert_not_called()

    def test_candidates_get_opaque_selection_ids(self):
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        rows = [
            {
                "grid": 0,
                "row": 0,
                "fields": {"출발": "신촌", "시간": "09:00"},
                "text": "신촌 | 09:00",
            }
        ]
        remembered = bridge._remember_rows("shuttle", rows, context="2026-08-01")
        selection_id = remembered[0]["selection_id"]
        self.assertEqual(len(selection_id), 12)
        self.assertEqual(
            bridge._selection_terms(selection_id, "shuttle"),
            ["신촌", "09:00"],
        )

    def test_latest_selection_replaces_old_and_is_consumed_once(self):
        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        first = bridge._remember_rows(
            "space",
            [{"fields": {"공간": "A101"}, "text": "A101"}],
        )[0]["selection_id"]
        second = bridge._remember_rows(
            "space",
            [{"fields": {"공간": "B202"}, "text": "B202"}],
        )[0]["selection_id"]
        with self.assertRaisesRegex(BridgeError, "selection_not_found"):
            bridge._selection(first, "space")
        self.assertEqual(
            bridge._selection(second, "space", consume=True)["text"],
            "B202",
        )
        with self.assertRaisesRegex(BridgeError, "selection_not_found"):
            bridge._selection(second, "space")

    def test_shuttle_filter_state_is_verified_before_search(self):
        class FakePage:
            def __init__(self):
                self.search_clicks = 0

            def click_text(self, label, **_arguments):
                if label == "예약":
                    return True
                if label in {"조회", "검색"}:
                    self.search_clicks += 1
                    return True
                return False

            def fill_label(self, _label, _value):
                return True

            def field_value_matches(self, label, _value):
                return label != "예약일자"

            def snapshot(self, **_arguments):
                return page_snapshot()

        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        page = FakePage()
        bridge._page = lambda: page
        bridge._open_menu = lambda _route: page.snapshot()
        result = bridge.shuttle(
            origin="신촌캠퍼스",
            destination="국제캠퍼스",
            date="2026-08-03",
        )
        self.assertEqual(result["state"], "field_mapping_required")
        self.assertEqual(result["unmatched_fields"], ["date"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(page.search_clicks, 0)

    def test_shuttle_ambiguous_write_is_not_completed_or_retried(self):
        class FakePage:
            def __init__(self):
                self.submitted = False
                self.history = False
                self.write_clicks = 0

            def click_text(self, label, **_arguments):
                if label in {"예약", "조회"}:
                    return True
                if label == "예약신청":
                    self.submitted = True
                    self.write_clicks += 1
                    return True
                if label == "내역/취소" and self.submitted:
                    self.history = True
                    return True
                return False

            def fill_label(self, _label, _value):
                return True

            def field_value_matches(self, _label, _value):
                return True

            def click_grid_row(self, _terms):
                return True

            def snapshot(self, **_arguments):
                rows = (
                    []
                    if self.history
                    else [["신촌캠퍼스", "국제캠퍼스", "09:00", "3"]]
                )
                return page_snapshot(
                    headers=["출발", "도착", "시간", "잔여좌석"],
                    rows=rows,
                )

        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        page = FakePage()
        bridge._page = lambda: page
        bridge._open_menu = lambda _route: page.snapshot()
        with mock.patch("yonsei_bridge.bridge.time.sleep", return_value=None):
            searched = bridge.shuttle(
                origin="신촌캠퍼스",
                destination="국제캠퍼스",
                date="2026-08-03",
            )
            selection_id = searched["candidates"][0]["selection_id"]
            result = bridge.shuttle(
                origin="신촌캠퍼스",
                destination="국제캠퍼스",
                date="2026-08-03",
                action="reserve",
                selection_id=selection_id,
                reason="수업",
                confirmed=True,
            )
            with self.assertRaisesRegex(BridgeError, "selection_not_found"):
                bridge.shuttle(
                    origin="신촌캠퍼스",
                    destination="국제캠퍼스",
                    date="2026-08-03",
                    action="reserve",
                    selection_id=selection_id,
                    reason="수업",
                    confirmed=True,
                )
        self.assertEqual(result["state"], "verification_required")
        self.assertFalse(result["official_result_verified"])
        self.assertFalse(result["retry_allowed"])
        self.assertEqual(page.write_clicks, 1)
        self.assertEqual(StudentRouter._status(result), "verification_required")

    def test_space_status_filter_failure_returns_no_candidates(self):
        class FakePage:
            def navigate(self, _url, **_arguments):
                return None

            def login_state(self):
                return "connected"

            def fill_student_request(self, request, _mapping):
                return {
                    key: {"filled": key != "date", "matched_label": None}
                    for key in request
                }

            def click_text(self, _label, **_arguments):
                raise AssertionError("Search must not run after a filter failure")

            def snapshot(self, **_arguments):
                return page_snapshot(
                    headers=["공간", "상태"],
                    rows=[["A101", "예약가능"]],
                )

        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        bridge.page = FakePage()
        result = bridge.space_dorm(
            service="space",
            action="status",
            request={"date": "2026-08-03", "headcount": 4},
        )
        self.assertEqual(result["state"], "field_mapping_required")
        self.assertEqual(result["unmatched_fields"], ["date"])
        self.assertEqual(result["rows"], [])

    def test_space_confirmed_write_requires_recent_selection_and_consumes_it(self):
        class FakePage:
            def __init__(self):
                self.history = False
                self.write_clicks = 0

            def navigate(self, _url, **_arguments):
                self.history = False

            def login_state(self):
                return "connected"

            def fill_student_request(self, request, _mapping):
                return {
                    key: {"filled": True, "matched_label": key}
                    for key in request
                    if key in {"date", "headcount", "purpose"}
                }

            def click_grid_row(self, _terms):
                return True

            def click_text(self, label, **_arguments):
                if label in {"조회", "검색"}:
                    return True
                if label == "신청":
                    self.write_clicks += 1
                    return True
                if label == "신청내역":
                    self.history = True
                    return True
                return False

            def snapshot(self, **_arguments):
                return page_snapshot(
                    headers=["공간", "건물", "상태"],
                    rows=[["A101", "공학관", "예약가능"]],
                )

        bridge = YonseiBridge.__new__(YonseiBridge)
        bridge.selections = {}
        page = FakePage()
        bridge.page = page
        with self.assertRaisesRegex(BridgeError, "selection_not_found"):
            bridge.space_dorm(
                service="space",
                action="apply",
                request={"purpose": "스터디"},
                confirmed=True,
            )
        with mock.patch("yonsei_bridge.bridge.time.sleep", return_value=None):
            searched = bridge.space_dorm(
                service="space",
                action="status",
                request={"date": "2026-08-03", "headcount": 4},
            )
            selection_id = searched["rows"][0]["selection_id"]
            result = bridge.space_dorm(
                service="space",
                action="apply",
                request={"purpose": "스터디"},
                selection_id=selection_id,
                confirmed=True,
            )
            with self.assertRaisesRegex(BridgeError, "selection_not_found"):
                bridge.space_dorm(
                    service="space",
                    action="apply",
                    request={"purpose": "스터디"},
                    selection_id=selection_id,
                    confirmed=True,
                )
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["official_result_verified"])
        self.assertEqual(page.write_clicks, 1)

    def test_space_request_uses_student_language_keys(self):
        page = BrowserPage.__new__(BrowserPage)
        observed = []

        def fill(label, value):
            observed.append((label, value))
            return label in {"이용일자", "사용인원", "사용목적"}

        page.fill_label = fill
        result = page.fill_student_request(
            {
                "date": "2026-08-01",
                "headcount": 15,
                "purpose": "스터디",
            },
            SPACE_REQUEST_FIELDS,
        )
        self.assertEqual(set(result), {"date", "headcount", "purpose"})
        self.assertTrue(all(item["filled"] for item in result.values()))
        self.assertNotIn("aria-label", str(observed))

    def test_learnus_reuses_official_portal_sso_once(self):
        class FakePage:
            def __init__(self):
                self.connected = False
                self.portal_clicks = 0

            def navigate(self, _url, **_arguments):
                return None

            def wait_for_login_state(self, **_arguments):
                return "connected" if self.connected else "login_required"

            def click_text(self, label, **_arguments):
                if label != "Portal Login":
                    return False
                self.portal_clicks += 1
                self.connected = True
                return True

            def snapshot(self, **_arguments):
                return PageSnapshot(
                    url="https://ys.learnus.org/my/",
                    title="LearnUs",
                    text="My courses",
                    grids=[],
                    buttons=[],
                    inputs=[],
                    links=[
                        {
                            "label": "Course",
                            "url": "https://ys.learnus.org/course/view.php?id=1",
                        }
                    ],
                )

        bridge = YonseiBridge.__new__(YonseiBridge)
        page = FakePage()
        bridge.page = page
        with mock.patch("yonsei_bridge.bridge.time.sleep", return_value=None):
            result = bridge.learnus_attendance(service="learnus")
        self.assertEqual(result["state"], "connected")
        self.assertTrue(result["portal_sso_attempted"])
        self.assertEqual(page.portal_clicks, 1)
        self.assertEqual(len(result["courses"]), 1)

    def test_router_returns_one_primary_result(self):
        class FakeBridge:
            def shuttle(self, **arguments):
                self.arguments = arguments
                return {
                    "action": "search",
                    "candidates": [
                        {
                            "selection_id": "abc123",
                            "text": "신촌 | 09:00 | 3석",
                        }
                    ],
                    "reservation_performed": False,
                }

        fake = FakeBridge()
        result = StudentRouter(fake).run(
            intent="shuttle",
            action="search",
            request={
                "origin": "신촌",
                "destination": "국제캠퍼스",
                "date": "2026-08-01",
                "preferred_time": "09:00",
            },
        )
        self.assertEqual(result["schema"], "yonsei-student-result/v1")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            result["primary_result"]["candidates"][0]["selection_id"],
            "abc123",
        )
        self.assertNotIn("row_terms", fake.arguments)

    def test_course_router_queries_catalog_before_registration_period(self):
        class FakeBridge:
            def mileage(self, **arguments):
                self.arguments = arguments
                return {
                    "catalog": {
                        "state": "available",
                        "registration_period_required": False,
                        "rows": [{"text": "CSI2102-01 | 자료구조"}],
                    },
                    "history": {"state": "available", "rows": []},
                    "current_registration": {
                        "state": "registration_period_limited_or_unavailable",
                        "rows": [],
                    },
                }

        fake = FakeBridge()
        result = StudentRouter(fake).run(
            intent="courses",
            request={
                "year": "2026",
                "semester": "2학기",
                "course_type": "공과대학",
                "keyword": "자료구조",
            },
        )
        primary = result["primary_result"]
        self.assertEqual(primary["course_count"], 1)
        self.assertFalse(primary["registration_period_required_for_catalog"])
        self.assertEqual(
            primary["current_registration_state"],
            "registration_period_limited_or_unavailable",
        )
        self.assertEqual(fake.arguments["keyword"], "자료구조")

    def test_course_filter_failure_is_not_reported_ready(self):
        class FakeBridge:
            def mileage(self, **_arguments):
                return {
                    "state": "field_mapping_required",
                    "catalog": {
                        "state": "field_mapping_required",
                        "requested_filters_applied": {
                            "year": True,
                            "semester": False,
                        },
                        "unmatched_filters": ["semester"],
                        "rows": [],
                    },
                    "history": {"state": "not_queried", "rows": []},
                    "current_registration": {"state": "not_queried", "rows": []},
                }

        result = StudentRouter(FakeBridge()).run(
            intent="courses",
            request={"year": "2026", "semester": "1학기"},
        )
        self.assertEqual(result["status"], "field_mapping_required")
        self.assertEqual(
            result["primary_result"]["requested_filters_applied"]["semester"],
            False,
        )
        self.assertEqual(
            result["primary_result"]["unmatched_filters"],
            ["semester"],
        )

    def test_errors_are_student_friendly(self):
        missing = friendly_error(ValueError("missing:origin,date"))
        self.assertEqual(missing["status"], "more_information_needed")
        self.assertEqual(missing["missing_information"], ["origin", "date"])
        timeout = friendly_error(ValueError("Timed out waiting for official page"))
        self.assertEqual(timeout["status"], "temporary_failure")
        self.assertNotIn("Timed out", timeout["message"])

    def test_mcp_initializes_and_lists_tools(self):
        process = subprocess.Popen(
            [sys.executable, str(BRIDGE_DIR / "mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert process.stdin is not None and process.stdout is not None
        try:
            for request in (
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "yonsei_student",
                        "arguments": {"intent": "셔틀"},
                    },
                },
            ):
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
            initialized = json.loads(process.stdout.readline())
            listed = json.loads(process.stdout.readline())
            korean_error = json.loads(process.stdout.readline())
            self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.6.0")
            self.assertEqual(len(listed["result"]["tools"]), 2)
            self.assertTrue(korean_error["result"]["isError"])
            self.assertIn(
                "필요한 정보",
                korean_error["result"]["structuredContent"]["message"],
            )
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()

    def test_cli_uses_selection_ids_and_student_language_requests(self):
        shuttle = subprocess.run(
            [sys.executable, str(BRIDGE_DIR / "cli.py"), "shuttle", "--help"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        service = subprocess.run(
            [sys.executable, str(BRIDGE_DIR / "cli.py"), "service", "--help"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("--selection-id", shuttle)
        self.assertNotIn("--row-term", shuttle)
        self.assertIn("--request", service)
        self.assertIn("--selection-id", service)
        self.assertNotIn("--field", service)
        self.assertNotIn("--submit-button", service)


if __name__ == "__main__":
    unittest.main()
