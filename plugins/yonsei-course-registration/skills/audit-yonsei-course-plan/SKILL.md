---
name: audit-yonsei-course-plan
description: Audit a normalized Yonsei course selection against the user's explicit credit, required-course, campus, day-off, time-window, and daily-load constraints. Use when checking whether one proposed course plan satisfies stated requirements without performing conflict search or registration.
---

# Audit Yonsei Course Plan

Return one auditable constraint report for one selected course set.

## Run

```bash
python3 "$SKILL_DIR/scripts/audit_course_plan.py" --input plan.json
```

Accept normalized `courses` and optional `constraints`:

- `min_credits`, `max_credits`
- `required_course_codes`
- `allowed_campuses`
- `days_off`
- `earliest_start`, `latest_end`
- `max_daily_minutes`

Report every unmet constraint and missing field. Do not present `constraints_met: true` when completeness is false.

## Boundaries

- Evaluate only explicit user constraints; do not infer graduation or major requirements.
- Do not infer credits or meeting times from course titles.
- Use `$check-yonsei-schedule` for pairwise overlaps, blocked times, and campus-transfer feasibility.
- Never submit, cancel, or modify a registration.
