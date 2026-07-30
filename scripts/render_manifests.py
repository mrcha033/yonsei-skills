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
    "learnus-course-copilot": {
        "version": "0.3.0",
        "display": "LearnUs 학습 도우미",
        "description": "LearnUs 강의, 과제 마감일, 학습자료를 정리하는 도구입니다. 로그인 정보는 저장하지 않습니다.",
        "short": "강의·과제·자료를 한 번에 정리",
        "long": "LearnUs 세션 관리, 수강 강의 확인, 과제 마감일 정리, 학습자료 목록 만들기를 각각 수행합니다. 학교의 지속형 API 토큰이 없어 공개 설치는 아직 보류됩니다.",
        "keywords": ["learnus", "yonsei", "lms", "course"],
        "capabilities": [
            "Memory-only LearnUs session management",
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
        "version": "0.5.0",
        "display": "연세 증명서 Mac 도우미",
        "description": "macOS에서 연세 인터넷증명서 ReportX 출력을 진단하고, 본인이 정상 발급한 준비 문서를 호환 PDF로 렌더링합니다.",
        "short": "Mac의 ReportX 증명서 출력 문제 해결",
        "long": "Windows 전용 ReportX 인계 정보를 해석하고 검증된 런타임 자산과 독립 FP3 렌더러로 호환 PDF를 만듭니다. 문서번호 예약은 명시적으로 한 번만 수행하며 결과는 공식 전자원본으로 주장하지 않습니다.",
        "keywords": ["yonsei", "certificate", "icert", "print", "pdf", "macos", "reportx"],
        "capabilities": [
            "ReportX 인계 정보 진단",
            "검증된 런타임 자산 준비",
            "FP3 호환 PDF 렌더링",
            "문서번호 1회 예약 보호",
            "명시적 프린터 제출",
        ],
        "prompts": [
            "Mac에서 연세 증명서 프린터 출력이 안 되는 문제를 해결해 줘.",
            "이 ReportX 발급 건을 진단하고 호환 PDF 범위를 설명해 줘.",
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
        "version": "0.2.0",
        "display": "연세 학사정보 정리",
        "description": "학사정보 화면 캡처나 붙여 넣은 표에서 강의·성적·학적 상태를 정리합니다. 학교 기록은 변경하지 않습니다.",
        "short": "강의·성적·학적 화면을 쉽게 정리",
        "long": "사용자가 첨부한 학사정보 화면, 표 또는 내보내기 파일을 바탕으로 이번 학기 강의, 성적 요약, 학적 상태를 정리합니다. 실시간 서버 조회 결과로 과장하지 않습니다.",
        "keywords": ["yonsei", "academic", "records", "student"],
        "capabilities": [
            "Supplied class snapshot normalization",
            "Conservative term grade summaries",
            "Enrollment and registration status checks",
        ],
        "prompts": [
            "첨부한 학사정보 화면에서 이번 학기 강의를 정리해 줘.",
            "이 성적표를 학점과 평량평균 중심으로 요약해 줘.",
            "이 화면에서 내 학적 상태와 확인이 필요한 항목을 알려 줘.",
        ],
    },
    "yonsei-course-registration": {
        "version": "0.2.0",
        "display": "연세 수강계획 도우미",
        "description": "붙여 넣은 과목 목록이나 화면 캡처로 시간표 충돌을 찾고 조건에 맞는 시간표 후보를 만듭니다. 수강신청은 대신 누르지 않습니다.",
        "short": "시간표 충돌 확인과 후보 조합 만들기",
        "long": "과목 표나 화면 캡처를 정리해 시간·캠퍼스 이동·공강·학점 조건을 검사하고 시간표 후보를 순위화합니다. 실제 수강신청, 취소, 대기 신청은 수행하지 않습니다.",
        "keywords": ["yonsei", "courses", "registration", "schedule"],
        "capabilities": [
            "Course-row normalization",
            "Schedule and campus conflict checks",
            "Explicit course-plan constraint audits",
            "Ranked timetable construction",
            "Official entry diagnostics",
        ],
        "prompts": [
            "이 과목 목록으로 충돌 없는 시간표 후보를 만들어 줘.",
            "금요일 공강과 18학점 조건으로 이 수강계획을 점검해 줘.",
            "이 시간표에서 겹치는 수업과 캠퍼스 이동 문제를 찾아 줘.",
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
        "version": "0.2.0",
        "display": "연세 셔틀 확인 도우미",
        "description": "셔틀 조회 화면에서 원하는 시간대와 잔여석을 정리하고 접속 문제를 진단합니다. 예약·취소는 수행하지 않습니다.",
        "short": "신촌·국제캠퍼스 셔틀 옵션 확인",
        "long": "사용자가 첨부한 셔틀 조회 화면이나 표를 날짜·방향·시간·잔여석 기준으로 정리하고 공식 진입점의 접속 문제를 확인합니다.",
        "keywords": ["yonsei", "shuttle", "booking", "campus"],
        "capabilities": [
            "Official shuttle client diagnostics",
            "Supplied trip option filtering",
            "Conservative seat and waitlist status",
        ],
        "prompts": [
            "내일 신촌에서 국제캠퍼스로 가는 셔틀을 이 화면에서 찾아 줘.",
            "오전 9시 이전 셔틀 중 잔여석 있는 편을 정리해 줘.",
            "연세 셔틀 페이지가 열리지 않는 이유를 진단해 줘.",
        ],
    },
    "yonsei-space-reservation": {
        "version": "0.2.0",
        "display": "연세 공간대관 도우미",
        "description": "공간 목록 화면에서 조건에 맞는 장소를 찾고 공개 규칙을 확인해 제출 전 신청 내용을 준비합니다.",
        "short": "공간 후보·이용 규칙·신청 초안 확인",
        "long": "사용자가 첨부한 공간대관 화면이나 표를 시간·수용인원·장비 기준으로 정리하고 공식 공개 규칙을 확인해 전송 전 신청 초안을 만듭니다.",
        "keywords": ["yonsei", "space", "room", "reservation"],
        "capabilities": [
            "Supplied space snapshot filtering",
            "Official public booking-rule checks",
            "Unsent reservation drafts",
        ],
        "prompts": [
            "이 공간 목록에서 15명이 쓸 수 있는 프로젝터 있는 방을 찾아 줘.",
            "이 대관 계획이 공개 이용 규칙에 맞는지 확인해 줘.",
            "이 내용으로 공간대관 신청 초안을 만들되 제출하지는 마.",
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
    return {
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
