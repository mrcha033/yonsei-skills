---
name: manage-learnus-session
description: Connect to Yonsei LearnUs in the student's persistent browser profile, reuse the official portal login, and recover from session expiry without receiving credentials in chat. Use when LearnUs login is required, a browser session expired, or the student asks to stay signed in; use the optional terminal session only when the student explicitly requests background or GUI-less operation.
---

# Manage LearnUs Session

Default to the student's browser, not a terminal login.

## Browser-first workflow

1. Reuse the persistent browser profile already used for Yonsei. Open:

   `https://ys.learnus.org/my/`

2. If the authorized **My courses** dashboard is visible, continue without
   interrupting the student.
3. If **Portal Login**, **External Login**, an ID/password form, MFA, or a
   session-expired page appears, leave that exact official tab open and ask the
   student once to complete login there.
4. Resume in the same browser profile. Verify the visible **My courses**
   dashboard and account menu before treating the session as connected.
5. Reuse that tab or profile for course, deadline, and material reads. On
   expiry, return to the official login screen and resume the last read-only
   step.

Never inspect or copy cookies, browser storage, saved passwords, OTPs, or
session parameters.

## Optional terminal mode

Use the bundled memory-only service only when the student explicitly asks for
background or GUI-less operation:

```bash
python3 "$SKILL_DIR/scripts/learnus_headless.py" status
python3 "$SKILL_DIR/scripts/learnus_headless.py" start --username "<Yonsei ID>"
```

The student must run `start` in their own interactive terminal and enter the
password at its hidden prompt. Never run it through a non-interactive wrapper.
The password remains only in that process and is lost when it stops.

Stop it when requested:

```bash
python3 "$SKILL_DIR/scripts/learnus_headless.py" stop
```

## Boundaries

- Do not describe a saved browser profile as permanent authentication; school
  sessions expire.
- Do not enable or request a Moodle token that the student's account does not
  expose.
- Do not submit assignments, messages, grades, or course changes.
- Stop on CAPTCHA, unexpected identity-provider pages, or repeated login
  responses and leave the official page for the student.

Run `python3 "$SKILL_DIR/scripts/learnus_headless.py" self-test` after terminal
session code changes.
