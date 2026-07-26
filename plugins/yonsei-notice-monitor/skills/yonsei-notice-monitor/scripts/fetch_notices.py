#!/usr/bin/env python3
"""Fetch bounded public notice metadata from official Yonsei sources."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin


UNIVERSITY_RSS = "https://www.yonsei.ac.kr/bbs/sc/58/rssList.do?row=50"
UNIVERSITY_ORIGIN = "https://www.yonsei.ac.kr"
IT_NOTICES = "https://yis.yonsei.ac.kr/ics/help/notice.do"
USER_AGENT = "yonsei-notice-monitor/0.1"
MAX_BODY = 4 * 1024 * 1024


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise RuntimeError("Notice source exceeded the bounded response limit.")
    return body


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def university_items(body: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(body)
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        link = clean(item.findtext("link"))
        items.append(
            {
                "source": "university",
                "title": clean(item.findtext("title")),
                "published_at": clean(item.findtext("pubDate")),
                "publisher": clean(item.findtext("author")),
                "url": urljoin(UNIVERSITY_ORIGIN, link),
            }
        )
    return items


class ITNoticeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture_title = False
        self.capture_date = False
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "a" and "c-board-title" in classes and "articleNo=" in values.get("href", ""):
            self.flush()
            self.current = {
                "source": "it",
                "title": "",
                "published_at": "",
                "publisher": "Yonsei Sinchon IT Service",
                "url": urljoin(IT_NOTICES, values["href"]),
            }
            self.capture_title = True
            self.text = []
        elif tag == "span" and self.current is not None and not self.current["published_at"]:
            self.capture_date = True
            self.text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.capture_title and self.current is not None:
            self.current["title"] = clean(" ".join(self.text))
            self.capture_title = False
            self.text = []
        elif tag == "span" and self.capture_date and self.current is not None:
            candidate = clean(" ".join(self.text))
            if re.fullmatch(r"\d{4}[.-]\d{2}[.-]\d{2}", candidate):
                self.current["published_at"] = candidate.replace(".", "-")
            self.capture_date = False
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.capture_title or self.capture_date:
            self.text.append(data)

    def flush(self) -> None:
        if self.current and self.current["title"]:
            self.items.append(self.current)
        self.current = None

    def close(self) -> None:
        super().close()
        self.flush()


def it_items(body: bytes) -> list[dict[str, str]]:
    parser = ITNoticeParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    return parser.items


def apply_filter(
    items: list[dict[str, str]],
    *,
    contains: str | None,
    limit: int,
) -> list[dict[str, str]]:
    if contains:
        needle = contains.casefold()
        items = [
            item
            for item in items
            if needle in f"{item['title']} {item['publisher']}".casefold()
        ]
    return items[:limit]


def self_test() -> None:
    rss = b"""<rss><channel><item><title>A</title><link>/x</link>
    <pubDate>2026-01-02</pubDate><author>P</author></item></channel></rss>"""
    assert university_items(rss)[0]["url"] == "https://www.yonsei.ac.kr/x"
    html = b"""<a class="c-board-title" href="?mode=view&amp;articleNo=1">IT A</a>
    <span>2026.01.03</span>"""
    parsed = it_items(html)
    assert parsed[0]["title"] == "IT A"
    assert parsed[0]["published_at"] == "2026-01-03"
    print("fetch_notices self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("all", "university", "it"), default="all")
    parser.add_argument("--contains")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.limit < 1 or args.limit > 50:
        parser.error("--limit must be between 1 and 50")
    items: list[dict[str, str]] = []
    if args.source in ("all", "university"):
        items.extend(university_items(fetch(UNIVERSITY_RSS)))
    if args.source in ("all", "it"):
        items.extend(it_items(fetch(IT_NOTICES)))
    result = apply_filter(items, contains=args.contains, limit=args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result:
            print(
                f"{item['published_at']}\t{item['source']}\t"
                f"{item['title']}\t{item['url']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
