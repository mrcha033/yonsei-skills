---
name: connect-yonsei-session
description: Connect once to the official Yonsei Portal in the student's persistent browser profile, reuse that authenticated session across Yonsei services, and resume after expiry without collecting credentials. Use when a student says 로그인, 포털 연결, 로그인 유지, 세션 만료, or asks to use an authenticated Yonsei service such as academic information, LearnUs, attendance, shuttle, space, library, counseling, student ID, or certificates.
---

# Connect Yonsei Session

Use the student's persistent Chrome profile when available. Keep the official
browser session as the shared login layer for later Yonsei tasks.

## Workflow

1. Reuse an already open official Yonsei tab when one exists. Otherwise open:

   `https://portal.yonsei.ac.kr/ui/index.html`

2. Check the visible page only. Do not inspect cookies, browser storage, saved
   passwords, network credentials, or profile files.
   When an HTML snapshot was supplied instead of a live browser, classify it
   without extracting credentials:

   ```bash
   python3 "$SKILL_DIR/scripts/classify_login_page.py" \
     --html "<snapshot>" \
     --success-marker "<visible authorized service label>"
   ```

3. If the requested service opens without an ID, password, MFA, or portal-login
   screen, continue without interrupting the student.
4. If authentication is required, leave that exact official tab open and ask
   the student once to finish login there. Never ask for a password or OTP in
   chat and never move those values into a terminal command.
5. After the student finishes, resume in the same browser profile and open the
   requested service again. Treat visible service content, not a portal HTTP
   response or a stored-cookie claim, as proof that login worked.
6. Keep using the same browser profile for academic information, LearnUs,
   attendance, shuttle, space, library, counseling, student ID, and
   certificates. Do not start a separate headless browser for each service.
7. If a downstream service has a separate institutional login, group the
   remaining login screens together, let the student complete each official
   screen once, then continue the original task.
8. On expiry, return to the official login screen in the same profile and
   resume from the last read-only step. Never repeat an uncertain reservation,
   application, issuance, or payment action after reauthentication.

Read `references/browser-session.md` when deciding whether a page is connected,
expired, or service-specific.

## Result

Report only:

- connected service or the exact official login screen awaiting the student
- whether the browser profile can be reused for the current task
- any service that still requires separate authentication
- the original task that will resume next

Do not expose identifiers, credentials, cookies, or authentication parameters.
