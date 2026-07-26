---
name: yonsei-yri
description: Open and inspect the user's authorized Yonsei Researcher Information records, prepare field-level changes, and require explicit confirmation before every write. Use for YRI publications, books, grants, patents, researcher profiles, KRI linkage, achievement status, or yri.yonsei.ac.kr access.
---

# Yonsei YRI

Use the direct official endpoint. Do not depend on a portal-launcher plugin.

## Workflow

1. Validate the packaged entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show yri --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe yri --json
   ```

2. Open it in an authenticated browser. Let the user complete SSO; never request a password or OTP in chat.
3. Limit inspection to the requested achievement type and date range. Redact researcher identifiers and unrelated coauthor data from chat output.
4. For a proposed change, show a field-level before/after diff, attachments, downstream KRI or evaluation implications when displayed, and whether the action is draft, save, submit, confirm, or delete.
5. Require explicit confirmation immediately before every write. Verify the resulting record and status after submission.

Fail closed on an unexpected host, token-bearing copied URL, or authorization mismatch. Direct landing-page access is not proof that all authenticated features work without an internal network; diagnose the actual failure and do not launch a VPN client.
