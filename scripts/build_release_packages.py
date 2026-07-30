#!/usr/bin/env python3
"""Build deterministic, click-first release packages for Yonsei students."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "dist"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)
STUDENT_PLUGINS = (
    "yonsei-student-companion",
    "yonsei-notice-monitor",
    "yonsei-course-registration",
    "yonsei-attendance-copilot",
    "yonsei-shuttle-booking",
    "yonsei-space-reservation",
    "yonsei-academic-copilot",
    "yonsei-certificate-assistant",
    "learnus-course-copilot",
)
SKIP_PARTS = {"__pycache__", ".DS_Store"}
ARCHIVES = (
    "yonsei-codex-ui-pack.zip",
    "yonsei-student-life.zip",
    "yonsei-student-life.skill",
    "yonsei-universal-plugin.zip",
)


class PackageError(ValueError):
    pass


def normalize_version(value: str) -> str:
    version = value.strip()
    if version.startswith("v"):
        version = version[1:]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise PackageError("version must look like 1.2.3 or 1.2.3-beta.1")
    return version


def zip_info(name: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (mode & 0xFFFF) << 16
    info.create_system = 3
    return info


def add_bytes(archive: zipfile.ZipFile, name: str, data: bytes, mode: int = 0o644) -> None:
    archive.writestr(zip_info(name, mode), data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def included_files(source: Path, *, skip_top_level_tests: bool = False) -> Iterable[Path]:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in SKIP_PARTS for part in relative.parts) or path.suffix == ".pyc":
            continue
        if skip_top_level_tests and relative.parts and relative.parts[0] == "tests":
            continue
        yield path


def add_tree(
    archive: zipfile.ZipFile,
    source: Path,
    destination: str,
    *,
    skip_top_level_tests: bool = False,
) -> None:
    for path in included_files(source, skip_top_level_tests=skip_top_level_tests):
        relative = path.relative_to(source).as_posix()
        mode = 0o755 if path.suffix == ".py" and path.read_bytes().startswith(b"#!") else 0o644
        add_bytes(archive, f"{destination.rstrip('/')}/{relative}", path.read_bytes(), mode)


def skill_metadata(skill_dir: Path) -> tuple[str, str]:
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(
        r"^---\s*\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\s*\n",
        content,
    )
    if not match:
        raise PackageError(f"Cannot read skill metadata: {skill_dir}")
    return match.group(1).strip(), match.group(2).strip()


def student_skills() -> list[Path]:
    result: list[Path] = []
    names: set[str] = set()
    for plugin_name in STUDENT_PLUGINS:
        for skill_file in sorted((ROOT / "plugins" / plugin_name / "skills").glob("*/SKILL.md")):
            skill_dir = skill_file.parent
            name, _ = skill_metadata(skill_dir)
            if name in names:
                raise PackageError(f"Duplicate student skill name: {name}")
            names.add(name)
            result.append(skill_dir)
    if len(result) != 35:
        raise PackageError(f"Expected 35 student skills, found {len(result)}")
    return result


def student_marketplace() -> dict:
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )
    entries = [
        entry for entry in marketplace["plugins"] if entry["name"] in STUDENT_PLUGINS
    ]
    if tuple(entry["name"] for entry in entries) != STUDENT_PLUGINS:
        raise PackageError("Student marketplace order or entries do not match the package list")
    return {
        "name": "yonsei-skills",
        "interface": {"displayName": "Yonsei Skills - 학생생활"},
        "plugins": entries,
    }


def logo_svg() -> bytes:
    return (ROOT / "assets" / "yonsei-student-life-logo.svg").read_bytes()


def wrapper_skill_markdown(skills: list[Path]) -> str:
    rows = []
    for skill_dir in skills:
        name, description = skill_metadata(skill_dir)
        rows.append(f"- `{name}`: {description} Read `workflows/{name}/SKILL.md`.")
    routes = "\n".join(rows)
    return f"""---
name: yonsei-student-life
description: Help Yonsei University students reuse one official browser login and manage a daily briefing, notices, courses, attendance, shuttle trips, space requests, academic records, graduation requirements, certificates, and LearnUs. Use when a student asks for any recurring Yonsei student-life workflow.
---

# Yonsei Student Life

Choose the single most relevant workflow below. Read its `SKILL.md` before acting.
Treat that workflow folder as `$SKILL_DIR` when it refers to bundled scripts or
references. Ask only for information the student has not already supplied.

{routes}

For shuttle reservation, space submission, or certificate issuance, use live
browser or local-device actions only when the current host provides those
capabilities. Otherwise stop after the reviewed shortlist or draft and tell the
student to continue in Codex desktop. Never request a password, OTP, or session
cookie in chat.
"""


def wrapper_openai_yaml() -> bytes:
    return """interface:
  display_name: "연세 학생생활 도우미"
  short_description: "공지부터 수강·셔틀·졸업·LearnUs까지 한 번에"
  default_prompt: "Use $yonsei-student-life to help with my Yonsei student-life task."
