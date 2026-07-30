#!/usr/bin/env python3
"""Render plugin manifests and both marketplaces from one specification."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/mrcha033/yonsei-skills"
AUTHOR = {"name": "mrcha033", "url": "https://github.com/mrcha033"}
OUTCOMES = json.loads(
    (ROOT / "contracts" / "skill-outcomes.json").read_text(encoding="utf-8")
)
INSTALLATIONS = {
    plugin["plugin"]: plugin["installation"]
    for plugin in OUTCOMES["plugins"]
}

SPECS = {
    "yonsei-student-companion": {
        "version": "0.5.0",
        "display": "오늘의 연세·포털 연결",
        "description": "한 번 로그인한 공통 브라우저를 이어 쓰고 포털·Underwood·LearnUs·출결·셔틀·공간·증명서를 빠른 명령으로 처리합니다.",
        "short": "한 번 로그인하고 학교생활을 한눈에",
        "long": "학생이 이미 로그인한 일반 브라우저 프로필을 먼저 찾아 Portal에서 Underwood까지 공식 SSO로 이어갑니다. 오늘과 7일 안의 수업·마감·예약을 정리하고 생활관, 장학금, 교환학생의 현재 상태와 다음 절차를 자연어로 관리합니다.",
        "keywords": ["yonsei", "portal", "session", "student", "daily", "dorm", "scholarship", "exchange"],
        "capabilities": [
            "Persistent browser-profile session reuse",
            "Current official portal service routing",
            "Read-only daily student briefing",
            "Dorm-life workflows",
            "Scholarship opportunity and application tracking",
            "Exchange journey tracking",
            "Fast authenticated Portal and Underwood commands",
            "Direct official Underwood course-handbook search",
            "Cross-platform shuttle, space, dorm, and document actions",
            "Single student-language router",
            "Student-friendly recovery messages and primary results",
        ],
        "prompts": [
            "연세 포털에 한 번 로그인하고 계속 이어서 써 줘.",
            "도서관 좌석 예약 화면을 찾아 바로 열어 줘.",
            "오늘 수업, LearnUs 마감, 출결, 예약을 한 번에 정리해 줘.",
            "내가 지원할 수 있는 장학금과 생활관 마감을 정리해 줘.",
            "교환학생 준비에서 다음에 해야 할 일을 알려 줘.",
        ],
    },
    "learnus-course-copilot": {
        "version": "0.4.0",
        "display": "LearnUs 학습 도우미",
        "description": "기존 연세 브라우저 로그인을 이어 사용해 LearnUs 강의, 과제 마감일, 학습자료를 정리합니다. GUI 없는 메모리 전용 세션은 요청한 경우에만 사용합니다.",
        "short": "브라우저 로그인으로 강의·과제·자료 정리",
        "long": "공식 LearnUs 화면에서 학생이 한 번 로그인하면 같은 브라우저 프로필을 이어 사용해 강의·과제·자료를 읽기 전용으로 정리합니다. 세션이 만료될 때만 공식 화면에서 다시 연결하며, 터미널 기반 메모리 전용 세션은 학생이 명시적으로 요청한 경우에만 선택합니다.",
        "keywords": ["learnus", "yonsei", "lms", "course"],
        "capabilities": [
            "Persistent browser-profile LearnUs session",
            "Optional memory-only background session",
            "Authorized course listing",
            "Associated deadline reporting",
            "Material and video inventory",
        ],
        "prompts": [
            "내 LearnUs 강의와 이번 주 마감 과제를 정리해 줘.",
            "이 LearnUs 강의에서 제출할 과제를 찾아 줘.",
            "이 강의의 학습자료와 영상을 목록으로 만들어 줘.",
        ],
    },
    "yonsei-certificate-assistant": {
        "version": "0.10.0",
        "display": "연세 증명서 발급 도우미",
        "description": "Windows 공식 ReportX 또는 macOS·Linux 호환 PDF 경로로 증명서와 학생활동·실습 확인서를 찾고, 원본 연세 글꼴을 유지해 발급합니다.",
        "short": "운영체제에 맞춰 증명서 발급 진행",
        "long": "학생의 운영체제를 자동 확인해 Windows에서는 학교의 공식 ReportX 무료 출력 경로를, macOS와 Linux에서는 문서번호 1회 예약을 포함한 독립 호환 PDF 경로를 사용합니다. 재배포 허가를 받은 연세 제목체와 본문체를 번들해 각각 PDF에 임베드하고, 다른 글꼴이 섞이면 발급 결과를 거부합니다.",
        "keywords": ["yonsei", "certificate", "icert", "print", "pdf", "windows", "macos", "linux", "reportx"],
        "capabilities": [
            "ReportX 인계 정보 진단",
            "검증된 런타임 자산 준비",
            "FP3 호환 PDF 렌더링",
            "문서번호 1회 예약 보호",
            "명시적 프린터 제출",
            "Windows/macOS/Linux 경로 자동 선택",
            "원본 연세 제목체·본문체 개별 PDF 임베딩",
            "학생활동·교육실습·생활관 문서 발급",
        ],
        "prompts": [
            "재학증명서를 국문 PDF로 발급하는 과정을 끝까지 진행해 줘.",
            "이 컴퓨터에서 연세 증명서를 발급해 줘.",
            "이 ReportX 발급 건을 진단하고 호환 PDF 범위를 설명해 줘.",
            "교육실습 확인서를 찾아 PDF 발급까지 진행해 줘.",
        ],
    },
    "yonsei-notice-monitor": {
        "version": "0.2.0",
        "display": "연세 공지·마감일 찾기",
        "description": "연세대학교와 신촌 IT 공식 공지를 검색하고, 신청·납부·행사 마감일과 지난 확인 이후 달라진 공지를 찾습니다.",
        "short": "공식 공지와 놓치기 쉬운 마감일 확인",
        "long": "로그인 없이 공식 공지를 통합 검색하고, 본문에서 신청·제출·납부·행사 날짜를 추려 주며, 사용자가 선택한 파일을 기준으로 새 공지와 변경된 공지를 비교합니다.",
        "keywords": ["yonsei", "notices", "it", "monitor"],
        "capabilities": [
            "Globally sorted official notice search",
            "Contextual deadline candidates",
            "Explicit-state change detection",
        ],
        "prompts": [
            "이번 주에 내가 놓치면 안 되는 연세대 공지를 찾아 줘.",
            "최근 장학·등록금 공지에서 다가오는 마감일을 정리해 줘.",
            "지난번 확인 이후 새로 올라오거나 바뀐 공지를 보여 줘.",
        ],
    },
    "yonsei-academic-copilot": {
        "version": "0.4.0",
        "display": "연세 학사·졸업 도우미",
        "description": "Underwood 학사정보·학사신청·교직이수를 정리하고, 공식 진행표와 학번·전공별 기준으로 졸업요건과 남은 학기를 계산합니다.",
        "short": "학사신청·교직·졸업요건을 한눈에",
        "long": "기존 브라우저 로그인으로 Underwood의 학사정보, 학사신청, 교직이수, 공식 학점진행표를 읽습니다. 정확한 학번·전공 기준과 비교해 졸업까지 부족한 학점·과목·인증과 다음 학기 계획을 보여 주며, 학과별 특수 요건은 확인 필요로 남깁니다.",
        "keywords": ["yonsei", "academic", "records", "student"],
        "capabilities": [
            "Supplied class snapshot normalization",
            "Conservative term grade summaries",
            "Enrollment and registration status checks",
            "Sourced graduation progress calculation",
            "Semester-by-semester graduation planning",
            "Underwood academic-application radar",
            "Teaching-credential progress and workflow",
        ],
        "prompts": [
            "첨부한 학사정보 화면에서 이번 학기 강의를 정리해 줘.",
            "이 성적표를 학점과 평량평균 중심으로 요약해 줘.",
            "이 화면에서 내 학적 상태와 확인이 필요한 항목을 알려 줘.",
            "내 성적표와 전공 졸업요건을 비교해 부족한 항목을 계산해 줘.",
            "졸업까지 남은 과목을 학기별로 배치해 줘.",
            "지금 열려 있는 학사신청과 곧 끝나는 마감을 보여 줘.",
            "내 교직이수에서 남은 교육·실습 요건을 계산해 줘.",
        ],
    },
    "yonsei-course-registration": {
        "version": "0.5.0",
        "display": "연세 수강계획 도우미",
        "description": "Underwood 수강편람을 직접 조회하고 시간표 충돌, 정원·신청자·개인 마일리지 이력·졸업 중요도를 반영해 수강신청 전략을 만듭니다.",
        "short": "시간표 조합과 마일리지 배분 전략",
        "long": "로그인된 Underwood의 수업 → 수강편람을 직접 조회하고, 시간·캠퍼스 이동·공강·학점 조건을 검사해 시간표 후보를 순위화합니다. 개인 마일리지 이력과 현재 확인 가능한 정원·신청자, 동점자 기준, 필수 여부, 대체 과목을 함께 고려해 불확실성을 표시한 배분안을 계산합니다. 수강신청 화면이 기간 제한으로 닫혀도 수강편람 조회는 별도로 이어갑니다.",
        "keywords": ["yonsei", "courses", "registration", "schedule"],
        "capabilities": [
            "Course-row normalization",
            "Authenticated Underwood handbook query",
            "Registration-period independent course discovery",
            "Schedule and campus conflict checks",
            "Explicit course-plan constraint audits",
            "Ranked timetable construction",
            "Official entry diagnostics",
            "Underwood history-aware mileage allocation",
        ],
        "prompts": [
            "2026년 2학기 공과대학 수강편람을 직접 찾아 충돌 없는 시간표 후보를 만들어 줘.",
            "금요일 공강과 18학점 조건으로 이 수강계획을 점검해 줘.",
            "이 시간표에서 겹치는 수업과 캠퍼스 이동 문제를 찾아 줘.",
            "내 Underwood 마일리지 이력과 현재 정원을 고려해서 72점을 전략적으로 나눠 줘.",
        ],
    },
    "yonsei-attendance-copilot": {
        "version": "0.2.0",
        "display": "연세 출결 확인 도우미",
        "description": "전자출결 화면이나 붙여 넣은 표를 요약하고, 확인할 기록과 정정 문의 초안을 만듭니다. 출석 체크는 수행하지 않습니다.",
        "short": "결석·지각 확인과 정정 문의 초안",
        "long": "사용자가 첨부한 전자출결 화면, 표 또는 파일에서 과목별 출결을 정리하고 사용자가 지적한 불일치를 검토해 전송 전 문의 초안을 만듭니다.",
        "keywords": ["yonsei", "attendance", "rollbook", "student"],
        "capabilities": [
            "Supplied attendance summaries",
            "User-review discrepancy detection",
            "Unsent correction drafts",
        ],
        "prompts": [
            "첨부한 전자출결 화면에서 결석과 지각을 과목별로 정리해 줘.",
            "이 출결 기록에서 내가 확인해야 할 항목을 찾아 줘.",
            "이 출결 오류에 대한 정정 문의를 작성하되 보내지는 마.",
        ],
    },
    "yonsei-shuttle-booking": {
        "version": "0.6.1",
        "display": "연세 셔틀 조회·예약",
        "description": "Windows·macOS·Linux에서 방향·날짜·시간을 말하면 공식 셔틀 후보를 찾고 예약·대기·취소하며, 접속 문제는 같은 흐름 안에서 자동 복구합니다.",
        "short": "신촌·국제캠퍼스 셔틀 조회와 예약",
        "long": "Windows·macOS·Linux의 기존 연세 브라우저 로그인 세션으로 공식 셔틀 화면을 열어 조건에 맞는 편을 정리합니다. 화면이 열리지 않으면 로그인 만료, 학교 서비스 장애, 화면 변경을 내부에서 자동 점검하고 원래 요청을 이어갑니다. 정확한 차량과 시간을 다시 확인한 뒤 한 번만 예약·대기·취소하고 공식 내역에서 결과를 검증합니다.",
        "keywords": ["yonsei", "shuttle", "booking", "campus", "windows", "macos", "linux"],
        "capabilities": [
            "Automatic access recovery inside the booking workflow",
            "Supplied trip option filtering",
            "Conservative seat and waitlist status",
            "Confirmed official reservation and cancellation workflow",
            "Cross-platform persistent browser workflow",
            "Daily round-trip and 20-minute rule checks",
        ],
        "prompts": [
            "내일 신촌에서 국제캠퍼스로 가는 셔틀을 이 화면에서 찾아 줘.",
            "오전 9시 이전 셔틀 중 잔여석 있는 편을 정리해 줘.",
            "셔틀 페이지가 안 열리면 원인을 확인하고 예약을 계속해 줘.",
            "내일 오전 9시쯤 신촌에서 국제캠퍼스로 가는 셔틀을 찾아 예약해 줘.",
        ],
    },
    "yonsei-space-reservation": {
        "version": "0.4.0",
        "display": "연세 공간 검색·신청",
        "description": "Windows·macOS·Linux에서 조건에 맞는 공식 공간을 찾고, 검토한 대관 신청을 확인받아 제출합니다.",
        "short": "공간 후보 확인부터 대관 신청까지",
        "long": "Windows·macOS·Linux의 공식 공간대관 화면에서 조건에 맞는 방을 찾고 공개 규칙, 수용인원, 시간과 표시 요금을 확인합니다. 최종 내용과 연락처를 보여 준 뒤 한 번만 제출하고 신청 내역에서 접수 상태를 검증합니다.",
        "keywords": ["yonsei", "space", "room", "reservation", "windows", "macos", "linux"],
        "capabilities": [
            "Supplied space snapshot filtering",
            "Official public booking-rule checks",
            "Unsent reservation drafts",
            "Confirmed official application submission workflow",
            "Cross-platform persistent browser workflow",
        ],
        "prompts": [
            "이 공간 목록에서 15명이 쓸 수 있는 프로젝터 있는 방을 찾아 줘.",
            "이 대관 계획이 공개 이용 규칙에 맞는지 확인해 줘.",
            "이 내용으로 공간대관 신청 초안을 만들되 제출하지는 마.",
            "다음 주 수요일 15명 스터디 공간을 찾아 신청까지 해 줘.",
        ],
    },
    "yonsei-yri": {
        "version": "0.2.0",
        "display": "연세 YRI 업적 정리",
        "description": "Normalize an authorized YRI export, reconcile it with a supplied reference list, or prepare an unsaved field-level change draft.",
        "short": "Audit supplied YRI research achievements",
        "long": "Install separate export-only skills for achievement listing, conservative missing-record reconciliation, and unsaved field-level change preparation.",
        "keywords": ["yonsei", "yri", "research", "achievements"],
        "capabilities": [
            "Authorized YRI export normalization",
            "Missing and duplicate candidate review",
            "Unsaved field-level change drafts",
        ],
        "prompts": [
            "List the achievements in this YRI export.",
            "Compare my YRI export with this reference bibliography.",
            "Prepare but do not save this YRI field change.",
        ],
    },
    "yonsei-rms": {
        "version": "0.2.0",
        "display": "연세 RMS 연구과제 점검",
        "description": "Summarize supplied RMS project data and audit its budget arithmetic or participant roles and periods without uploads, approvals, or submissions.",
        "short": "Audit supplied RMS project snapshots",
        "long": "Install separate snapshot-only skills for project summaries, budget consistency checks, and participant-period validation against explicit supplied data.",
        "keywords": ["yonsei", "rms", "research", "management"],
        "capabilities": [
            "Supplied project summaries",
            "Budget arithmetic audits",
            "Participant role and period checks",
        ],
        "prompts": [
            "Summarize this supplied RMS project snapshot.",
            "Check this RMS budget snapshot for inconsistencies.",
            "Validate these RMS participant roles and periods.",
        ],
    },
    "yonsei-erp": {
        "version": "0.2.0",
        "display": "연세 ERP 내보내기 점검",
        "description": "Filter supplied ERP request and approval snapshots or audit payment lifecycle status without accessing payroll, approving, paying, or submitting.",
        "short": "Review supplied ERP workflow snapshots",
        "long": "Install separate snapshot-only skills for request status, approval inbox, and payment lifecycle review with strict field whitelists and no administrative writes.",
        "keywords": ["yonsei", "erp", "administration", "workflow"],
        "capabilities": [
            "Supplied request status lists",
            "Approval inbox triage",
            "Payment lifecycle audits",
        ],
        "prompts": [
            "List requests in this authorized ERP snapshot.",
            "Triage this supplied ERP approval inbox.",
            "Check payment status in this supplied ERP snapshot.",
        ],
    },
    "yonsei-groupware": {
        "version": "0.2.0",
        "display": "연세 그룹웨어 내보내기 점검",
        "description": "Triage supplied approval data, search an explicit authorized document export, or prepare an unsent message without approving, sending, or sharing.",
        "short": "Review supplied groupware exports safely",
        "long": "Install separate offline skills for approval inbox triage, local authorized-export search, and unsent message drafting with no external communication or workflow mutation.",
        "keywords": ["yonsei", "groupware", "collaboration", "workflow"],
        "capabilities": [
            "Supplied approval inbox triage",
            "Authorized export document search",
            "Unsent message drafts",
        ],
        "prompts": [
            "Triage this supplied groupware approval snapshot.",
            "Search this authorized local groupware export.",
            "Draft but do not send this groupware message.",
        ],
    },
}

MARKETPLACE_ORDER = [
    "yonsei-student-companion",
    "yonsei-notice-monitor",
    "yonsei-course-registration",
    "yonsei-attendance-copilot",
    "yonsei-shuttle-booking",
    "yonsei-space-reservation",
    "yonsei-academic-copilot",
    "yonsei-certificate-assistant",
    "learnus-course-copilot",
    "yonsei-yri",
    "yonsei-rms",
    "yonsei-erp",
    "yonsei-groupware",
]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def codex_manifest(name: str, spec: dict, version: str | None = None) -> dict:
    manifest = {
        "name": name,
        "version": version or spec["version"],
        "description": spec["description"],
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "license": "MIT",
        "keywords": spec["keywords"],
        "skills": "./skills/",
        "interface": {
            "displayName": spec["display"],
            "shortDescription": spec["short"],
            "longDescription": spec["long"],
            "developerName": "mrcha033",
            "category": "Education",
            "capabilities": spec["capabilities"],
            "websiteURL": REPOSITORY,
            "defaultPrompt": spec["prompts"],
        },
    }
    if name == "yonsei-student-companion":
        manifest["mcpServers"] = "./.mcp.json"
    return manifest


def claude_manifest(name: str, spec: dict) -> dict:
    return {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": name,
        "displayName": spec["display"],
        "version": spec["version"],
        "description": spec["description"],
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "license": "MIT",
        "keywords": spec["keywords"],
        "skills": "./skills/",
    }


def main() -> int:
    for name, spec in SPECS.items():
        plugin_root = ROOT / "plugins" / name
        codex_path = plugin_root / ".codex-plugin" / "plugin.json"
        codex_version = spec["version"]
        if codex_path.exists():
            current = json.loads(codex_path.read_text(encoding="utf-8")).get("version", "")
            if current.startswith(f"{spec['version']}+codex."):
                codex_version = current
        write_json(codex_path, codex_manifest(name, spec, codex_version))
        write_json(plugin_root / ".claude-plugin" / "plugin.json", claude_manifest(name, spec))

    claude_marketplace = {
        "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
        "name": "yonsei-skills",
        "description": "Independently installable, outcome-tested Yonsei University skills.",
        "owner": {"name": "mrcha033"},
        "plugins": [
            {
                "name": name,
                "displayName": spec["display"],
                "source": f"./plugins/{name}",
                "description": spec["description"],
                "version": spec["version"],
                "author": {"name": "mrcha033"},
                "homepage": REPOSITORY,
                "repository": REPOSITORY,
                "category": "education",
                "tags": spec["keywords"],
            }
            for name in MARKETPLACE_ORDER
            for spec in [SPECS[name]]
            if INSTALLATIONS[name] == "AVAILABLE"
        ],
    }
    codex_marketplace = {
        "name": "yonsei-skills",
        "interface": {"displayName": "Yonsei Skills"},
        "plugins": [
            {
                "name": name,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{name}",
                },
                "policy": {
                    "installation": INSTALLATIONS[name],
                    "authentication": "ON_INSTALL",
                },
                "category": "Education",
            }
            for name in MARKETPLACE_ORDER
        ],
    }
    write_json(ROOT / ".claude-plugin" / "marketplace.json", claude_marketplace)
    write_json(ROOT / ".agents" / "plugins" / "marketplace.json", codex_marketplace)
    print(f"Rendered {len(SPECS)} plugin manifests and the Claude marketplace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
