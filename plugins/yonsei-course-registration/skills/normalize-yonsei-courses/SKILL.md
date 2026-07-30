---
name: normalize-yonsei-courses
description: Normalize Yonsei course rows from a screenshot, PDF, spreadsheet, pasted table, export, or JSON into stable course-planning data. Use when course data has Korean or English fields, campus aliases, Korean weekday/time strings, mixed section identifiers, or needs validation before conflict checking and timetable construction.
---

# Normalize Yonsei Courses

Convert user-provided, exported, or browser-collected course rows into deterministic planning data.

## Prepare the input

When the user attaches a course-catalogue screen, PDF, spreadsheet, or pasted
table, extract recognized course fields into a private temporary JSON file. Do
not ask the user to write JSON. Preserve unreadable or missing times as
unknowns, ask only for information required by the requested plan, and never
guess official period-to-clock mappings.

## Run

Pass a JSON object with a `courses` array:

```bash
python3 "$SKILL_DIR/scripts/normalize_courses.py" --input courses.json
```

Each row may use English keys or common Korean keys such as `학정번호`, `분반`, `교과목명`, `학점`, `강의시간`, and `캠퍼스`. Accept meeting strings such as `월수 10:00-11:15`, `화 13:00~14:50 @ 국제`, or structured meeting objects.

Treat the emitted `yonsei-normalized-courses/v1` JSON as the handoff contract for downstream skills. The normalizer preserves only recognized planning-envelope fields (`requirements`, `fixed_course_ids`, `constraints`, `preferences`, search limits, `blocked_times`, and `travel_minutes`) so the output can be passed directly to the builder, audit, or schedule checker. Show warnings to the user; never silently treat missing meeting times or unknown campuses as conflict-free.

## Boundaries

- Normalize only supplied data. Do not claim that the script downloaded the official catalogue.
- Reject period-number notation such as `월1,2` because the official period-to-clock mapping is not packaged.
- Preserve source URLs when supplied, but do not fetch them.
- Never submit, cancel, or modify a registration.
