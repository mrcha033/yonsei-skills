---
name: plan-yonsei-mileage-strategy
description: Allocate a student's Yonsei course-registration mileage using supplied current capacity, applicant counts, past mileage cutoffs, tie-break context, graduation importance, and alternatives. Use when a student asks how much mileage to put on each course or wants a risk-aware registration strategy.
---

# Plan Yonsei Mileage Strategy

Calculate a recommendation from the student's actual registration screen and
past results. Do not present historical cutoffs as guarantees.

## Workflow

1. Accept screenshots, spreadsheets, pasted tables, or JSON containing desired
   courses, capacity, current or past applicants, past cutoff mileage when
   available, mileage cap, required-course importance, and alternatives.
2. Ask for the total mileage budget only when it is not visible in the supplied
   material. Do not hardcode a policy-year budget.
3. Convert the recognized values into the input described in
   `references/strategy-input.md`.
4. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/plan_mileage_strategy.py" --input "<temporary-json>"
   ```

5. Show the recommended allocation, risk band, supplied historical evidence,
   and a fallback course for every high-risk choice.
6. Recalculate when current applicants, capacity, or available mileage changes.

## Boundaries

- Never submit course registration or repeatedly poll the registration server.
- Treat missing or stale history as uncertainty, not zero competition.
- Explain that same-mileage tie breakers and major or year quotas can change
  outcomes even above a prior cutoff.
- Keep one or more alternatives for required courses when possible.
