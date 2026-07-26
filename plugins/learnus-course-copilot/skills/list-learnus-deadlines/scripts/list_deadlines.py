#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


DATE_TOKEN = (
    r"20\d{2}(?:[-./]\s*\d{1,2}[-./]\s*\d{1,2}"
    r"|년\s*\d{1,2}월\s*\d{1,2}일)"
    r"(?:\s+(?:오전|오후)?\s*\d{1,2}:\d{2})?"
)
DATE_RE = re.compile(DATE_TOKEN)
DUE_RE = re.compile(
    rf"(?:제출\s*마감|제출\s*기한|마감|종료|due(?:\s+date)?)\s*[:：]?\s*({DATE_TOKEN})",
    re.IGNORECASE,
)
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
CONTAINER_TAGS = {"li", "article", "section", "div", "tr"}
ACTIVITY_CLASSES = {
    "activity",
    "activity-item",
    "activityinstance",
    "activity-instance",
}


def is_activity_container(tag: str, values: dict[str, str]) -> bool:
    classes = set(values.get("class", "").lower().split())
    data_for = values.get("data-for", "").lower()
    return (
        bool(classes & ACTIVITY_CLASSES)
        or any(value.startswith("modtype_") for value in classes)
        or data_for in {"cmitem", "activity", "activity-item"}
        or (tag == "li" and values.get("data-id", "").isdigit())
    )


class DeadlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.body_classes: set[str] = set()
        self.has_password = False
        self.has_logout = False
        self.has_usermenu = False
        self.ignored_depth = 0
        self.text_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.heading_depth = 0
        self.containers: list[dict] = []
        self.container_stack: list[tuple[str, int]] = []
        self.current_link: dict | None = None
        self.links: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {str(key).lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self.ignored_depth += 1
            return
        if lowered == "body":
            self.body_classes.update(values.get("class", "").lower().split())
        if values.get("data-region", "").lower() == "usermenu":
            self.has_usermenu = True
        if lowered == "input" and values.get("type", "").lower() == "password":
            self.has_password = True
        if lowered in CONTAINER_TAGS:
            index = len(self.containers)
            self.containers.append(
                {
                    "text": [],
                    "is_activity": is_activity_container(lowered, values),
                }
            )
            self.container_stack.append((lowered, index))
        if lowered in {"h1", "h2"}:
            self.heading_depth += 1
        if lowered == "a":
            href = values.get("href", "")
            if "/login/logout.php" in href:
                self.has_logout = True
            self.current_link = {
                "href": href,
                "label": [],
                "containers": [index for _tag, index in self.container_stack],
            }

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            if self.ignored_depth:
                self.ignored_depth -= 1
            return
        if lowered == "a" and self.current_link is not None:
            self.current_link["label"] = " ".join(
                "".join(self.current_link["label"]).split()
            )
            self.links.append(self.current_link)
            self.current_link = None
        if lowered in {"h1", "h2"} and self.heading_depth:
            self.heading_depth -= 1
        if lowered in CONTAINER_TAGS:
            for position in range(len(self.container_stack) - 1, -1, -1):
                if self.container_stack[position][0] == lowered:
                    del self.container_stack[position:]
                    break

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        self.text_parts.append(clean)
        if self.heading_depth:
            self.heading_parts.append(clean)
        if self.current_link is not None:
            self.current_link["label"].append(clean + " ")
        for _tag, index in self.container_stack:
            self.containers[index]["text"].append(clean)


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY):
            value = "REDACTED"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def safe_assignment_url(href: str, base_url: str) -> str | None:
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
        or "/mod/assign/" not in parts.path
        or parts.username is not None
        or parts.password is not None
    ):
        return None
    return redact_url(absolute)


def choose_deadline(label: str, activity_text: str) -> tuple[str | None, str]:
    searchable = " ".join((label, activity_text))
    labeled = DUE_RE.search(searchable)
    if labeled:
        return " ".join(labeled.group(1).split()), "visible_due_label"
    dates = list(dict.fromkeys(" ".join(match.split()) for match in DATE_RE.findall(searchable)))
    if len(dates) == 1:
        return dates[0], "single_date_in_activity"
    if not dates:
        return None, "no_date_in_activity"
    return None, "ambiguous_dates_in_activity"


def analyze(html: str, base_url: str) -> dict:
    parser = DeadlineParser()
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

    deadlines: list[dict[str, str]] = []
    undated: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        url = safe_assignment_url(link["href"], base_url)
        if url is None or url in seen:
            continue
        seen.add(url)
        deadline, basis = choose_deadline(link["label"], link["label"])
        activity_index = next(
            (
                container_index
                for container_index in reversed(link["containers"])
                if parser.containers[container_index]["is_activity"]
            ),
            None,
        )
        if activity_index is not None:
            activity_text = " ".join(parser.containers[activity_index]["text"])
            deadline, basis = choose_deadline(link["label"], activity_text)
        item = {
            "assignment": link["label"] or "Unnamed assignment",
            "url": url,
            "association": basis,
        }
        if deadline:
            item["deadline"] = deadline
            deadlines.append(item)
        else:
            undated.append(item)

    if blocked:
        status = "blocked"
        deadlines = []
        undated = []
    elif login_required:
        status = "login_required"
        deadlines = []
        undated = []
    elif authenticated_evidence and (parser.heading_parts or seen):
        status = "authenticated"
    else:
        status = "unsupported"
        deadlines = []
        undated = []

    warning = {
        "blocked": "LearnUs returned an access-denied or maintenance page.",
        "login_required": "Authentication is required; do not rely on deadline data.",
        "unsupported": "The snapshot is not a supported authenticated course page.",
    }.get(status)
    return {
        "schema_version": 1,
        "kind": "learnus_deadline_report",
        "status": status,
        "base_url": redact_url(base_url),
        "course_title": parser.heading_parts[0] if parser.heading_parts else None,
        "deadlines": deadlines,
        "undated_assignments": undated,
        "warnings": [warning] if warning else [],
    }


def main() -> int:
    cli = argparse.ArgumentParser(
        description="List visibly associated deadlines from an authorized LearnUs course."
    )
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
