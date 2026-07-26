---
name: check-yonsei-schedule
description: Check normalized Yonsei courses for overlapping meetings, duplicate sections, blocked times, and insufficient campus-transfer time. Use when validating a proposed timetable or comparing selected sections before registration; reports unknown timing and travel assumptions instead of claiming a schedule is conflict-free.
---

# Check Yonsei Schedule

Check one proposed set of courses and return a single conflict report.

## Run

Use normalized output from `$normalize-yonsei-courses`:

```bash
python3 "$SKILL_DIR/scripts/check_schedule.py" --input plan.json
```

Optional input fields:

- `blocked_times`: meeting-shaped objects the student cannot attend.
- `travel_minutes`: an object such as `{"sinchon->international": 90}`. Reverse directions must be stated separately.

These fields may be top-level or nested under `constraints`, matching the direct output envelope from `$normalize-yonsei-courses`.

`conflict_free` is `true` only when the check is complete, `false` when a conflict exists, and `null` when unresolved data prevents a verdict. `no_detected_conflicts` remains a narrower observation. Missing meeting data or an unspecified cross-campus transfer produces an `unknown`, not a silent pass.

## Boundaries

- Check only the supplied snapshot; do not infer current seat availability.
- Do not invent travel durations.
- Never submit, cancel, or modify a registration.
