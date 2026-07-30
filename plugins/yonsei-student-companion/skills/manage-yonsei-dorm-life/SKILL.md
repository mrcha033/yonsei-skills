---
name: manage-yonsei-dorm-life
description: Manage Yonsei dorm applications, payment and room status, roommate requests, overnight stays, repairs, facility bookings, move-in, and move-out through the official authenticated browser. Use when a student asks for any Sinchon, International Campus, or Mirae dorm task.
---

# Manage Yonsei Dorm Life

Handle a dorm request from natural language while preserving the student's
authenticated browser session on Windows, macOS, or Linux.

## Preferred command path

Call `yonsei_student` with `intent: "dorm"` and put campus, dorm, date, reason,
facility, roommate, or issue in `request`. Status is read-only. For an
application, booking, cancellation, or report, review `primary_result`, then
repeat with the selected ID and `confirmed: true`.

## Workflow

1. Follow `$connect-yonsei-session`, identify the student's campus and dorm,
   and open the visible official dorm or Underwood menu in the same persistent
   browser profile.
2. Translate the request into one action: application, payment/status check,
   roommate, overnight stay, repair, facility booking, move-in, or move-out.
3. Read the current eligibility, application window, active status, facility
   availability, and required fields from the official page. Do not reuse an
   old semester's rules.
4. Prepare the request:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_dorm_action.py" --input "<temporary-json>"
   ```

5. Ask only for fields still missing. For a status check, report the visible
   result without changing anything.
6. For an application, booking, report, or cancellation, fill the official
   form, show the exact dorm, date/time, facility or issue, and reason, then ask
   for confirmation immediately before the final button.
7. Click once and verify the official application number or updated state.

## Boundaries

- Never guess a room, resident number, eligibility, fee, or approval.
- Never retry an uncertain write after login expiry or a timeout.
- If browser control is unavailable, leave the official page open and provide
  the reviewed request so the student can press the final button.