""".encode("utf-8")


def build_codex_ui_pack(output: Path, version: str) -> None:
    root = "yonsei-skills"
    with zipfile.ZipFile(output, "w") as archive:
        add_bytes(
            archive,
            f"{root}/.agents/plugins/marketplace.json",
            (json.dumps(student_marketplace(), ensure_ascii=False, indent=2) + "\n").encode(),
        )
        add_bytes(
            archive,
            f"{root}/README-START-HERE.md",
            (ROOT / "docs" / "download-and-install.md").read_bytes(),
        )
        add_bytes(
            archive,
            f"{root}/PACKAGE_INFO.txt",
            f"Yonsei Student UI Pack {version}\nStudent plugins: 9\nStudent skills: 35\n".encode(),
        )
        for plugin_name in STUDENT_PLUGINS:
            add_tree(
                archive,
                ROOT / "plugins" / plugin_name,
                f"{root}/plugins/{plugin_name}",
                skip_top_level_tests=True,
            )


def add_wrapper_skill(archive: zipfile.ZipFile, root: str, skills: list[Path]) -> None:
    add_bytes(archive, f"{root}/SKILL.md", wrapper_skill_markdown(skills).encode())
    add_bytes(archive, f"{root}/agents/openai.yaml", wrapper_openai_yaml())
    add_bytes(archive, f"{root}/assets/logo.svg", logo_svg())
    for skill_dir in skills:
        name, _ = skill_metadata(skill_dir)
        add_tree(archive, skill_dir, f"{root}/workflows/{name}")


def build_student_skill(output: Path, skills: list[Path]) -> None:
    with zipfile.ZipFile(output, "w") as archive:
        add_wrapper_skill(archive, "yonsei-student-life", skills)


def universal_manifest(version: str) -> dict:
    return {
        "name": "yonsei-student-life",
        "version": version,
        "description": "Yonsei student-life workflows with reusable browser login, a daily briefing, notices, courses, graduation, shuttle, spaces, certificates, and LearnUs.",
        "author": {"name": "mrcha033", "url": "https://github.com/mrcha033"},
        "homepage": "https://github.com/mrcha033/yonsei-skills",
        "repository": "https://github.com/mrcha033/yonsei-skills",
        "license": "MIT",
        "keywords": ["yonsei", "student", "courses", "campus"],
        "skills": "./skills/",
        "interface": {
            "displayName": "연세 학생생활 도우미",
            "shortDescription": "한 번 로그인하고 오늘 할 일부터 졸업까지",
            "longDescription": "공식 연세 로그인 화면에서 한 번 인증한 브라우저 프로필을 이어 사용하고, 오늘의 수업·마감·출결·예약과 공지, 수강계획, 셔틀, 공간대관, 학사·졸업, 증명서, LearnUs 업무를 자연어로 처리합니다.",
            "developerName": "mrcha033",
            "category": "Education",
            "capabilities": [
                "Official notice search",
                "Reusable official browser session",
                "Read-only daily student briefing",
                "Course and graduation planning",
                "Reviewed campus workflow assistance",
            ],
            "websiteURL": "https://github.com/mrcha033/yonsei-skills",
            "privacyPolicyURL": "https://github.com/mrcha033/yonsei-skills/blob/main/docs/privacy.md",
            "termsOfServiceURL": "https://github.com/mrcha033/yonsei-skills/blob/main/docs/terms.md",
            "defaultPrompt": [
                "연세 포털에 한 번 로그인하고 오늘 할 일을 정리해 줘.",
                "이번 주에 놓치면 안 되는 연세대 공지를 찾아 줘.",
                "내 성적표와 전공 졸업요건을 비교해 줘.",
                "정원과 지난 컷을 고려해 수강 마일리지를 나눠 줘.",
            ],
            "brandColor": "#183B66",
            "composerIcon": "./assets/logo.svg",
            "logo": "./assets/logo.svg",
        },
    }


def build_universal_plugin(output: Path, version: str, skills: list[Path]) -> None:
    root = "yonsei-student-life"
    with zipfile.ZipFile(output, "w") as archive:
        add_bytes(
            archive,
            f"{root}/.codex-plugin/plugin.json",
            (json.dumps(universal_manifest(version), ensure_ascii=False, indent=2) + "\n").encode(),
        )
        add_bytes(archive, f"{root}/assets/logo.svg", logo_svg())
        for skill_dir in skills:
            name, _ = skill_metadata(skill_dir)
            add_tree(archive, skill_dir, f"{root}/skills/{name}")


def validate_archive(path: Path, expected_root: str) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise PackageError(f"Unsafe or empty archive: {path.name}")
        if any(not name.startswith(f"{expected_root}/") for name in names):
            raise PackageError(f"Archive root mismatch: {path.name}")
        bad = archive.testzip()
        if bad:
            raise PackageError(f"Corrupt member {bad} in {path.name}")


def write_checksums(output_dir: Path) -> None:
    lines = []
    for name in ARCHIVES:
        path = output_dir / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(output_dir: Path, version: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    skills = student_skills()
    build_codex_ui_pack(output_dir / ARCHIVES[0], version)
    build_student_skill(output_dir / ARCHIVES[1], skills)
    shutil.copyfile(output_dir / ARCHIVES[1], output_dir / ARCHIVES[2])
    build_universal_plugin(output_dir / ARCHIVES[3], version, skills)
    validate_archive(output_dir / ARCHIVES[0], "yonsei-skills")
    validate_archive(output_dir / ARCHIVES[1], "yonsei-student-life")
    validate_archive(output_dir / ARCHIVES[2], "yonsei-student-life")
    validate_archive(output_dir / ARCHIVES[3], "yonsei-student-life")
    write_checksums(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--version", default="0.0.0")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = normalize_version(args.version)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="yonsei-packages-") as temporary:
            build(Path(temporary), version)
    else:
        build(args.output.resolve(), version)
        print(f"Built {len(ARCHIVES)} archives in {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
