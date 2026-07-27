---
name: list-groupware-approvals
description: List electronic approvals, official incoming or outgoing documents, external administrative-network documents, and e-SOP approval items from an explicit user-supplied groupware JSON snapshot or Excel-transcribed JSON snapshot. Use for offline queue review without opening groupware or approving, rejecting, returning, submitting, sharing, or sending anything.
---

# List Groupware Approvals

Process only the groupware snapshot the user supplied in this task. Do not infer live approval state.

## Workflow

1. Require:
   - `schema_version`: `yonsei-offline-snapshot/v1`
   - `source_kind`: `user_supplied_json` or `excel_transcribed_json`
   - optional `exported_at`
   - `records`: approval metadata
2. Require Excel content to be explicitly transcribed or exported to JSON before processing.
3. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/list_groupware_approvals.py" \
     --input /path/to/approvals.json \
     --action-required-only
   ```

4. Return the structured JSON and preserve its offline/live boundary.

## Safety contract

- Accept only whitelisted approval metadata; fail on unknown fields.
- Never approve, reject, return, delegate, submit, share, recall, send, fax, or message.
- Exclude recipient addresses, phone or fax numbers, personal contacts, credentials, comments, attachment bodies, and unrelated document content.
- Stop on duplicate IDs, unsupported workflow types or statuses, malformed values, or unknown snapshot metadata.

`my_action_required` reports the supplied snapshot only and grants no authority to act.
