#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


DATE_RE = re.compile(
    r"(?:20\d{2}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?(?:\s+\d{1,2}:\d{2})?)"
)
LOGIN_MARKERS = ("portal login", "external login", "로그인", "sso", "password")
COURSE_MARKERS = ("course/view.php", "mod/", "강의", "과제", "assignment", "course")
SENSITIVE_QUERY = ("token", "key", "signature", "auth", "expires")


class SnapshotParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.current_link: str | None = None
        self.current_text: list[str] = []
        self.in_title = False
        self.heading_depth = 0
        self.ignored_depth = 0
        self.has_password_input = False

    def handle_starttag(self, tag: str, attrs):
        values = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.ignored_depth += 1
        elif tag == "input" and values.get("type", "").lower() == "password":
            self.has_password_input = True
        elif tag == "a":
            self.current_link = values.get("href", "")
            self.current_text = []
        elif tag == "title":
            self.in_title = True
        elif tag in {"h1", "h2"}:
            self.heading_depth += 1

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag == "a" and self.current_link is not None:
            self.links.append(
                {"href": self.current_link, "label": " ".join("".join(self.current_text).split())}
            )
            self.current_link = None
            self.current_text = []
        elif tag == "title":
            self.in_title = False
        elif tag in {"h1", "h2"} and self.heading_depth:
            self.heading_depth -= 1

    def handle_data(self, data: str):
        if self.ignored_depth:
            return
        clean = " ".join(data.split())
        if not clean:
            return
        self.text_parts.append(clean)
        if self.current_link is not None:
            self.current_text.append(clean + " ")
        if self.in_title:
            self.title_parts.append(clean)
        if self.heading_depth:
            self.heading_parts.append(clean)


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY):
            value = "REDACTED"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def classify_link(url: str) -> str | None:
    lower = url.lower()
    if "mod/assign/" in lower or "assignment" in lower:
        return "assignments"
    if any(marker in lower for marker in ("mod/vod", ".m3u8", "recording", "video", "media", "vimeo")):
        return "videos"
    if (
        "pluginfile.php" in lower
        or "mod/resource/" in lower
        or "mod/folder/" in lower
        or re.search(r"\.(?:pdf|pptx?|docx?|xlsx?|zip|hwp)(?:$|[?#])", lower)
    ):
        return "materials"
    return None


def analyze(html: str, base_url: str) -> dict:
    parser = SnapshotParser()
    parser.feed(html)
    full_text = " ".join(parser.text_parts)
    lower = f"{full_text} {base_url}".lower()
    login_required = parser.has_password_input or any(marker in lower for marker in LOGIN_MARKERS)
    course_shaped = any(marker in lower for marker in COURSE_MARKERS)
    status = "login_required" if login_required else ("authenticated" if course_shaped else "unsupported")
    groups: dict[str, list[dict[str, str]]] = {
        "materials": [],
        "assignments": [],
        "videos": [],
    }
    seen: set[tuple[str, str]] = set()
    for link in parser.links:
        absolute = urljoin(base_url, link["href"])
        group = classify_link(absolute)
        if not group:
            continue
        safe = redact_url(absolute)
        key = (group, safe)
        if key in seen:
            continue
        seen.add(key)
        item = {"label": link["label"] or Path(urlsplit(safe).path).name, "url": safe}
        dates = DATE_RE.findall(link["label"])
        if dates:
            item["visible_date"] = dates[0]
        groups[group].append(item)
    title = " ".join(parser.heading_parts[:1]) or " ".join(parser.title_parts)
    return {
        "schema_version": 1,
        "status": status,
        "base_url": redact_url(base_url),
        "course_title": title or None,
        **groups,
        "date_mentions": sorted(set(DATE_RE.findall(full_text))),
        "warnings": (
            ["Authentication is required in the browser; no course data should be relied on."]
            if status == "login_required"
            else ([] if status == "authenticated" else ["Unsupported or insufficient snapshot."])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze an authorized LearnUs HTML snapshot.")
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.html.read_text(encoding="utf-8"), args.base_url)
    body = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
