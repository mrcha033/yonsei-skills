---
name: yonsei-erp
description: Open and inspect authorized Yonsei ERP administrative workflows with a read-only default and explicit confirmation before any write, approval, or submission. Use for authorized ERP personnel, payroll, purchasing, facilities, finance, administrative requests, or infra.yonsei.ac.kr ERP access.
---

# Yonsei ERP

Use the direct official SSO endpoint. Treat administrative, personnel, payroll, purchasing, and finance data as sensitive.

## Workflow

1. Validate the packaged entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show erp --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe erp --json
   ```

2. Open it in an authenticated browser and let the user complete SSO. Never request credentials in chat.
3. Confirm the user's intended module and authorized role before reading records. Collect only the minimum fields needed.
4. Default to summarizing the requested record or preparing a draft. Do not expose direct identifiers, contact details, bank data, tax data, payroll details, or unrelated employee information.
5. Before a write, show the exact record, field-level diff, monetary amount and unit when applicable, attachments, recipients or approvers, and workflow transition.
6. Require explicit confirmation immediately before save, submit, approve, reject, payment-related action, or external communication. Verify the official resulting status.

Fail closed on unexpected hosts, plain-HTTP credential submission, missing authorization, or ambiguous amounts. Do not launch a VPN client; first diagnose the authenticated failure.
