#!/usr/bin/env python3
"""Search a whitelisted, explicitly supplied groupware document export offline."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

INPUT_SCHEMA = "yonsei-offline-snapshot/v1"
OUTPUT_SCHEMA = "yonsei-offline-result/v1"
REQUIRED_EXPORT_SCOPE = "explicit_user_supplied_export"
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 20000
SOURCE_KINDS = {"user_supplied_json", "excel_transcribed_json"}
DOCUMENT_TYPES = {
    "official_document_inbound",
    "official_document_outbound",
    "electronic_approval",
    "external_admin_network",
    "e_sop",
    "sms_record",
    "fax_record",
    "messenger_record",
}
STATUSES = {"draft", "received", "sent", "in_review", "approved", "rejected", "returned", "archived", "cancelled"}
TOP_LEVEL_FIELDS = {"schema_version", "source_kind", "export_scope", "exported_at", "records"}
RECORD_FIELDS = {
    "document_id",
    "document_type",
    "title",
    "status",
    "originating_unit",
    "document_date",
    "received_at",
    "sent_at",
    "external_reference_label",
    "keywords",
    "summary",
}
REQUIRED_FIELDS = {"document_id", "document_type", "title", "status"}
SEARCH_FIELDS = {
    "document_id",
    "document_type",
    "title",
    "status",
    "originating_unit",
    "external_reference_label",
    "keywords",
    "summary",
}


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
                fail("input_too_large", "Snapshot exceeds the 10 MiB input limit.")
            raw = path.read_bytes()
        except OSError as exc:
            fail("input_read_failed", str(exc))
    if len(raw) > MAX_INPUT_BYTES:
        fail("input_too_large", "Snapshot exceeds the 10 MiB input limit.")
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
    for field in RECORD_FIELDS - {"keywords"}:
        value = record.get(field)
        if value is None and field not in REQUIRED_FIELDS:
            continue
        if not isinstance(value, str) or (field in REQUIRED_FIELDS and not value.strip()):
            fail("invalid_field_type", "records[%d].%s must be a string." % (index, field))
        limit = 1000 if field == "summary" else (300 if field == "title" else 500)
        if len(value) > limit:
            fail("field_too_long", "records[%d].%s is too long." % (index, field))
    keywords = record.get("keywords", [])
    if not isinstance(keywords, list) or len(keywords) > 30:
        fail("invalid_keywords", "records[%d].keywords must be an array of at most 30 strings." % index)
    if any(not isinstance(value, str) or not value.strip() or len(value) > 100 for value in keywords):
        fail("invalid_keywords", "records[%d].keywords contains an invalid value." % index)
    if record["document_type"] not in DOCUMENT_TYPES:
        fail("unsupported_document_type", "records[%d] has an unsupported document_type." % index)
    if record["status"] not in STATUSES:
        fail("unsupported_status", "records[%d] has an unsupported status." % index)
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
    if data.get("export_scope") != REQUIRED_EXPORT_SCOPE:
        fail("explicit_export_required", "export_scope must be %s." % REQUIRED_EXPORT_SCOPE)
    if "exported_at" in data and not isinstance(data["exported_at"], str):
        fail("invalid_exported_at", "exported_at must be a string when present.")
    records = data.get("records")
    if not isinstance(records, list):
        fail("invalid_records", "records must be an array.")
    if len(records) > MAX_RECORDS:
        fail("too_many_records", "Snapshot exceeds the 20,000-record limit.")
    validated = [validate_record(record, index) for index, record in enumerate(records)]
    ids = [record["document_id"] for record in validated]
    if len(ids) != len(set(ids)):
        fail("duplicate_document_id", "document_id values must be unique.")
    return validated


def matched_fields(record, needle):
    matches = []
    for field in sorted(SEARCH_FIELDS):
        value = record.get(field)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        if any(needle in item.casefold() for item in values):
            matches.append(field)
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help=".json path or '-' for stdin")
    parser.add_argument("--query", required=True)
    parser.add_argument("--document-type", choices=sorted(DOCUMENT_TYPES))
    parser.add_argument("--status", choices=sorted(STATUSES))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        query = args.query.strip()
        if not query or len(query) > 200:
            fail("invalid_query", "query must contain 1 to 200 characters.")
        if args.limit < 1 or args.limit > 500:
            fail("invalid_limit", "limit must be between 1 and 500.")
        raw, snapshot = read_input(args.input)
        records = validate_snapshot(snapshot)
        if args.document_type:
            records = [record for record in records if record["document_type"] == args.document_type]
        if args.status:
            records = [record for record in records if record["status"] == args.status]
        needle = query.casefold()
        matches = []
        for record in records:
            fields = matched_fields(record, needle)
            if fields:
                matches.append({"document": record, "matched_fields": fields})
        matches.sort(
            key=lambda match: (
                match["document"].get("document_date", ""),
                match["document"]["document_id"],
            ),
            reverse=True,
        )
        matches = matches[: args.limit]
        print(
            json.dumps(
                {
                    "schema_version": OUTPUT_SCHEMA,
                    "operation": "search-groupware-documents",
                    "ok": True,
                    "source_mode": "explicit_offline_user_supplied_export",
                    "live_data": False,
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                    "snapshot_exported_at": snapshot.get("exported_at"),
                    "query": query,
                    "filters": {
                        "document_type": args.document_type,
                        "status": args.status,
                        "limit": args.limit,
                    },
                    "match_count": len(matches),
                    "matches": matches,
                    "search_scope_exhaustive_only_for_supplied_export": True,
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
                    "operation": "search-groupware-documents",
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
