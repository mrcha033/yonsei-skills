---
name: track-yonsei-academic-applications
description: Track active Yonsei Underwood academic applications, eligibility, deadlines, submitted state, missing documents, and the next student action. Use when a student asks what academic applications are open, what they already submitted, or what deadline is next.
---

# Track Yonsei Academic Applications

Turn Underwood's many application menus into one deadline radar.

## Preferred command path

Call `yonsei_student` with `intent: "applications"` and put the student-facing
category and application name in `request`. Use its `primary_result` as the
live radar input. Use screenshots only as a fallback.

## Workflow

1. Follow `$connect-yonsei-session` and reuse the authenticated managed browser
   profile. Open Portal, then Underwood through the official SSO link.
2. Read visible application menus and current rows for leave or return, major
   changes, multiple majors or minors, graduation, credit recognition, exams,
   exchange-related academic processing, and other student-accessible academic
   applications.
3. Record application name, category, opening and closing time, eligibility,
   official state, missing items, and the last observed time. Do not infer
   eligibility from a menu merely being visible.
4. Put those rows in the input described by `references/application-input.md`
   and run:

   ```bash
   python3 "$SKILL_DIR/scripts/build_application_radar.py" --input "<temporary-json>"
   ```

5. Show **지금 신청**, **곧 마감**, **진행 중**, and **확인 필요**, with one
   next action for each item.
6. When the student asks to submit, open the exact official application, fill
   only supplied facts, show the final summary, and ask for confirmation
   immediately before submission. Click once and verify the official state.

## Boundaries

- Never invent an eligibility rule or missing document.
- Never submit, withdraw, upload, or pay during a read-only tracking request.
- After session expiry, resume the last read-only step. Do not repeat an
  uncertain submission.
