---
name: yonsei-academic-copilot
description: Open and inspect the user's authorized Yonsei Academic Information System records through the official SSO entry, with a read-only first release. Use for class schedules, grades, enrollment status, academic history, student information, or diagnosing access to underwood1.yonsei.ac.kr.
---

# Yonsei Academic Copilot

Default to read-only inspection. Do not submit, cancel, or change an academic request in version 0.1.

## Workflow

1. Resolve and probe the stable entry instead of reusing a copied `requestTimeStr` URL:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show academic --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe academic --json
   ```

2. Open the reported entry in an authenticated browser. Ask the user to complete SSO there if needed; never request a password or OTP in chat.
3. Navigate only to the record type the user requested. Collect the minimum fields needed and avoid exposing student numbers, addresses, phone numbers, or unrelated grades.
4. Report the page and timestamp inspected, the requested records, and any access or completeness limitation.
5. If an authenticated function fails, separate login failure, authorization denial, application error, and network failure. Direct reachability alone does not establish that every function works off campus. Do not launch a VPN client from this skill.

Do not reuse the LearnUs headless daemon: it is intentionally restricted to the LearnUs origin.
