---
name: summarize-yonsei-today
description: Build a read-only daily Yonsei briefing from Portal plus accessible Underwood classes, scholarships, mileage, graduation and teaching progress, LearnUs, and attendance. Use when a student asks 오늘 뭐 해야 해, 오늘의 연세, 이번 주 학교 일정, 마감 한 번에, or wants a recurring campus dashboard.
---

# Summarize Yonsei Today

Make one compact student briefing instead of sending the student through
several portal menus.

## Preferred command path

Call `yonsei_student` with `intent: "today"` and `request.full: true`. If it
returns `login_required`, call `yonsei_bridge_connect`, let the student finish
the one visible official login, then repeat the same request. Report
`primary_result` first.

## Workflow

1. Use the student's current date, campus, and time zone. Ask for campus only if
   it changes the requested result and cannot be read from an already open
   schedule.
2. Follow `$connect-yonsei-session` once, then reuse that browser profile for
   every source. Do not request a separate login before each page.
3. Read Portal, Underwood classes/scholarships/mileage/graduation/teaching,
   LearnUs, and attendance. Skip a source when the student lacks access or the
   page requires a separate login they do not want to complete.
4. Read only what is needed for:

   - next class and campus move
   - deadlines due today or within seven days
   - absence, lateness, or disputed attendance needing review
   - Underwood class, scholarship, mileage, graduation, and
     teaching-credential items that are active or due soon

5. Never click attendance check-in, submit an assignment, reserve, apply, issue,
   or pay anything in this read-only briefing.
6. De-duplicate the same event when it appears in more than one service. Keep
   the official service name and the time last observed.
7. Put the collected items in a temporary JSON file and sort them:

   ```bash
   python3 "$SKILL_DIR/scripts/build_daily_briefing.py" \
     --input "<temporary-json>"
   ```

8. Present **지금**, **오늘**, **7일 안**, **진행 중**, and **확인 필요**. Omit empty
   sections and delete the temporary file.

## Result

Keep the first screen short:

- the next required action
- at most five dated items
- warnings that could cause a missed deadline, absence, cancellation, or
  overdue item
- unavailable services only when they materially affect the briefing

Offer a deeper view of one item without forcing the student back through login.
