#!/usr/bin/env python3
"""Check one whitelisted ERP payment record in a user-supplied offline snapshot."""

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
STATUSES = {
    "requested",
    "reviewing",
    "approved",
    "scheduled",
    "paid",
    "failed",
    "returned",
    "cancelled",
    "unverified",
}
TOP_LEVEL_FIELDS = {"schema_version", "source_kind", "exported_at", "records"}
RECORD_FIELDS = {
    "payment_id",
    "request_id",
    "category",
    "payment_kind",
    "payee_label",
    "status",
    "amount",
    "currency",
    "requested_at",
    "scheduled_date",
    "paid_at",
    "failure_code",
    "updated_at",
}
REQUIRED_FIELDS = {"payment_id", "request_id", "category", "payment_kind", "status", "amount", "currency"}
STRING_FIELDS = RECORD_FIELDS - {"amount"}


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
        value = record.get(field)
        if value is None and field not in REQUIRED_FIELDS:
            continue
        if not isinstance(value, str) or (field in REQUIRED_FIELDS and not value.strip()):
            fail("invalid_field_type", "records[%d].%s must be a string." % (index, field))
        if len(value) > 500:
            fail("field_too_long", "records[%d].%s is too long." % (index, field))
    if record["category"] not in CATEGORIES:
        fail("unsupported_category", "records[%d] has an unsupported category." % index)
    if record["status"] not in STATUSES:
        fail("unsupported_status", "records[%d] has an unsupported status." % index)
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
    ids = [record["payment_id"] for record in validated]
    if len(ids) != len(set(ids)):
        fail("duplicate_payment_id", "payment_id values must be unique.")
    return validated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help=".json path or '-' for stdin")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--payment-id")
    selector.add_argument("--request-id")
    args = parser.parse_args()
    try:
        raw, snapshot = read_input(args.input)
        records = validate_snapshot(snapshot)
        if args.payment_id:
            matches = [record for record in records if record["payment_id"] == args.payment_id]
            selector_value = {"payment_id": args.payment_id}
        else:
            matches = [record for record in records if record["request_id"] == args.request_id]
            selector_value = {"request_id": args.request_id}
        if not matches:
            fail("payment_not_found", "No payment matches the supplied selector.")
        if len(matches) != 1:
            fail("ambiguous_payment", "The supplied selector matches multiple payment records.")
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA,
                    "operation": "check-erp-payment-status",
                    "ok": True,
                    "source_mode": "offline_user_supplied_snapshot",
                    "live_data": False,
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                    "snapshot_exported_at": snapshot.get("exported_at"),
                    "selector": selector_value,
                    "payment": matches[0],
                    "settlement_verified": False,
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
                    "operation": "check-erp-payment-status",
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
