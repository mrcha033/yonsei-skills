#!/usr/bin/env python3
"""Student-language router and friendly results for Yonsei Bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from yonsei_bridge.bridge import BridgeError, YonseiBridge
else:
    from .bridge import BridgeError, YonseiBridge


INTENTS = (
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
)


def friendly_error(error: Exception) -> dict[str, Any]:
    raw = str(error)
    lowered = raw.casefold()
    if raw.startswith("missing:"):
        fields = [item for item in raw.split(":", 1)[1].split(",") if item]
        return {
            "schema": "yonsei-student-error/v1",
            "status": "more_information_needed",
            "message": "진행에 필요한 정보가 조금 더 있습니다.",
            "missing_information": fields,
            "recovery": "학생에게 누락된 항목만 자연스럽게 질문한 뒤 같은 요청을 이어서 실행하세요.",
        }
    cases = (
        (
            ("login_required", "로그인", "password"),
            "login_required",
            "학교 로그인이 필요합니다.",
            "열린 공식 연세 로그인 화면에서 한 번 로그인한 뒤 같은 요청을 다시 실행하세요.",
        ),
        (
            ("chrome", "chromium", "edge"),
            "browser_unavailable",
            "지원되는 브라우저를 열 수 없습니다.",
            "Chrome, Edge 또는 Chromium이 설치되어 있는지 확인한 뒤 다시 시도하세요.",
        ),
        (
            ("selection_not_found", "row could not be matched", "row could not"),
            "selection_expired",
            "앞서 고른 항목을 현재 화면에서 다시 찾지 못했습니다.",
            "최신 후보를 다시 조회한 뒤 원하는 항목을 한 번 더 선택하세요.",
        ),
        (
            ("field_mapping_required", "field", "입력"),
            "page_changed",
            "학교 화면의 입력 항목이 달라져 일부 내용을 채우지 못했습니다.",
            "열린 공식 화면을 확인하고 누락된 항목만 알려 주세요. 이미 채운 내용은 다시 묻지 않습니다.",
        ),
        (
            ("button was not available", "action button", "menu"),
            "page_changed",
            "학교 화면에서 필요한 메뉴나 버튼을 찾지 못했습니다.",
            "페이지를 새로 연 뒤 다시 시도하세요. 계속되면 학교 화면이 변경된 상태입니다.",
        ),
        (
            ("timed out", "timeout", "connection closed"),
            "temporary_failure",
            "학교 화면의 응답이 늦어 결과를 확인하지 못했습니다.",
            "중복 신청을 피하기 위해 자동 재시도하지 않습니다. 공식 내역을 먼저 확인하세요.",
        ),
        (
            ("compatibility agent", "bundled helper", "font"),
            "local_component_missing",
            "증명서 발급 구성요소를 준비하지 못했습니다.",
            "통합 플러그인을 다시 설치한 뒤 글꼴과 발급 구성요소 확인을 실행하세요.",
        ),
    )
    for markers, status, message, recovery in cases:
        if any(marker in lowered for marker in markers):
            return {
                "schema": "yonsei-student-error/v1",
                "status": status,
                "message": message,
                "recovery": recovery,
            }
    return {
        "schema": "yonsei-student-error/v1",
        "status": "official_page_unavailable",
        "message": "학교 화면에서 요청을 완료하지 못했습니다.",
        "recovery": "열린 공식 화면의 상태를 확인한 뒤 다시 요청하세요. 비밀번호나 인증번호는 채팅에 입력하지 마세요.",
    }


class StudentRouter:
    def __init__(self, bridge: YonseiBridge | None = None) -> None:
        self.bridge = bridge or YonseiBridge()

    @staticmethod
    def _required(request: dict[str, Any], fields: tuple[str, ...]) -> None:
        missing = [field for field in fields if request.get(field) in (None, "")]
        if missing:
            raise BridgeError("missing:" + ",".join(missing))

    @staticmethod
    def _status(result: dict[str, Any]) -> str:
        state = str(result.get("state", ""))
        if state == "login_required":
            return "login_required"
        if state == "confirmation_required":
            return "confirmation_required"
        if state in {"field_mapping_required", "page_changed", "verification_required"}:
            return state
        if state == "completed" and result.get("official_result_verified") is True:
            return "completed"
        if result.get("write_attempted_once"):
            return "verification_required"
        if state in {"reportx_agent_ready", "official_reportx_ready", "official_document_route_ready"}:
            return "ready_for_official_finish"
        return "ready"

    @staticmethod
    def _primary(intent: str, result: dict[str, Any]) -> dict[str, Any]:
        if intent == "today":
            sources = list(result.get("sources", []))
            dashboard_lines = [
                line.strip()
                for line in str(result.get("dashboard", {}).get("text", "")).splitlines()
                if line.strip()
            ][:30]
            underwood_rows = [
                row
                for source in result.get("underwood", {}).values()
                if isinstance(source, dict)
                for row in source.get("rows", [])
            ][:30]
            return {
                "title": "오늘의 연세를 확인했습니다.",
                "source_count": len(sources),
                "sources": sources,
                "dashboard_highlights": dashboard_lines,
                "underwood_items": underwood_rows,
            }
        if intent == "applications":
            rows = result.get("applications", [])
            return {
                "title": "학사 신청 현황을 확인했습니다.",
                "application_count": len(rows),
                "applications": rows,
            }
        if intent == "courses":
            catalog = result.get("catalog", {})
            catalog_rows = catalog.get("rows", [])
            history = result.get("history", {}).get("rows", [])
            current = result.get("current_registration", {}).get("rows", [])
            filters_applied = catalog.get("requested_filters_applied", {})
            unmatched_filters = catalog.get("unmatched_filters", [])
            return {
                "title": (
                    "수강편람 검색 조건을 적용하지 못했습니다."
                    if catalog.get("state") == "field_mapping_required"
                    else "공식 수강편람과 개인 수강 자료를 확인했습니다."
                ),
                "course_count": len(catalog_rows),
                "history_count": len(history),
                "current_course_count": len(current),
                "catalog_state": catalog.get("state"),
                "requested_filters_applied": filters_applied,
                "unmatched_filters": unmatched_filters,
                "registration_period_required_for_catalog": False,
                "courses": catalog_rows,
                "history": history,
                "current_courses": current,
                "current_registration_state": result.get(
                    "current_registration", {}
                ).get("state"),
            }
        if intent == "graduation":
            calculator = result.get("calculator_input", {})
            return {
                "title": "졸업·교직 계산 자료를 확인했습니다.",
                "earned_credit_rows": calculator.get("official_progress", []),
                "preliminary_audit_rows": calculator.get("official_audit", []),
                "teaching_rows": calculator.get("teaching_progress", []),
                "advisory_only": True,
            }
        if intent == "shuttle":
            candidates = result.get("candidates", [])
            state = result.get("state")
            return {
                "title": (
                    "공식 셔틀 내역에서 처리를 확인했습니다."
                    if state == "completed"
                    else (
                        "셔틀 검색 조건을 적용하지 못했습니다."
                        if state in {"field_mapping_required", "page_changed"}
                        else (
                            "셔틀 처리는 시도됐지만 공식 내역에서 결과를 확정하지 못했습니다."
                            if state == "verification_required"
                            else f"조건에 맞는 셔틀 {len(candidates)}개를 찾았습니다."
                        )
                    )
                ),
                "state": state,
                "candidates": candidates,
                "official_rows": result.get("official_rows", []),
                "unmatched_fields": result.get("unmatched_fields", []),
                "retry_allowed": result.get("retry_allowed"),
                "action": result.get("action"),
            }
        if intent in {"space", "dorm"}:
            rows = result.get("rows", [])
            state = result.get("state")
            return {
                "title": (
                    "공식 신청 내역에서 처리를 확인했습니다."
                    if state == "completed"
                    else (
                        "검색 또는 입력 조건을 적용하지 못했습니다."
                        if state in {"field_mapping_required", "page_changed"}
                        else (
                            "신청은 시도됐지만 공식 내역에서 결과를 확정하지 못했습니다."
                            if state == "verification_required"
                            else f"이용 가능한 항목 {len(rows)}개를 확인했습니다."
                        )
                    )
                ),
                "state": state,
                "candidates": rows,
                "review": result.get("review"),
                "official_rows": result.get("official_rows", []),
                "unmatched_fields": result.get("unmatched_fields", []),
                "accepted_input": result.get("accepted_input", {}),
                "retry_allowed": result.get("retry_allowed"),
                "action": result.get("action", "status"),
            }
        if intent == "documents":
            official = result.get("official_result", {})
            completed = (
                result.get("state") == "completed"
                and result.get("official_result_verified") is True
            )
            return {
                "title": (
                    "증명서 무료 출력 PDF를 발급했습니다."
                    if completed
                    else "증명서 발급 경로를 준비했습니다."
                ),
                "document_type": result.get("document_type"),
                "state": result.get("state"),
                "output_format": result.get("output_format", "pdf"),
                "review": result.get("review"),
                "pdf_path": official.get("pdf_path") if completed else None,
                "sha256": official.get("sha256") if completed else None,
                "page_count": official.get("page_count") if completed else None,
                "completion_notified": (
                    official.get("completion_notified") if completed else None
                ),
                "next_step": result.get("next_step"),
            }
        if intent == "learnus":
            courses = result.get("courses", [])
            return {
                "title": f"LearnUs 강의 {len(courses)}개를 확인했습니다.",
                "courses": courses,
            }
        rows = result.get("rows", [])
        return {
            "title": f"전자출결 기록 {len(rows)}행을 확인했습니다.",
            "attendance_rows": rows,
            "check_in_performed": False,
        }

    def run(
        self,
        *,
        intent: str,
        action: str = "status",
        request: dict[str, Any] | None = None,
        selection_id: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        if intent not in INTENTS:
            raise BridgeError("missing:intent")
        request = request or {}
        if intent == "today":
            result = self.bridge.today(full=bool(request.get("full", True)))
        elif intent == "applications":
            result = self.bridge.academic_applications(
                category=str(request.get("category", "장학")),
                application=request.get("application"),
            )
        elif intent == "courses":
            result = self.bridge.mileage(
                year=request.get("year"),
                semester=request.get("semester"),
                campus=request.get("campus"),
                course_type=request.get("course_type"),
                department=request.get("department"),
                keyword=request.get("keyword"),
            )
        elif intent == "graduation":
            result = self.bridge.graduation_teaching(
                include_teaching=bool(request.get("include_teaching", True))
            )
        elif intent == "shuttle":
            self._required(request, ("origin", "date"))
            if action in {"reserve", "waitlist"}:
                self._required(request, ("reason",))
            result = self.bridge.shuttle(
                origin=str(request["origin"]),
                destination=request.get("destination"),
                date=str(request["date"]),
                preferred_time=request.get("preferred_time"),
                depart_after=request.get("depart_after"),
                depart_before=request.get("depart_before"),
                action=action if action != "status" else "search",
                selection_id=selection_id,
                reason=request.get("reason"),
                confirmed=confirmed,
            )
        elif intent in {"space", "dorm"}:
            result = self.bridge.space_dorm(
                service=intent,
                action=action,
                category=str(request.get("category", "기숙사")),
                menu=request.get("menu"),
                request=request,
                selection_id=selection_id,
                confirmed=confirmed,
            )
        elif intent == "documents":
            self._required(request, ("document_type",))
            issuing = action in {"issue", "print"}
            if issuing:
                required = ["language", "copies", "output_format"]
                if request.get("document_type") == "transcript":
                    required.extend(("include_rank", "gpa_conversion"))
                    if request.get("gpa_conversion") is True:
                        required.append("gpa_scale")
                self._required(request, tuple(required))
            output_format = str(
                request.get(
                    "output_format",
                    "print" if action == "print" else "pdf",
                )
            )
            result = self.bridge.documents(
                document_type=str(request["document_type"]),
                action="issue" if action in {"issue", "print"} else "open",
                output_format=output_format,
                language=request.get("language"),
                copies=request.get("copies"),
                purpose=request.get("purpose"),
                include_rank=request.get("include_rank"),
                gpa_conversion=request.get("gpa_conversion"),
                gpa_scale=request.get("gpa_scale"),
                confirmed=confirmed,
            )
        else:
            result = self.bridge.learnus_attendance(service=intent)
        return {
            "schema": "yonsei-student-result/v1",
            "intent": intent,
            "status": self._status(result),
            "primary_result": self._primary(intent, result),
            "details": result,
            "reporting_instruction": "학생에게 primary_result만 먼저 설명하고, 세부 자료는 요청받을 때만 펼쳐 보여 주세요.",
        }
