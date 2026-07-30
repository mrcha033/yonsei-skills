---
name: find-yonsei-attendance-discrepancies
description: Compare displayed and user-expected statuses from a supplied Yonsei attendance screenshot, pasted table, export, or JSON, identify records explicitly disputed by the user, and report which items have enough reason and evidence to draft a correction. Use without inferring presence or changing official records.
---

# Find Yonsei Attendance Discrepancies

Return one discrepancy report from a supplied review snapshot.

## Prepare the input

If the user supplies an attendance screen or table, extract the displayed
records into a private temporary JSON file, then ask the user which entries they
dispute and what evidence they want considered. Do not make the user write JSON
or infer an expected status from location or timetable data.

## Run

```bash
python3 "$SKILL_DIR/scripts/find_discrepancies.py" --input attendance-review.json
```

Each record needs course, date, and `recorded_status`. Supply `expected_status` when known, or set `user_disputed: true`. Set `reviewed: true` for a record the user checked and accepts. A discrepancy is ready for a draft only when it has a different expected status, a reason, and at least one evidence description.

`no_discrepancies_found` is true only when every row is explicitly reviewed. Unreviewed rows remain `unknowns`.

## Boundaries

- Never infer presence from timetable, location, Bluetooth, device, or network data.
- Process only user-supplied attachments, pasted data, or JSON and reject credential, session, check-in, beacon, or location fields.
- Do not accuse a person or system of error; report a user-review candidate.
- Never submit a correction or alter an attendance record.
