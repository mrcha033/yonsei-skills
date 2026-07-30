---
name: plan-yonsei-mileage-strategy
description: Read a student's authorized Underwood mileage history and combine it with current capacity, applicant counts, catalogue data, tie-break context, graduation importance, and alternatives to plan a risk-aware Yonsei course-registration strategy. Use when a student asks how much mileage to put on each course or wants a strategic timetable.
---

# Plan Yonsei Mileage Strategy

Calculate a recommendation from the student's actual registration screen and
past results. Do not present historical cutoffs as guarantees.

## Preferred command path

Call `yonsei_mileage_history` first. It returns both personal mileage history
and the current registration rows. Feed those values into the bundled
calculator; ask the student only for constraints or desired courses that are
not visible.

## Workflow

1. Follow `$connect-yonsei-session` and open the student's authorized Underwood
   mileage-history list. Read term, course and section, mileage, and success
   state. Open a history detail only when useful and read applied-course count,
   first-time status, major status, year, prior and total earned-credit ratios,
   and graduation context. Do not ask for screenshots when the live authorized
   page is available.
2. Read the current official catalogue and registration screen for desired
   courses, capacity, applicants, mileage cap, graduation importance, and
   alternatives. Accept screenshots, spreadsheets, pasted tables, or JSON only
   as a fallback.
3. Ask for the total mileage budget only when it is not visible in the supplied
   material. Do not hardcode a policy-year budget.
4. Convert the recognized values into the input described in
   `references/strategy-input.md`.
5. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/plan_mileage_strategy.py" --input "<temporary-json>"
   ```

6. Show the recommended allocation, risk band, personal history signal,
   tie-break context, current demand, uncertainty, and a fallback course for
   every high-risk choice.
7. Recalculate when current applicants, capacity, catalogue availability, or
   available mileage changes.

## Boundaries

- Never submit course registration or repeatedly poll the registration server.
- Treat missing or stale history as uncertainty, not zero competition.
- Explain that same-mileage tie breakers and major or year quotas can change
  outcomes even above a prior cutoff.
- Keep one or more alternatives for required courses when possible.
