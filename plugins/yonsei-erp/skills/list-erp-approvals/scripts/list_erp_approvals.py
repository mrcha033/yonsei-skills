#!/usr/bin/env python3
"""List whitelisted ERP approval metadata from a user-supplied offline snapshot."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

INPUT_SCHEMA = "yonsei-offline-snapshot/v1"
OUTPUT_SCHEMA = "yonsei-offline-result/v1"
MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 10000
SOURCE_KINDS = {"user_supplied_json", "excel_transcribed_json"}
CATEGORIES = {"personnel", "finance", "budget", "purchasing", "facilities"}
STATUSES = {"pending", "in_review", "approved", "rejected", "returned", "cancelled", "completed"}
TOP_LEVEL_FIELDS = {"schema_version", "source_kind", "exported_at", "records"}
RECORD_FIELDS = {
    "approval_id",
    "category",
    "title",
    "status",
    "requesting_unit",
    "submitted_at",
    "updated_at",
    "due_date",
    "amount",
    "currency",
    "current_stage",
    "my_action_required",
}
REQUIRED_FIELDS = {"approval_id", "category", "title", "status", "my_action_required"}
STRING_FIELDS = RECORD_FIELDS - {"amount", "my_action_required"}


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
                fail("input_too_large", "Snapshot exceeds the 5 MiB input limit.")
            raw = path.read_bytes()
        except OSError as exc:
            fail("input_read_failed", str(exc))
    if len(raw) > MAX_INPUT_BYTES:
        fail("input_too_large", "Snapshot exceeds the 5 MiB input limit.")
    try:
        return raw, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("invalid_json", str(exc))


def validate_string(record, field, required=False):
    value = record.get(field)
    if value is None and not required:
        return
    if not isinstance(value, str) or (required and not value.strip()):
        fail("invalid_field_type", "%s must be a non-empty string." % field)
    if len(value) > (300 if field == "title" else 500):
        fail("field_too_long", "%s is too long." % field)


def validate_record(record, index):
    if not isinstance(record, dict):
        fail("invalid_record", "records[%d] must be an object." % index)
    unknown = sorted(set(record) - RECORD_FIELDS)
    if unknown:
        fail(
            "unknown_record_fields",
            "records[%d] contains non-whitelisted fields: %s" % (index, ", ".join(unknown)),
        )
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        fail("missing_record_fields", "records[%d] is missing: %s" % (index, ", ".join(missing)))
    for field in STRING_FIELDS:
        validate_string(record, field, required=field in REQUIRED_FIELDS)
    if record["category"] not in CATEGORIES:
        fail("unsupported_category", "records[%d] has an unsupported category." % index)
    if record["status"] not in STATUSES:
        fail("unsupported_status", "records[%d] has an unsupported status." % index)
    if not isinstance(record["my_action_required"], bool):
        fail("invalid_action_flag", "records[%d].my_action_required must be boolean." % index)
    if "amount" in record:
        amount = record["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            fail("invalid_amount", "records[%d].amount must be a non-negative number." % index)
    return {field: record[field] for field in RECORD_FIELDS if field in record}


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
    records = data.get("records")
    if not isinstance(records, list):
        fail("invalid_records", "records must be an array.")
    if len(records) > MAX_RECORDS:
        fail("too_many_records", "Snapshot exceeds the 10,000-record limit.")
    validated = [validate_record(record, index) for index, record in enumerate(records)]
    ids = [record["approval_id"] for record in validated]
    if len(ids) != len(set(ids)):
        fail("duplicate_approval_id", "approval_id values must be unique.")
    return validated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help=".json path or '-' for stdin")
    parser.add_argument("--category", choices=sorted(CATEGORIES))
    parser.add_argument("--status", choices=sorted(STATUSES))
    parser.add_argument("--action-required-only", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        if args.limit < 1 or args.limit > 500:
            fail("invalid_limit", "limit must be between 1 and 500.")
        raw, snapshot = read_input(args.input)
        records = validate_snapshot(snapshot)
        if args.category:
            records = [record for record in records if record["category"] == args.category]
        if args.status:
            records = [record for record in records if record["status"] == args.status]
        if args.action_required_only:
            records = [record for record in records if record["my_action_required"]]
        records.sort(
            key=lambda record: (record.get("due_date", ""), record["approval_id"]),
        )
        records = records[: args.limit]
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA,
                    "operation": "list-erp-approvals",
                    "ok": True,
                    "source_mode": "offline_user_supplied_snapshot",
                    "live_data": False,
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                    "snapshot_exported_at": snapshot.get("exported_at"),
                    "filters": {
                        "category": args.category,
                        "status": args.status,
                        "action_required_only": args.action_required_only,
                        "limit": args.limit,
                    },
                    "record_count": len(records),
                    "records": records,
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
                    "operation": "list-erp-approvals",
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
