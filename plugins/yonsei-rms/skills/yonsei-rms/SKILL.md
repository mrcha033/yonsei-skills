---
name: yonsei-rms
description: Open and inspect authorized Yonsei Research Management System records, prepare field-level changes, and require explicit confirmation before every write. Use for RMS projects, budgets, participants, research expenses, attachments, submissions, approvals, or rms2.yonsei.ac.kr access.
---

# Yonsei RMS

Use the direct official endpoint and default to read-only inspection.

## Workflow

1. Validate the packaged entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show rms --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe rms --json
   ```

2. Open it in an authenticated browser and let the user complete SSO. Never request credentials in chat.
3. Inspect only the requested project, budget period, participant, expense, or attachment. Do not expose bank, tax, resident-registration, payment, or unrelated personnel information.
4. Before changing anything, show the project identifier, exact field-level diff, amount and unit, attachment set, workflow transition, and downstream approver.
5. Require explicit confirmation immediately before save, submit, cancel, approve, reject, participant change, budget change, or attachment deletion.
6. Verify the official resulting state and reference number.

Stop on an unexpected host, authorization mismatch, or ambiguous money amount. Diagnose authenticated network failure before considering another network path; do not launch a VPN client.
