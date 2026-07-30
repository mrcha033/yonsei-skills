#!/usr/bin/env python3
"""Resolve a plain-language request against packaged student portal routes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", value.lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument(
        "--campus",
        choices=("common", "sinchon", "mirae"),
        help="Use only when the service differs by campus.",
    )
    args = parser.parse_args()
    catalog_path = Path(__file__).resolve().parent.parent / "references" / "services.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    query = normalized(args.query)
    matches = []
    for service in catalog["services"]:
        if args.campus and service["campus"] not in {"common", args.campus}:
            continue
        aliases = [service["label"], *service["aliases"]]
        scores = [
            3 if normalized(alias) == query else 2
            if normalized(alias) in query else 1
            if query in normalized(alias) else 0
            for alias in aliases
        ]
        score = max(scores)
        if score:
            matches.append((score, service))
    matches.sort(key=lambda item: (-item[0], item[1]["label"]))
    best = [service for score, service in matches if score == matches[0][0]] if matches else []
    state = "resolved" if len(best) == 1 else "ambiguous" if best else "not_found"
    print(
        json.dumps(
            {
                "schema": "yonsei-portal-route/v1",
                "state": state,
                "matches": best[:5],
                "portal": catalog["portal"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if state != "not_found" else 2


if __name__ == "__main__":
    raise SystemExit(main())
