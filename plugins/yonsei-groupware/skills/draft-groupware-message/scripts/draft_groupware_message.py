#!/usr/bin/env python3
"""Create a review-only groupware message draft from a user-supplied snapshot."""

import hashlib
import json
import sys
import argparse
from pathlib import Path

INPUT_SCHEMA = "yonsei-offline-snapshot/v1"
OUTPUT_SCHEMA = "yonsei-offline-result/v1"
MAX_INPUT_BYTES = 1024 * 1024
SOURCE_KINDS = {"user_supplied_json", "excel_transcribed_json"}
CHANNELS = {"official_document", "sms", "fax", "e_sop", "messenger"}
TOP_LEVEL_FIELDS = {"schema_version", "source_kind", "exported_at", "draft"}
DRAFT_FIELDS = {
    "channel",
    "recipient_label",
    "subject",
    "greeting",
    "purpose",
    "facts",
    "requested_action",
    "deadline",
    "sender_unit",
}
REQUIRED_FIELDS = {"channel", "recipient_label", "subject", "purpose", "facts", "sender_unit"}
STRING_FIELDS = DRAFT_FIELDS - {"facts"}


class SnapshotError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code, message):
    raise SnapshotError(code, message)


def read_input(path_value):
    if path_value == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = Path(path_value)
        if path.suffix.lower() != ".json":
            fail("unsupported_input_format", "Input must be a .json file or '-' for JSON stdin.")
        try:
            if path.stat().st_size > MAX_INPUT_BYTES:
                fail("input_too_large", "Snapshot exceeds the 1 MiB input limit.")
            raw = path.read_bytes()
        except OSError as exc:
            fail("input_read_failed", str(exc))
    if len(raw) > MAX_INPUT_BYTES:
        fail("input_too_large", "Snapshot exceeds the 1 MiB input limit.")
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("invalid_json", str(exc))


def validate_snapshot(data):
    if not isinstance(data, dict):
        fail("invalid_snapshot", "Snapshot root must be an object.")
    unknown = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unknown:
        fail("unknown_top_level_fields", "Snapshot contains unknown fields: %s" % ", ".join(unknown))
    if data.get("schema_version") != INPUT_SCHEMA:
        fail("unsupported_schema", "schema_version must be %s." % INPUT_SCHEMA)
    if data.get("source_kind") not in SOURCE_KINDS:
        fail("unsupported_source_kind", "source_kind must identify a supplied JSON snapshot.")
    if "exported_at" in data and not isinstance(data["exported_at"], str):
        fail("invalid_exported_at", "exported_at must be a string when present.")
    draft = data.get("draft")
    if not isinstance(draft, dict):
        fail("invalid_draft", "draft must be an object.")
    unknown = sorted(set(draft) - DRAFT_FIELDS)
    if unknown:
        fail("unknown_draft_fields", "draft contains non-whitelisted fields: %s" % ", ".join(unknown))
    missing = sorted(REQUIRED_FIELDS - set(draft))
    if missing:
        fail("missing_draft_fields", "draft is missing: %s" % ", ".join(missing))
    for field in STRING_FIELDS:
        value = draft.get(field)
        if value is None and field not in REQUIRED_FIELDS:
            continue
        if not isinstance(value, str) or (field in REQUIRED_FIELDS and not value.strip()):
            fail("invalid_field_type", "draft.%s must be a string." % field)
        limit = 500 if field in {"purpose", "requested_action"} else 300
        if len(value) > limit:
            fail("field_too_long", "draft.%s is too long." % field)
    if draft["channel"] not in CHANNELS:
        fail("unsupported_channel", "draft.channel is unsupported.")
    facts = draft["facts"]
    if not isinstance(facts, list) or not facts or len(facts) > 20:
        fail("invalid_facts", "draft.facts must contain 1 to 20 strings.")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 500 for value in facts):
        fail("invalid_facts", "draft.facts contains an invalid value.")
    return {field: draft[field] for field in DRAFT_FIELDS if field in draft}


def render_body(draft):
    lines = [draft.get("greeting", "안녕하세요."), "", draft["purpose"].strip()]
    lines.extend(["", "확인 사항:"])
    lines.extend("- " + fact.strip() for fact in draft["facts"])
    if draft.get("requested_action"):
        lines.extend(["", "요청 사항: " + draft["requested_action"].strip()])
    if draft.get("deadline"):
        lines.append("기한: " + draft["deadline"].strip())
    lines.extend(["", draft["sender_unit"].strip()])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help=".json path or '-' for stdin")
    args = parser.parse_args()
    try:
        raw, snapshot = read_input(args.input)
        draft = validate_snapshot(snapshot)
        result_draft = {
            "channel": draft["channel"],
            "recipient_label": draft["recipient_label"],
            "subject": draft["subject"],
            "body": render_body(draft),
            "sender_unit": draft["sender_unit"],
        }
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA,
                    "operation": "draft-groupware-message",
                    "ok": True,
                    "source_mode": "offline_user_supplied_snapshot",
                    "live_data": False,
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                    "snapshot_exported_at": snapshot.get("exported_at"),
                    "draft": result_draft,
                    "requires_human_review": True,
                    "recipient_resolved": False,
                    "send_performed": False,
                    "fax_performed": False,
                    "share_performed": False,
                    "submit_performed": False,
                    "mutations_performed": [],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    except SnapshotError as exc:
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA,
                    "operation": "draft-groupware-message",
                    "ok": False,
                    "live_data": False,
                    "error": {"code": exc.code, "message": exc.message},
                    "mutations_performed": [],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
