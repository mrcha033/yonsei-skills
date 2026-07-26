---
name: manage-learnus-session
description: Start, inspect, refresh, and stop a GUI-less Yonsei LearnUs session using a hidden terminal password prompt and memory-only credentials. Use when LearnUs authentication is required, an existing headless session expired, or the user asks to forget the retained password.
---

# Manage LearnUs Session

Keep authentication separate from course-data tasks. Never ask for a Yonsei password in chat or pass one in an argument, environment variable, file, log, or artifact.

## Workflow

1. Inspect the local service:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" status
   ```

2. If it is not running, ask the user to run this command in their interactive terminal:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" start --username "<Yonsei ID>"
   ```

   The command must read the password through its hidden TTY prompt. Do not run `start` through a non-interactive wrapper.

3. Report whether the local service is running, whether a session was established, its `last-known-authenticated` state, and how many automatic reauthentications occurred. `status` deliberately performs no remote request, so never describe it as proof that the current cookie is still valid.
4. To fetch an exact authorized LearnUs page for a sibling outcome skill:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" fetch \
     --url "https://ys.learnus.org/..." \
     --output "<fresh secure temporary path>"
   ```

5. Stop the service when requested or when retained credentials are no longer needed:

   ```bash
   python3 "$SKILL_DIR/scripts/learnus_headless.py" stop
   ```

## Boundaries

- Follow `references/headless-auth.md`.
- Accept only HTTPS on port 443 for the fixed LearnUs and Yonsei SSO hosts.
- Fetch only the read-only dashboard (`/my/`) and one numeric course view (`/course/view.php?id=...`); reject logout and action paths.
- Do not follow an external redirect with cookies or credential context.
- Fail closed on CAPTCHA, MFA, access-denied, maintenance, unexpected SSO pages, or repeated login responses.
- Retain the password only inside the local process for automatic reauthentication.
- Use browser authentication only when interactive verification is required; never copy browser cookies into this service.

Run `python3 "$SKILL_DIR/scripts/learnus_headless.py" self-test` after changes.
