---
name: list-erp-approvals
description: List and filter ERP approval items from an explicit user-supplied JSON snapshot or Excel-transcribed JSON snapshot for personnel, finance, budget, purchasing, and facilities workflows. Use for offline review of approval queues or completed approval history without approving, rejecting, submitting, or opening live ERP.
---

# List ERP Approvals

Use only the snapshot explicitly supplied by the user. Treat every result as a historical offline view.

## Workflow

1. Require `yonsei-offline-snapshot/v1`, a supported `source_kind`, and an array named `records`.
2. Require the user to export or transcribe Excel rows to JSON before using this skill.
3. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/list_erp_approvals.py" \
     --input /path/to/approvals.json \
     --action-required-only
   ```

4. Return the structured result without adding records or claiming a live queue state.

## Safety contract

- Accept only whitelisted queue metadata; reject unknown fields.
- Never approve, reject, return, delegate, save, submit, share, or trigger a payment.
- Do not include employee identifiers, direct contact details, bank or tax data, credentials, comments, or attachment bodies.
- Stop on duplicate approval IDs, unknown schemas, malformed values, or unsupported categories and statuses.

`my_action_required` is snapshot metadata only. It is not permission to act.
