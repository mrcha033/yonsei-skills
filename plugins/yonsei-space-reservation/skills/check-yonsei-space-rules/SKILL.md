---
name: check-yonsei-space-rules
description: Read the current official Yonsei space rules first and check a booking proposal against public lead-time, duration, booking-count, ten-minute interval, applicant eligibility, and restricted-period rules; use a screenshot, pasted form, export, or JSON only when the live rule page is unavailable or intentionally supplied. Use before preparing a request; return unknown when required facts are absent.
---

# Check Yonsei Space Rules

Return one evidence-linked eligibility report.

## Prepare the input

Collect the proposal in ordinary language or from an attached form and convert
only the required fields to a private temporary JSON file. Do not ask the user
to write JSON. Ask about restricted periods or prior booking counts when they
are not visible instead of inferring them.

## Run

```bash
python3 "$SKILL_DIR/scripts/check_space_rules.py" --input proposal.json
```

Required input:

```json
{
  "requested_on": "2026-07-27T13:30:00+09:00",
  "date": "2026-07-30",
  "start": "14:00",
  "end": "16:00",
  "applicant_type": "student",
  "bookings_in_same_7_day_window": 0,
  "restricted_period": false
}
```

Applicant types are `student`, `graduate_student`, `staff`, `alumni`,
`registered_organization`, and `general_public`.

`eligible` is `false` for a definite violation, `null` when unresolved facts
prevent a verdict, and `true` only when every implemented rule is checkable.

## Boundaries

- Read `references/official-rules.md` when explaining a verdict.
- Do not infer exam, opening-week, or special-event periods.
- Approval and payment may still be required after a rule pass.
- Never submit a request or claim that staff approved it.
