---
name: learnus-course-copilot
description: Inspect authorized Yonsei LearnUs courses through a password-prompted headless session or an existing authenticated browser, collect course materials, identify assignments and deadlines, and produce study-ready structured output. Use for LearnUs pages, lecture resources, VOD links, assignment tracking, downloads, GUI-less hosts, or expired SSO sessions.
---

# LearnUs Course Copilot

Prefer the local headless session service on GUI-less hosts. It prompts for the password in the user's terminal, keeps credentials and cookies in memory only, and automatically reauthenticates after session expiry. Never ask for a Yonsei password in chat or pass one through a command-line argument, environment variable, or file.

## Headless workflow

1. Check the local service:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" status
   ```

2. If it is not running, ask the user to run this command in their own interactive terminal. The script accepts the password only through a hidden TTY prompt and detaches after successful authentication:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" start \
     --username "<Yonsei login ID>"
   ```

3. Fetch only the exact authorized page needed. Use a fresh temporary file and do not print raw HTML:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" fetch \
     --url "https://ys.learnus.org/course/view.php?id=..." \
     --output "<secure temporary path>"
   ```

4. Analyze the saved page:

   ```bash
   python3 "$SKILL_DIR/scripts/analyze_learnus_snapshot.py" \
     --html "<secure temporary path>" \
     --base-url "https://ys.learnus.org/course/view.php?id=..."
   ```

5. Review the structured result, then fetch only resources the user explicitly requested. The service retries authentication once when LearnUs returns a login page.
6. Return the course title, materials, assignments/deadlines, VOD entries, inaccessible items, and the exact redacted pages inspected.

Stop and forget the in-memory password when the work is finished or when the user requests it:

```bash
python3 "$SKILL_DIR/scripts/learnus_headless.py" stop
```

## Browser fallback

Use a browser-control skill when Yonsei SSO requests CAPTCHA, MFA, or another interactive verification, or when the SSO contract has changed. Open the exact LearnUs URL in the existing browser session, read a bounded DOM snapshot, and ask the user to sign in there if a login boundary appears. Never copy browser cookies into the headless service.

## Boundaries

- Treat public web search as discovery only; it cannot authenticate LearnUs.
- Accept passwords only through `learnus_headless.py start` and its hidden TTY prompt. The CLI intentionally has no password option.
- The headless service permits HTTPS requests only to `ys.learnus.org` through a Unix socket restricted to the current user.
- Fail closed on CAPTCHA, MFA, an unexpected SSO endpoint, an off-origin redirect, or a second login response after automatic reauthentication.
- Do not infer completion, attendance, or a deadline from a filename alone.
- Do not redistribute course materials or download an entire course unless the user explicitly asks.
- Keep signed URLs and tokens out of logs and delivered artifacts. Report a redacted URL or page locator when needed.
- Mark the result `login_required` when the snapshot is not authenticated.
- Follow `references/snapshot-contract.md` when adding parser support for a new LearnUs page shape.
- Follow `references/headless-auth.md` for the service lifecycle and security contract.

Run `python3 "$SKILL_DIR/scripts/self_test.py"` after changing the parser or headless client.
