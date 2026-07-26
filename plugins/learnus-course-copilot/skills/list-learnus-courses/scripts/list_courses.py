#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


BLOCKED_MARKERS = (
    "access denied",
    "access forbidden",
    "접근 권한이 없습니다",
    "권한이 없습니다",
    "service maintenance",
    "temporarily unavailable",
    "서비스 점검 중",
    "서비스 점검중",
    "시스템 점검 중",
)
SENSITIVE_QUERY = ("token", "key", "signature", "auth", "expires")


class CourseIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.body_classes: set[str] = set()
        self.dashboard_shaped = False
        self.has_password = False
        self.has_logout = False
        self.has_usermenu = False
        self.ignored_depth = 0
        self.current_href: str | None = None
        self.current_label: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(key).lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self.ignored_depth += 1
            return
        classes = values.get("class", "").lower().split()
        if lowered == "body":
            self.body_classes.update(classes)
        region = values.get("data-region", "").lower()
        if region in {"course-overview", "myoverview", "courses-view"} or any(
            marker in classes for marker in ("dashboard-card", "course-card", "block_myoverview")
        ):
            self.dashboard_shaped = True
        if region == "usermenu":
            self.has_usermenu = True
        if lowered == "input" and values.get("type", "").lower() == "password":
            self.has_password = True
        if lowered == "a":
            href = values.get("href", "")
            if "/login/logout.php" in href:
                self.has_logout = True
            self.current_href = href
            self.current_label = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            if self.ignored_depth:
                self.ignored_depth -= 1
            return
        if lowered == "a" and self.current_href is not None:
            self.links.append(
                (self.current_href, " ".join("".join(self.current_label).split()))
            )
            self.current_href = None
            self.current_label = []

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        self.text_parts.append(clean)
        if self.current_href is not None:
            self.current_label.append(clean + " ")


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY):
            value = "REDACTED"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def safe_course_url(href: str, base_url: str) -> tuple[str, str] | None:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    try:
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or parts.hostname != "ys.learnus.org"
        or port not in (None, 443)
        or parts.path != "/course/view.php"
        or parts.username is not None
        or parts.password is not None
    ):
        return None
    course_id = next(
        (value for key, value in parse_qsl(parts.query) if key == "id" and value.isdigit()),
        "",
    )
    if not course_id:
        return None
    return redact_url(absolute), course_id


def analyze(html: str, base_url: str) -> dict:
    parser = CourseIndexParser()
    parser.feed(html)
    parser.close()
    visible_text = " ".join(parser.text_parts)
    lowered = visible_text.lower()
    blocked = any(marker in lowered for marker in BLOCKED_MARKERS)
    login_required = (
        parser.has_password
        or "notloggedin" in parser.body_classes
        or "portal login" in lowered
        or "external login" in lowered
    )
    authenticated_evidence = (
        "loggedin" in parser.body_classes
        or "logged-in" in parser.body_classes
        or parser.has_logout
        or parser.has_usermenu
    )

    courses: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, label in parser.links:
        parsed = safe_course_url(href, base_url)
        if parsed is None:
            continue
        url, course_id = parsed
        if course_id in seen:
            continue
        seen.add(course_id)
        courses.append(
            {
                "course_id": course_id,
                "name": label or f"Course {course_id}",
                "url": url,
            }
        )

    if blocked:
        status = "blocked"
        courses = []
    elif login_required:
        status = "login_required"
        courses = []
    elif authenticated_evidence and (parser.dashboard_shaped or courses):
        status = "authenticated"
    else:
        status = "unsupported"
        courses = []

    warning = {
        "blocked": "LearnUs returned an access-denied or maintenance page.",
        "login_required": "Authentication is required; do not rely on course links.",
        "unsupported": "The snapshot is not a supported authenticated dashboard.",
    }.get(status)
    return {
        "schema_version": 1,
        "kind": "learnus_course_index",
        "status": status,
        "base_url": redact_url(base_url),
        "courses": courses,
        "warnings": [warning] if warning else [],
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="List courses from an authorized LearnUs dashboard.")
    cli.add_argument("--html", type=Path, required=True)
    cli.add_argument("--base-url", required=True)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    result = analyze(args.html.read_text(encoding="utf-8"), args.base_url)
    body = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
