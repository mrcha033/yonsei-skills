#!/usr/bin/env python3
"""Deterministic, bounded tools for official public Yonsei notices."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


SCHEMA = "yonsei-notices/v1"
STATE_SCHEMA = "yonsei-notice-state/v1"
USER_AGENT = "yonsei-notice-skills/0.2"
MAX_INDEX_BODY = 2 * 1024 * 1024
MAX_DETAIL_BODY = 2 * 1024 * 1024
MAX_DETAIL_TEXT = 100_000
MAX_EXCERPT = 1_200
MAX_CONTEXT = 180
DEFAULT_TIMEOUT = 15.0
ALLOWED_HOSTS = frozenset({"www.yonsei.ac.kr", "yis.yonsei.ac.kr"})

UNIVERSITY_RSS = "https://www.yonsei.ac.kr/bbs/sc/58/rssList.do?row=50"
UNIVERSITY_ORIGIN = "https://www.yonsei.ac.kr"
IT_NOTICES = (
    "https://yis.yonsei.ac.kr/ics/help/notice.do"
    "?mode=list&article.offset=0&articleLimit=50"
)

DATE_FULL_RE = re.compile(
    r"(?<!\d)(?P<year>20\d{2})\s*(?:[./-]|년)\s*"
    r"(?P<month>\d{1,2})\s*(?:[./-]|월)\s*"
    r"(?P<day>\d{1,2})\s*일?"
)
DATE_MONTH_DAY_RE = re.compile(
    r"(?<![\d./-])(?P<month>\d{1,2})\s*월\s*"
    r"(?P<day>\d{1,2})\s*일"
)
DATE_DOTTED_MONTH_DAY_RE = re.compile(
    r"(?<![\d./-])(?P<month>\d{1,2})\s*\.\s*"
    r"(?P<day>\d{1,2})\s*\.?"
)
DATE_DOTTED_DAY_RE = re.compile(
    r"(?<![\d./-])(?P<day>\d{1,2})\s*\."
)
_FULL_DATE_TOKEN = (
    r"20\d{2}\s*(?:[./-]|년)\s*\d{1,2}\s*"
    r"(?:[./-]|월)\s*\d{1,2}\s*일?"
)
_KOREAN_MONTH_DAY_TOKEN = r"\d{1,2}\s*월\s*\d{1,2}\s*일"
_DOTTED_MONTH_DAY_TOKEN = r"\d{1,2}\s*\.\s*\d{1,2}\s*\.?"
_DOTTED_DAY_TOKEN = r"\d{1,2}\s*\."
RANGE_DATE_TOKEN_RE = re.compile(
    rf"(?<![\d./-])(?:{_FULL_DATE_TOKEN}|"
    rf"{_KOREAN_MONTH_DAY_TOKEN}|{_DOTTED_MONTH_DAY_TOKEN}|"
    rf"{_DOTTED_DAY_TOKEN})(?!\d)"
)
RANGE_SEPARATOR_RE = re.compile(
    r"(?:~|∼|～|–|—|(?<=\s)-(?=\s)|부터)"
)
TIME_RE = re.compile(
    r"(?<!\d)(?:(?P<period>오전|오후)\s*)?"
    r"(?P<hour>\d{1,2})\s*"
    r"(?::\s*(?P<colon_minute>\d{2})|"
    r"시(?:\s*(?P<word_minute>\d{1,2})\s*분)?)"
    r"(?!\d)"
)
DEADLINE_WORDS = (
    "마감",
    "까지",
    "제출기한",
    "제출 기한",
    "신청기간",
    "신청 기간",
    "접수기간",
    "접수 기간",
    "납부기간",
    "납부 기간",
    "등록기간",
    "등록 기간",
    "공모기간",
    "공모 기간",
)
EVENT_WORDS = (
    "일시",
    "행사",
    "개최",
    "시행",
    "점검",
    "작업",
    "시험",
    "수업",
)


class NoticeError(RuntimeError):
    """A user-facing deterministic failure."""


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\u00a0", " ").split())


def clean_title(value: str | None) -> str:
    title = clean(value)
    if title.endswith("}") and "{" not in title:
        title = title[:-1].rstrip()
    return title


def truncate(value: str, limit: int) -> str:
    value = clean(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def validate_official_url(url: str) -> None:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NoticeError("Refused URL with an invalid port.") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in ALLOWED_HOSTS
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise NoticeError(f"Refused non-official or non-HTTPS URL: {redact_url(url)}")


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        destination = urljoin(req.full_url, newurl)
        validate_official_url(destination)
        return super().redirect_request(
            req, fp, code, msg, headers, destination
        )


def canonical_url(url: str) -> str:
    """Remove presentation-only query parameters while preserving article identity."""
    parsed = urlsplit(url)
    validate_official_url(url)
    if parsed.hostname == "yis.yonsei.ac.kr":
        allowed = {
            key: value
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key in {"mode", "articleNo"}
        }
        query = urlencode(sorted(allowed.items()))
    else:
        query = ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def fetch(url: str, *, timeout: float, max_body: int) -> tuple[bytes, str]:
    validate_official_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/html;q=0.9",
        },
    )
    opener = urllib.request.build_opener(SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            validate_official_url(final_url)
            body = response.read(max_body + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NoticeError(f"Fetch failed for {redact_url(url)}: {exc}") from exc
    if len(body) > max_body:
        raise NoticeError(
            f"Response exceeded {max_body} bytes for {redact_url(final_url)}"
        )
    return body, final_url


def normalize_published(value: str) -> tuple[str, str]:
    text = clean(value)
    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y.%m.%d",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if "%H" in fmt:
                return parsed.isoformat(timespec="seconds"), parsed.date().isoformat()
            return parsed.date().isoformat(), parsed.date().isoformat()
        except ValueError:
            continue
    raise NoticeError(f"Unsupported publication date: {text!r}")


def notice_id(source: str, url: str) -> str:
    payload = f"{source}\0{canonical_url(url)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def make_notice(
    *,
    source: str,
    title: str,
    published: str,
    publisher: str,
    url: str,
    excerpt: str = "",
) -> dict[str, str]:
    normalized_at, normalized_date = normalize_published(published)
    normalized_url = canonical_url(url)
    return {
        "id": notice_id(source, normalized_url),
        "source": source,
        "source_label": (
            "Yonsei University Notices"
            if source == "university"
            else "Yonsei Sinchon IT Service Notices"
        ),
        "title": clean_title(title),
        "published_at": normalized_at,
        "published_date": normalized_date,
        "publisher": clean(publisher),
        "url": normalized_url,
        "excerpt": truncate(excerpt, MAX_EXCERPT),
    }


def university_items(body: bytes) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise NoticeError(f"University RSS is invalid XML: {exc}") from exc
    items: list[dict[str, str]] = []
    for entry in root.findall("./channel/item"):
        link = clean(entry.findtext("link"))
        if not link:
            continue
        try:
            item = make_notice(
                source="university",
                title=entry.findtext("title") or "",
                published=entry.findtext("pubDate") or "",
                publisher=entry.findtext("author") or "Yonsei University",
                url=urljoin(UNIVERSITY_ORIGIN, link),
                excerpt=entry.findtext("description") or "",
            )
        except NoticeError:
            continue
        if item["title"]:
            items.append(item)
    return items


class ITIndexParser(HTMLParser):
    """Extract title, publisher, and date from the official IT board list."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw_items: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None
        self.buffer: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if (
            tag == "a"
            and "c-board-title" in classes
            and "articleNo=" in values.get("href", "")
        ):
            self.flush()
            self.current = {
                "title": "",
                "published": "",
                "publisher": "",
                "url": urljoin(IT_NOTICES, values["href"]),
            }
            self.capture = "title"
            self.buffer = []
        elif tag == "span" and self.current is not None:
            self.capture = "metadata"
            self.buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.capture == "title" and self.current is not None:
            self.current["title"] = clean(" ".join(self.buffer))
            self.capture = None
            self.buffer = []
        elif tag == "span" and self.capture == "metadata" and self.current is not None:
            candidate = clean(" ".join(self.buffer))
            if re.fullmatch(r"\d{4}[.-]\d{2}[.-]\d{2}", candidate):
                self.current["published"] = candidate.replace(".", "-")
            elif candidate and not self.current["publisher"]:
                self.current["publisher"] = candidate
            self.capture = None
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def flush(self) -> None:
        if (
            self.current
            and self.current["title"]
            and self.current["published"]
        ):
            self.raw_items.append(self.current)
        self.current = None
        self.capture = None
        self.buffer = []

    def close(self) -> None:
        super().close()
        self.flush()


