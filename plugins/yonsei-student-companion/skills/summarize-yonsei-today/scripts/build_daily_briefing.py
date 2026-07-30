#!/usr/bin/env python3
"""Sort and deduplicate already collected Yonsei daily-briefing items."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SEOUL = ZoneInfo("Asia/Seoul")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SEOUL)
    return parsed.astimezone(SEOUL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--now", help="ISO 8601 time; defaults to current Seoul time.")
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(SEOUL)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    seen: set[tuple[str, str]] = set()
    sections = {"지금": [], "오늘": [], "7일 안": [], "확인 필요": []}
    for item in items:
        title = str(item.get("title", "")).strip()
        due_value = str(item.get("due_at", "")).strip()
        if not title:
            continue
        key = (title.casefold(), due_value)
        if key in seen:
            continue
        seen.add(key)
        if item.get("needs_review") or not due_value:
            section = "확인 필요"
            sort_time = now + timedelta(days=3650)
        else:
            sort_time = parse_time(due_value)
            delta = sort_time - now
            if timedelta(minutes=-30) <= delta <= timedelta(hours=2):
                section = "지금"
            elif sort_time.date() == now.date():
                section = "오늘"
            elif now < sort_time <= now + timedelta(days=7):
                section = "7일 안"
            else:
                continue
        normalized = {
            "title": title,
            "source": str(item.get("source", "")).strip(),
            "due_at": due_value or None,
            "status": str(item.get("status", "")).strip() or None,
        }
        sections[section].append((sort_time, normalized))
    result = {
        section: [item for _, item in sorted(values, key=lambda pair: pair[0])][:5]
        for section, values in sections.items()
        if values
    }
    print(
        json.dumps(
            {
                "schema": "yonsei-daily-briefing/v1",
                "observed_at": now.isoformat(),
                "sections": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
