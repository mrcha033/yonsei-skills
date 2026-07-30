---
name: plan-yonsei-mileage-strategy
description: Read a student's authorized Underwood mileage history and combine it with current capacity, applicant counts, catalogue data, tie-break context, graduation importance, and alternatives to plan a risk-aware Yonsei course-registration strategy. Use when a student asks how much mileage to put on each course or wants a strategic timetable.
---

# Plan Yonsei Mileage Strategy

Calculate a recommendation from the student's actual registration screen and
past results. Do not present historical cutoffs as guarantees.

## Preferred command path

Call `yonsei_student` with `intent: "courses"`. Its `primary_result` contains
the current official Underwood handbook rows, personal mileage history, and any
available current registration rows. Pass the student's year, semester, campus,
college or category, department, and course keyword in `request` when known.
Feed those values into the bundled calculator; ask only for constraints or
desired courses that are not visible.

## Workflow

1. Follow `$connect-yonsei-session`, open `수업 → 수강편람` in Underwood, apply
   the student's search conditions, and run the official `조회`. This handbook
   is the primary source and does not require the separate registration window
   to be open. Never ask the student to capture it while the authorized page is
   available.
2. Open the student's Underwood mileage-history list. Read term, course and
   section, mileage, and success state. Open a history detail only when useful
   and read applied-course count, first-time status, major status, year, prior
   and total earned-credit ratios, and graduation context.
3. Read capacity, applicants, mileage cap, graduation importance, and
   alternatives from the official screens that are currently available. If the
   registration-only screen is closed for the period, keep the handbook result,
   mark current demand as unavailable, and continue with explicit uncertainty.
   Accept screenshots, spreadsheets, pasted tables, or JSON only after the
   direct official path fails or when the student intentionally supplies one.
4. Ask for the total mileage budget only when it is not visible in the supplied
   material. Do not hardcode a policy-year budget.
5. Convert the recognized values into the input described in
   `references/strategy-input.md`.
6. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/plan_mileage_strategy.py" --input "<temporary-json>"
   ```

7. Show the recommended allocation, risk band, personal history signal,
   tie-break context, current demand, uncertainty, and a fallback course for
   every high-risk choice.
8. Recalculate when current applicants, capacity, catalogue availability, or
   available mileage changes.

## Boundaries

- Never submit course registration or repeatedly poll the registration server.
- Do not treat a closed registration entry as evidence that `수강편람` is
  unavailable; diagnose and report the two states separately.
- Treat missing or stale history as uncertainty, not zero competition.
- Explain that same-mileage tie breakers and major or year quotas can change
  outcomes even above a prior cutoff.
- Keep one or more alternatives for required courses when possible.
