---
name: yonsei-groupware
description: Open and inspect authorized Yonsei groupware content while requiring explicit confirmation before sending, sharing, approving, rejecting, or otherwise changing external state. Use for authorized groupware mail, messages, documents, forms, approvals, collaboration workflows, or ysgw.yonsei.ac.kr access.
---

# Yonsei Groupware

Use the direct official endpoint and default to reading or drafting.

## Workflow

1. Validate the packaged entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show groupware --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe groupware --json
   ```

2. Open it in an authenticated browser and let the user complete SSO. Never request credentials in chat.
3. Inspect only the requested mailbox, thread, document, form, or approval item. Do not reveal unrelated recipients, attachments, or confidential content.
4. Draft without sending by default. Before an external action, show recipients, subject or document title, attachment names, visible body or decision, and the exact action.
5. Require explicit confirmation immediately before send, forward, share, delete, submit, approve, reject, or recall. Verify the official resulting state.

Stop on recipient ambiguity, unexpected hosts, authorization mismatch, or an unreviewed attachment. Diagnose authenticated network failure before considering another network path; do not launch a VPN client.
