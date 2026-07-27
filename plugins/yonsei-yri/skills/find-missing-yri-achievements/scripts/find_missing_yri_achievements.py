#!/usr/bin/env python3
"""Find identifier-based missing candidates in a supplied YRI snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "yonsei-yri-achievement-reconciliation/v1"
ERROR_SCHEMA = "yonsei-yri-snapshot-error/v1"
FORBIDDEN_KEYS = {
    "password", "passwd", "userpw", "otp", "token", "access_token",
    "refresh_token", "cookie", "cookies", "session", "sessionid",
}
TYPE_ALIASES = {
    "논문": "article", "article": "article",
    "저역서": "book", "book": "book",
    "전시작품": "exhibition", "exhibition": "exhibition",
    "연구비": "funding", "funding": "funding",
    "지식재산": "intellectual-property",
    "intellectual-property": "intellectual-property",
    "기술이전": "technology-transfer",
    "technology-transfer": "technology-transfer",
    "수상": "award", "award": "award",
    "학술활동": "academic-activity",
    "academic-activity": "academic-activity",
    "보고서": "report", "report": "report",
}


class InputError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def reject_json_constant(value: str) -> None:
    raise InputError("invalid-json-number", "Non-finite JSON numbers are not allowed.")


def scan_credentials(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise InputError(
                    "credential-field-not-allowed",
                    "Credential or session fields are not accepted.",
                    f"{path}.{key}",
                )
            scan_credentials(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_credentials(item, f"{path}[{index}]")


def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("missing-text", "A non-empty text value is required.", path)
    return value.strip()


def optional_text(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InputError("invalid-text", "Expected text or null.", path)
    return value.strip() or None


def normalize_type(value: Any, path: str) -> str:
    raw = required_text(value, path)
    key = raw.lower() if raw.isascii() else raw
    if key not in TYPE_ALIASES:
        raise InputError(
            "unknown-achievement-type",
            "Achievement type is outside the declared YRI type contract.",
            path,
        )
    return TYPE_ALIASES[key]


def normalize_year(value: Any, path: str) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1000 <= value <= 9999:
        raise InputError("invalid-year", "Year must be a four-digit integer.", path)
    return value


def normalized_title(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", folded).strip()


def normalized_doi(value: Any, path: str) -> Any:
    text = optional_text(value, path)
    if text is None:
        return None
    normalized = text.casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized.strip()


def normalize_row(raw: Any, path: str, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise InputError("invalid-achievement", "Each achievement must be an object.", path)
    title = required_text(raw.get("title"), f"{path}.title")
    return {
        "source_index": index,
        "record_id": optional_text(raw.get("record_id"), f"{path}.record_id"),
        "type": normalize_type(raw.get("type"), f"{path}.type"),
        "title": title,
        "year": normalize_year(raw.get("year"), f"{path}.year"),
        "doi": normalized_doi(raw.get("doi"), f"{path}.doi"),
        "kri_id": optional_text(raw.get("kri_id"), f"{path}.kri_id"),
        "issn": optional_text(raw.get("issn"), f"{path}.issn"),
        "_title_key": normalized_title(title),
    }


def match_key(row: dict[str, Any]) -> Any:
    if row["doi"]:
        return ("doi", row["doi"])
    if row["kri_id"]:
        return ("kri_id", row["kri_id"].casefold())
    if row["year"] is not None:
        return ("title-year-type", row["type"], row["_title_key"], row["year"])
    return None


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "source_index", "record_id", "type", "title", "year",
            "doi", "kri_id", "issn",
        )
    }


def transform(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InputError("invalid-root", "Input must be a JSON object.")
    scan_credentials(data)
    captured_at = required_text(data.get("captured_at"), "$.captured_at")
    if data.get("owner_scope") != "self":
        raise InputError("scope-not-self", 'owner_scope must be exactly "self".', "$.owner_scope")
    source_format = data.get("source_format", "json")
    if source_format not in {"json", "excel-transcribed"}:
        raise InputError(
            "unsupported-source-format",
            "source_format must be json or excel-transcribed.",
            "$.source_format",
        )
    raw_reference = data.get("reference_achievements")
    raw_yri = data.get("yri_achievements")
    if not isinstance(raw_reference, list):
        raise InputError(
            "invalid-reference-achievements",
            "reference_achievements must be an array.",
            "$.reference_achievements",
        )
    if not isinstance(raw_yri, list):
        raise InputError(
            "invalid-yri-achievements",
            "yri_achievements must be an array.",
            "$.yri_achievements",
        )
    references = [
        normalize_row(row, f"$.reference_achievements[{index}]", index)
        for index, row in enumerate(raw_reference)
    ]
    yri_rows = [
        normalize_row(row, f"$.yri_achievements[{index}]", index)
        for index, row in enumerate(raw_yri)
    ]

    yri_by_key = {}
    for row in yri_rows:
        key = match_key(row)
        if key is not None:
            yri_by_key.setdefault(key, []).append(row)

    missing = []
    matched = []
    ambiguous = []
    unresolved = []
    for reference in references:
        key = match_key(reference)
        if key is None:
            unresolved.append(
                {
                    "reference": public_row(reference),
                    "reason": "no-doi-kri-id-or-title-year-type-key",
                }
            )
            continue
        candidates = yri_by_key.get(key, [])
        basis = key[0]
        if not candidates:
            missing.append(
                {"reference": public_row(reference), "match_basis": basis}
            )
        elif len(candidates) == 1:
            matched.append(
                {
                    "reference_index": reference["source_index"],
                    "yri_index": candidates[0]["source_index"],
                    "match_basis": basis,
                }
            )
        else:
            ambiguous.append(
                {
                    "reference": public_row(reference),
                    "candidate_yri_indexes": [
                        row["source_index"] for row in candidates
                    ],
                    "match_basis": basis,
                }
            )

    duplicates = []
    for key, rows in sorted(yri_by_key.items(), key=lambda item: repr(item[0])):
        if len(rows) > 1:
            duplicates.append(
                {
                    "match_basis": key[0],
                    "yri_indexes": [row["source_index"] for row in rows],
                }
            )

    return {
        "schema": OUTPUT_SCHEMA,
        "provenance": {
            "mode": "user-supplied-snapshot",
            "source_format": source_format,
            "captured_at": captured_at,
            "owner_scope": "self",
            "live_system_queried": False,
        },
        "summary": {
            "reference_count": len(references),
            "yri_snapshot_count": len(yri_rows),
            "matched_count": len(matched),
            "missing_candidate_count": len(missing),
            "ambiguous_count": len(ambiguous),
            "unresolved_count": len(unresolved),
        },
        "matched": matched,
        "missing_candidates": missing,
        "ambiguous_matches": ambiguous,
        "possible_duplicates": duplicates,
        "unresolved_references": unresolved,
        "complete": not ambiguous and not unresolved and not duplicates,
        "writes_performed": False,
        "submitted": False,
    }


def load_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_constant=reject_json_constant)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="JSON path or - for stdin")
    args = parser.parse_args()
    try:
        result = transform(load_input(args.input))
    except (InputError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({
            "schema": ERROR_SCHEMA,
            "error": {
                "code": getattr(exc, "code", "invalid-input"),
                "message": str(exc),
                "path": getattr(exc, "path", "$"),
            },
            "live_system_queried": False,
            "writes_performed": False,
            "submitted": False,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
