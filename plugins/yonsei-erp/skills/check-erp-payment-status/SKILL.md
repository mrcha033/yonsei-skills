---
name: check-erp-payment-status
description: Check exactly one payment record by payment ID or request ID in an explicit user-supplied ERP JSON snapshot or Excel-transcribed JSON snapshot. Use for offline finance, budget, purchasing, personnel reimbursement, or facilities payment-status questions without initiating, retrying, approving, sharing, or submitting a payment.
---

# Check ERP Payment Status

Read one unambiguous payment from a supplied snapshot. Do not connect to ERP or describe the result as current.

## Workflow

1. Require a `yonsei-offline-snapshot/v1` JSON snapshot with whitelisted payment metadata.
2. Require exactly one selector:

   ```bash
   python3 "$SKILL_DIR/scripts/check_erp_payment_status.py" \
     --input /path/to/payments.json \
     --payment-id PAY-001
   ```

   Alternatively use `--request-id`.

3. Return the structured result. If zero or multiple records match, preserve the fail-closed error instead of guessing.

## Safety contract

- Reject account numbers, card data, tax IDs, employee IDs, personal contacts, credentials, free-form bank responses, and attachment content.
- Never initiate, approve, retry, cancel, schedule, share, or mark a payment paid.
- Treat `paid` as a value in the supplied export, not bank settlement proof.
- Stop on duplicate payment IDs, an ambiguous request ID, unknown schema, unsupported status, or malformed amount.