def it_items(body: bytes) -> list[dict[str, str]]:
    parser = ITIndexParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    items: list[dict[str, str]] = []
    for raw in parser.raw_items:
        items.append(
            make_notice(
                source="it",
                title=raw["title"],
                published=raw["published"],
                publisher=raw["publisher"] or "Yonsei Sinchon IT Service",
                url=raw["url"],
            )
        )
    return items


class ArticleTextParser(HTMLParser):
    """Prefer the board article body and fall back to all visible text."""

    VOID_TAGS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.article_depth = 0
        self.all_text: list[str] = []
        self.article_text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return
        classes = set(values.get("class", "").split())
        if self.article_depth and tag not in self.VOID_TAGS:
            self.article_depth += 1
        elif classes & {"fr-view", "viewCont"}:
            self.article_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.article_depth:
            self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = clean(data)
        if not value:
            return
        self.all_text.append(value)
        if self.article_depth:
            self.article_text.append(value)

    def text(self) -> str:
        selected = self.article_text or self.all_text
        return truncate(" ".join(selected), MAX_DETAIL_TEXT)


def article_text(body: bytes) -> str:
    parser = ArticleTextParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    return parser.text()


def fetch_sources(
    source: str,
    *,
    timeout: float,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    items: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []
    errors: list[str] = []
    requested: list[tuple[str, str, Any]] = []
    if source in {"all", "university"}:
        requested.append(("university", UNIVERSITY_RSS, university_items))
    if source in {"all", "it"}:
        requested.append(("it", IT_NOTICES, it_items))
    for source_name, url, parser in requested:
        try:
            body, final_url = fetch(url, timeout=timeout, max_body=MAX_INDEX_BODY)
            parsed = parser(body)
            items.extend(parsed)
            sources.append(
                {
                    "source": source_name,
                    "url": redact_url(final_url),
                    "status": "ok",
                    "items": len(parsed),
                }
            )
        except NoticeError as exc:
            errors.append(str(exc))
            sources.append(
                {
                    "source": source_name,
                    "url": redact_url(url),
                    "status": "error",
                    "items": 0,
                }
            )
    if not items and errors:
        raise NoticeError("; ".join(errors))
    return items, sources, errors


def filter_notices(
    items: Iterable[dict[str, str]],
    *,
    contains: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[dict[str, str]]:
    needle = clean(contains).casefold() if contains else ""
    filtered: list[dict[str, str]] = []
    for item in items:
        published = date.fromisoformat(item["published_date"])
        if date_from and published < date_from:
            continue
        if date_to and published > date_to:
            continue
        haystack = " ".join(
            (item["title"], item["publisher"], item.get("excerpt", ""))
        ).casefold()
        if needle and needle not in haystack:
            continue
        filtered.append(item)
    filtered.sort(
        key=lambda item: (
            item["published_at"],
            item["source"],
            item["title"],
            item["url"],
        ),
        reverse=True,
    )
    return filtered[:limit]


def parse_iso_date(value: str | None, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise NoticeError(f"{option} must be YYYY-MM-DD") from exc


def search_payload(args: argparse.Namespace, *, limit: int | None = None) -> dict[str, Any]:
    date_from = parse_iso_date(args.date_from, "--from")
    date_to = parse_iso_date(args.date_to, "--to")
    if date_from and date_to and date_from > date_to:
        raise NoticeError("--from must not be after --to")
    items, sources, errors = fetch_sources(args.source, timeout=args.timeout)
    effective_limit = limit if limit is not None else args.limit
    results = filter_notices(
        items,
        contains=args.contains,
        date_from=date_from,
        date_to=date_to,
        limit=effective_limit,
    )
    return {
        "schema": SCHEMA,
        "operation": "search",
        "query": {
            "source": args.source,
            "contains": args.contains,
            "published_from": args.date_from,
            "published_to": args.date_to,
            "limit": effective_limit,
        },
        "sources": sources,
        "partial": bool(errors),
        "errors": errors,
        "count": len(results),
        "results": results,
    }


def infer_date(
    year: int | None,
    month: int,
    day: int,
    *,
    anchor: date,
) -> date | None:
    inferred_year = year or anchor.year
    try:
        candidate = date(inferred_year, month, day)
    except ValueError:
        return None
    # Publication/start date remains the sole inference anchor. A large
    # backwards jump represents the common December-to-January rollover,
    # while --as-of never participates in year selection.
    if year is None and (anchor - candidate).days > 120:
        try:
            candidate = date(inferred_year + 1, month, day)
        except ValueError:
            return None
    return candidate


def classify_context(context: str) -> str:
    lowered = context.casefold()
    if any(word in lowered for word in DEADLINE_WORDS):
        return "deadline"
    if any(word in lowered for word in EVENT_WORDS):
        return "event"
    return "date"


def parse_range_date_token(match: re.Match[str]) -> dict[str, Any] | None:
    value = match.group(0)
    full = DATE_FULL_RE.fullmatch(value)
    if full:
        return {
            "match": match,
            "syntax": "full",
            "year": int(full.group("year")),
            "month": int(full.group("month")),
            "day": int(full.group("day")),
        }
    korean = DATE_MONTH_DAY_RE.fullmatch(value)
    if korean:
        return {
            "match": match,
            "syntax": "korean-month-day",
            "year": None,
            "month": int(korean.group("month")),
            "day": int(korean.group("day")),
        }
    dotted = DATE_DOTTED_MONTH_DAY_RE.fullmatch(value)
    if dotted:
        return {
            "match": match,
            "syntax": "dotted-month-day",
            "year": None,
            "month": int(dotted.group("month")),
            "day": int(dotted.group("day")),
        }
    dotted_day = DATE_DOTTED_DAY_RE.fullmatch(value)
    if dotted_day:
        return {
            "match": match,
            "syntax": "dotted-day",
            "year": None,
            "month": None,
            "day": int(dotted_day.group("day")),
        }
    return None


def safe_dotted_range_token(value: str) -> bool:
    stripped = value.strip()
    # Require either the official-style trailing dot or visible whitespace
    # after the month separator. Compact values such as "v8.21" are not
    # promoted to dates merely because a range marker occurs nearby.
    return stripped.endswith(".") or bool(re.search(r"\.\s+\d", stripped))


def same_bounded_clause(fragment: str) -> bool:
    return len(fragment) <= 64 and not any(mark in fragment for mark in "\r\n;")


def normalized_time_after(
    text: str,
    *,
    token_end: int,
    next_token_start: int | None,
) -> dict[str, str]:
    right = min(len(text), token_end + 48)
    if next_token_start is not None:
        right = min(right, next_token_start)
    segment = text[token_end:right]
    for separator in ("\r", "\n", ";"):
        if separator in segment:
            segment = segment.split(separator, 1)[0]
    for match in TIME_RE.finditer(segment):
        period = match.group("period")
        hour = int(match.group("hour"))
        raw_minute = match.group("colon_minute") or match.group("word_minute")
        minute = int(raw_minute) if raw_minute is not None else 0
        if minute > 59:
            continue
        if period:
            if not 1 <= hour <= 12:
                continue
            if period == "오전":
                hour = 0 if hour == 12 else hour
            else:
                hour = hour if hour == 12 else hour + 12
        elif hour > 23:
            continue
        return {
            "time": f"{hour:02d}:{minute:02d}",
            "time_text": clean(match.group(0)),
        }
    return {}


def extract_date_mentions(
    text: str,
    *,
    anchor: date,
    as_of: date | None,
    deadline_from: date | None,
    deadline_to: date | None,
) -> list[dict[str, str]]:
    tokens = [
        token
        for match in RANGE_DATE_TOKEN_RE.finditer(text)
        if (token := parse_range_date_token(match)) is not None
    ]
    range_occurrences: dict[
        tuple[int, int, str], tuple[dict[str, Any], date]
    ] = {}
    ranged_spans: set[tuple[int, int]] = set()
    for separator in RANGE_SEPARATOR_RE.finditer(text):
        before = [
            token
            for token in tokens
            if token["match"].end() <= separator.start()
            and same_bounded_clause(
                text[token["match"].end() : separator.start()]
            )
            and token["syntax"] != "dotted-day"
            and (
                token["syntax"] != "dotted-month-day"
                or safe_dotted_range_token(token["match"].group(0))
            )
        ]
        after = [
            token
            for token in tokens
            if token["match"].start() >= separator.end()
            and token["match"].start() - separator.end() <= 32
            and same_bounded_clause(
                text[separator.end() : token["match"].start()]
            )
            and not (
                separator.group(0) == "부터"
                and "까지"
                in text[separator.end() : token["match"].start()]
            )
            and (
                token["syntax"] != "dotted-month-day"
                or safe_dotted_range_token(token["match"].group(0))
            )
        ]
        if not before or not after:
            continue
        start_token = max(before, key=lambda token: token["match"].end())
        end_token = min(after, key=lambda token: token["match"].start())
        start_candidate = infer_date(
            start_token["year"],
            start_token["month"],
            start_token["day"],
            anchor=anchor,
        )
        if start_candidate is None:
            continue
        end_candidate = infer_date(
            end_token["year"],
            end_token["month"] or start_candidate.month,
            end_token["day"],
            anchor=start_candidate,
        )
        if end_candidate is None:
            continue
        start_match = start_token["match"]
        end_match = end_token["match"]
        start_span = (start_match.start(), start_match.end())
        end_span = (end_match.start(), end_match.end())
        range_occurrences[(*start_span, "start")] = (
            start_token,
            start_candidate,
        )
        range_occurrences[(*end_span, "end")] = (end_token, end_candidate)
        ranged_spans.update((start_span, end_span))

    occurrences = list(range_occurrences.items())
    for token in tokens:
        match = token["match"]
        span = (match.start(), match.end())
        if span in ranged_spans or token["syntax"] in {
            "dotted-month-day",
            "dotted-day",
        }:
            continue
        candidate = infer_date(
            token["year"],
            token["month"],
            token["day"],
            anchor=anchor,
        )
        if candidate is None:
            continue
        occurrences.append(((*span, "single"), (token, candidate)))

    accepted_spans = sorted(
        {(key[0], key[1]) for key, _ in occurrences},
        key=lambda span: (span[0], span[1]),
    )
    next_start_by_span: dict[tuple[int, int], int | None] = {}
    for index, span in enumerate(accepted_spans):
        next_start_by_span[span] = (
            accepted_spans[index + 1][0]
            if index + 1 < len(accepted_spans)
            else None
        )

    mentions: list[dict[str, str]] = []
    for (start, end, range_role), (token, candidate) in occurrences:
        if deadline_from and candidate < deadline_from:
            continue
        if deadline_to and candidate > deadline_to:
            continue
        match = token["match"]
        left = max(0, start - MAX_CONTEXT // 2)
        right = min(len(text), end + MAX_CONTEXT // 2)
        context = truncate(text[left:right], MAX_CONTEXT)
        kind = classify_context(context)
        status = "unknown"
        if as_of:
            status = "past" if candidate < as_of else "upcoming"
        mention = {
            "date": candidate.isoformat(),
            "kind": kind,
            "status": status,
            "range_role": range_role,
            "matched_text": clean(match.group(0)),
            "context": context,
        }
        mention.update(
            normalized_time_after(
                text,
                token_end=end,
                next_token_start=next_start_by_span[(start, end)],
            )
        )
        mentions.append(mention)
    timed_mention_groups = {
        (mention["date"], mention["kind"], mention["range_role"])
        for mention in mentions
        if mention.get("time")
    }
    mentions = [
        mention
        for mention in mentions
        if mention.get("time")
        or (
            mention["date"],
            mention["kind"],
            mention["range_role"],
        )
        not in timed_mention_groups
    ]
    unique: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for mention in mentions:
        key = (
            mention["date"],
            mention["kind"],
            mention.get("time", ""),
            mention["range_role"],
        )
        existing = unique.get(key)
        if existing is None or len(mention["context"]) < len(existing["context"]):
            unique[key] = mention
    return sorted(
        unique.values(),
        key=lambda item: (
            item["date"],
            item.get("time", ""),
            item["range_role"],
            item["kind"],
            item["context"],
        ),
    )


def deadlines_payload(args: argparse.Namespace) -> dict[str, Any]:
    as_of = parse_iso_date(args.as_of, "--as-of")
    deadline_from = parse_iso_date(args.deadline_from, "--deadline-from")
    deadline_to = parse_iso_date(args.deadline_to, "--deadline-to")
    if deadline_from and deadline_to and deadline_from > deadline_to:
        raise NoticeError("--deadline-from must not be after --deadline-to")
    base = search_payload(args, limit=args.limit)
    results: list[dict[str, Any]] = []
    detail_errors: list[str] = []
    for notice in base["results"]:
        text_parts = [notice["title"], notice.get("excerpt", "")]
        detail_status = "not-needed"
        if args.fetch_details:
            try:
                body, _ = fetch(
                    notice["url"],
                    timeout=args.timeout,
                    max_body=MAX_DETAIL_BODY,
                )
                text_parts.append(article_text(body))
                detail_status = "ok"
            except NoticeError as exc:
                detail_status = "error"
                detail_errors.append(f"{notice['id']}: {exc}")
        # A yearless date belongs to the notice's publication year.  --as-of
        # only classifies that resolved date as upcoming or past.
        anchor = date.fromisoformat(notice["published_date"])
        mentions = extract_date_mentions(
            " ".join(text_parts),
            anchor=anchor,
            as_of=as_of,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
        )
        if not args.include_all_dates:
            mentions = [item for item in mentions if item["kind"] == "deadline"]
        if mentions or args.include_empty:
            result = {key: value for key, value in notice.items() if key != "excerpt"}
            result["detail_status"] = detail_status
            result["date_mentions"] = mentions
            results.append(result)
    return {
        "schema": SCHEMA,
        "operation": "deadlines",
        "query": {
            **base["query"],
            "as_of": args.as_of,
            "deadline_from": args.deadline_from,
            "deadline_to": args.deadline_to,
            "fetch_details": args.fetch_details,
            "include_all_dates": args.include_all_dates,
        },
        "sources": base["sources"],
        "partial": base["partial"] or bool(detail_errors),
        "errors": [*base["errors"], *detail_errors],
        "count": len(results),
        "results": results,
    }


def state_record(item: dict[str, str]) -> dict[str, str]:
    return {
        key: item[key]
        for key in (
            "id",
            "source",
            "title",
            "published_at",
            "published_date",
            "publisher",
            "url",
        )
    }


def source_state_records(
    sources: Iterable[dict[str, Any]],
) -> list[dict[str, str | int]]:
    records: list[dict[str, str | int]] = []
    for source in sources:
        name = source.get("source")
        status = source.get("status")
        raw_count = source.get("items", 0)
        if not isinstance(name, str) or status not in {"ok", "error"}:
            continue
        count = raw_count if isinstance(raw_count, int) and raw_count >= 0 else 0
        records.append({"source": name, "status": status, "items": count})
    return records


def healthy_source_counts(state: dict[str, Any] | None) -> dict[str, int]:
    if state is None:
        return {}

    # States written before source-health snapshots were introduced still prove
    # a successful non-empty parse through their retained notice records.
    counts: dict[str, int] = {}
    for item in state.get("items", []):
        source = item.get("source") if isinstance(item, dict) else None
        if isinstance(source, str):
            counts[source] = counts.get(source, 0) + 1

    saved_sources = state.get("sources")
    if not isinstance(saved_sources, list):
        return counts
    for source in source_state_records(saved_sources):
        name = str(source["source"])
        if source["status"] == "ok" and int(source["items"]) > 0:
            counts[name] = int(source["items"])
        else:
            counts.pop(name, None)
    return counts


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoticeError(f"Cannot read state file {path}: {exc}") from exc
    if payload.get("schema") != STATE_SCHEMA or not isinstance(
        payload.get("items"), list
    ):
        raise NoticeError(f"Unsupported state file schema in {path}")
    return payload


def write_state(path: Path, payload: dict[str, Any]) -> None:
    if not path.parent.is_dir():
        raise NoticeError(f"State directory does not exist: {path.parent}")
    serialized = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        raise NoticeError(f"Cannot write state file {path}: {exc}") from exc


def changes_payload(args: argparse.Namespace) -> dict[str, Any]:
    # Always retain the complete bounded source window before comparing state.
    base = search_payload(args, limit=100)
    current = [state_record(item) for item in base["results"]]
    state_path = Path(args.state).expanduser().resolve()
    previous_state = load_state(state_path)
    requested_query = {
        "source": args.source,
        "contains": args.contains,
        "published_from": args.date_from,
        "published_to": args.date_to,
    }
    if (
        previous_state is not None
        and previous_state.get("query") != requested_query
        and not args.reset
    ):
        raise NoticeError(
            "State query differs from this run; choose another --state path "
            "or pass --reset to establish a new baseline."
        )
    initialized = previous_state is None or args.reset
    if args.reset:
        previous_state = None
    current_sources = source_state_records(base["sources"])
    previous_healthy_counts = healthy_source_counts(previous_state)
    source_health_issues = [
        {
            "source": source["source"],
            "previous_healthy_count": previous_healthy_counts[source["source"]],
            "current_count": 0,
            "reason": "zero_items_after_healthy_nonempty_baseline",
        }
        for source in current_sources
        if source["status"] == "ok"
        and source["items"] == 0
        and previous_healthy_counts.get(str(source["source"]), 0) > 0
    ]
    suspicious_empty_sources = {
        str(issue["source"]) for issue in source_health_issues
    }
    previous = {
        item["id"]: item for item in (previous_state or {}).get("items", [])
    }
    current_by_id = {item["id"]: item for item in current}
    added = [
        item for key, item in current_by_id.items() if key not in previous
    ]
    successful_sources = {
        source["source"] for source in base["sources"] if source["status"] == "ok"
    } - suspicious_empty_sources
    missing = [
        item
        for key, item in previous.items()
        if key not in current_by_id and item["source"] in successful_sources
    ]
    updated: list[dict[str, Any]] = []
    for key in sorted(previous.keys() & current_by_id.keys()):
        before = previous[key]
        after = current_by_id[key]
        changed_fields = [
            field
            for field in ("title", "published_at", "publisher", "url")
            if before.get(field) != after.get(field)
        ]
        if changed_fields:
            updated.append(
                {
                    "id": key,
                    "changed_fields": changed_fields,
                    "before": before,
                    "after": after,
                }
            )
    added.sort(key=lambda item: (item["published_at"], item["id"]), reverse=True)
    missing.sort(key=lambda item: (item["published_at"], item["id"]), reverse=True)
    if initialized:
        # Establishing a baseline is not an alert storm.
        added_for_output: list[dict[str, str]] = []
    else:
        added_for_output = added
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    next_state = {
        "schema": STATE_SCHEMA,
        "observed_at": observed_at,
        "query": requested_query,
        "items": current,
        "sources": current_sources,
    }
    state_write_blocked_reason: str | None = None
    if base["partial"]:
        state_write_blocked_reason = "partial_fetch"
    elif source_health_issues:
        state_write_blocked_reason = "suspicious_empty_source"
    elif args.dry_run:
        state_write_blocked_reason = "dry_run"
    else:
        write_state(state_path, next_state)
    return {
        "schema": SCHEMA,
        "operation": "changes",
        "state_path": str(state_path),
        "state_written": state_write_blocked_reason is None,
        "state_write_blocked_reason": state_write_blocked_reason,
        "initialized": initialized,
        "observed_at": observed_at,
        "window_semantics": (
            "missing means absent from the current bounded source window, "
            "not confirmed deletion"
        ),
        "sources": base["sources"],
        "source_health_issues": source_health_issues,
        "partial": base["partial"],
        "errors": base["errors"],
        "current_count": len(current),
        "changes": {
            "added": added_for_output,
            "updated": updated,
            "missing_from_current_window": missing if not initialized else [],
        },
    }


def add_common_query_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        choices=("all", "university", "it"),
        default="all",
    )
    parser.add_argument("--contains", help="Case-insensitive metadata text filter.")
    parser.add_argument("--from", dest="date_from", help="Publication date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="date_to", help="Publication date, YYYY-MM-DD.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds (1-30).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search, extract deadlines, and detect changes in official Yonsei notices."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    search = subparsers.add_parser("search", help="Search globally sorted notices.")
    add_common_query_arguments(search)
    search.add_argument("--limit", type=int, default=20)

    deadlines = subparsers.add_parser(
        "deadlines", help="Extract bounded deadline mentions from official notices."
    )
    add_common_query_arguments(deadlines)
    deadlines.add_argument("--limit", type=int, default=10)
    deadlines.add_argument("--as-of", help="Classify dates relative to YYYY-MM-DD.")
    deadlines.add_argument("--deadline-from", help="Mention date lower bound.")
    deadlines.add_argument("--deadline-to", help="Mention date upper bound.")
    deadlines.add_argument(
        "--no-fetch-details",
        dest="fetch_details",
        action="store_false",
        help="Use title and RSS excerpt only.",
    )
    deadlines.set_defaults(fetch_details=True)
    deadlines.add_argument("--include-all-dates", action="store_true")
    deadlines.add_argument("--include-empty", action="store_true")

    changes = subparsers.add_parser(
        "changes", help="Compare the current bounded window with explicit state."
    )
    add_common_query_arguments(changes)
    changes.add_argument("--state", required=True, help="Explicit JSON state path.")
    changes.add_argument("--dry-run", action="store_true")
    changes.add_argument(
        "--reset",
        action="store_true",
        help="Replace an existing state file with a quiet new baseline.",
    )

    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not 1.0 <= args.timeout <= 30.0:
        raise NoticeError("--timeout must be between 1 and 30 seconds")
    if hasattr(args, "limit") and not 1 <= args.limit <= 50:
        raise NoticeError("--limit must be between 1 and 50")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        validate_args(args)
        if args.operation == "search":
            payload = search_payload(args)
        elif args.operation == "deadlines":
            payload = deadlines_payload(args)
        else:
            payload = changes_payload(args)
        emit(payload)
        return 0
    except NoticeError as exc:
        emit(
            {
                "schema": SCHEMA,
                "operation": args.operation,
                "error": {"type": "notice_error", "message": str(exc)},
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
