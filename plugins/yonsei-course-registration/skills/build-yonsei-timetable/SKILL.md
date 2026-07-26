---
name: build-yonsei-timetable
description: Construct deterministic conflict-free Yonsei timetable candidates from normalized course sections and explicit requirement groups. Use when choosing one section per desired course, respecting credit limits, blocked times, campus transfers, days off, and preferred compact schedules without performing registration.
---

# Build Yonsei Timetable

Return ranked, conflict-free timetable candidates from explicit alternatives.

## Run

```bash
python3 "$SKILL_DIR/scripts/build_timetable.py" --input choices.json
```

Supply normalized `courses` plus:

```json
{
  "requirements": [
    {"id": "writing", "course_ids": ["YCA1001-01", "YCA1001-02"], "required": true}
  ],
  "fixed_course_ids": [],
  "constraints": {
    "min_credits": 3,
    "max_credits": 18,
    "days_off": ["fri"],
    "travel_minutes": {"sinchon->international": 90}
  },
  "preferences": {
    "course_weights": {"YCA1001-02": 5}
  },
  "max_solutions": 10
}
```

Define one requirement per course or elective choice and list acceptable sections. The result ranks feasible schedules by campus changes, active days, gaps, preference weights, and credits in that order.

If `feasible` is false, report rejection reasons rather than relaxing constraints silently.

## Boundaries

- Require complete clock times and credits for every candidate considered.
- Treat a cross-campus transition without an explicit travel duration as infeasible.
- Use only supplied course snapshots; do not claim live seat availability.
- Never submit, cancel, waitlist, poll, or modify a registration.
