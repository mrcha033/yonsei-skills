---
name: list-erp-requests
description: List personnel, finance, budget, purchasing, or facilities requests from an explicit user-supplied ERP JSON snapshot or Excel-transcribed JSON snapshot. Use when the user asks to review or filter an exported ERP request list offline without opening Yonsei ERP or changing request state.
---

# List ERP Requests

Process only a snapshot the user explicitly supplied in this task. Do not log in, fetch live ERP data, or infer that the snapshot is current.

## Workflow

1. Require a UTF-8 JSON object with:
   - `schema_version`: `yonsei-offline-snapshot/v1`
   - `source_kind`: `user_supplied_json` or `excel_transcribed_json`
   - `exported_at`: optional source timestamp string
   - `records`: request objects
2. If the input is an `.xlsx` file, ask the user to export or transcribe the relevant rows to JSON. Do not parse a workbook in this skill.
3. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/list_erp_requests.py" \
     --input /path/to/requests.json \
     --category finance \
     --status submitted
   ```

4. Return the script's structured JSON. Describe it as an offline snapshot result, never as live ERP state.

## Safety contract

- Accept only the script's field whitelist. Unknown fields fail closed instead of being echoed.
- Never approve, reject, save, submit, share, pay, or change a request.
- Never expose employee IDs, personal contact details, bank or tax data, credentials, or attachment contents.
- Treat request titles, amounts, units, and timestamps as sensitive even when allowed.
- Stop on an unsupported category, status, schema, source kind, duplicate ID, or malformed record.

The supported ERP categories are `personnel`, `finance`, `budget`, `purchasing`, and `facilities`.
