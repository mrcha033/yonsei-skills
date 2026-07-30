---
name: summarize-yonsei-attendance
description: Normalize a user-provided Yonsei electronic-attendance screenshot, pasted table, export, or JSON snapshot and summarize present, late, absent, early-leave, excused, and pending records overall and by course. Use for authorized attendance history without checking in or querying the live system.
---

# Summarize Yonsei Attendance

Return one attendance summary from the student's authorized live page or one
supplied snapshot.

## Preferred command path

Call `yonsei_student` with `intent: "attendance"`. Normalize attendance rows
from `primary_result` with the bundled summarizer. Use an attachment only when
the official page is unavailable. Never enter a code or perform check-in.

## Prepare the input

When the user attaches an attendance screen, PDF, spreadsheet, or pasted table,
transcribe the recognized course, date, session, and displayed-status fields to
a private temporary JSON file. Do not ask the user to create JSON. Ask about
unreadable rows rather than inferring them.

## Run

```bash
python3 "$SKILL_DIR/scripts/summarize_attendance.py" --input attendance.json
```

Provide `captured_at` and a `records` array. Each row needs a course code, course title, class date, and displayed status. English or Korean field labels and status values are accepted.

Report the snapshot timestamp, computed date range, totals, and per-course breakdown. Unknown statuses and duplicate course/date/session records fail closed.

## Boundaries

- Read only the student's authenticated official attendance page or process
  user-supplied attachments, pasted data, or JSON.
- Reject credential or session fields and preserve only recognized attendance fields.
- Never enter an attendance code, attest presence, use Bluetooth or location data, spoof a device, or perform a check-in.
- Do not submit or apply an attendance correction.
