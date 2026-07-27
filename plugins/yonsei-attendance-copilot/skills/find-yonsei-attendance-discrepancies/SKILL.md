---
name: find-yonsei-attendance-discrepancies
description: Compare displayed and user-expected statuses in a supplied Yonsei attendance JSON snapshot, identify records explicitly disputed by the user, and report which items have enough reason and evidence to draft a correction. Use for reviewing possible attendance errors without inferring presence or changing official records.
---

# Find Yonsei Attendance Discrepancies

Return one discrepancy report from a supplied review snapshot.

## Run

```bash
python3 "$SKILL_DIR/scripts/find_discrepancies.py" --input attendance-review.json
```

Each record needs course, date, and `recorded_status`. Supply `expected_status` when known, or set `user_disputed: true`. Set `reviewed: true` for a record the user checked and accepts. A discrepancy is ready for a draft only when it has a different expected status, a reason, and at least one evidence description.

`no_discrepancies_found` is true only when every row is explicitly reviewed. Unreviewed rows remain `unknowns`.

## Boundaries

- Never infer presence from timetable, location, Bluetooth, device, or network data.
- Process only supplied JSON and reject credential, session, check-in, beacon, or location fields.
- Do not accuse a person or system of error; report a user-review candidate.
- Never submit a correction or alter an attendance record.
