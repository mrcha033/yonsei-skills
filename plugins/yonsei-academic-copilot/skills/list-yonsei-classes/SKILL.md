---
name: list-yonsei-classes
description: Normalize a user-provided Yonsei Academic Information System JSON snapshot into a current-term class list with course identifiers, sections, instructors, credits, and structured meeting times. Use when the user has exported or manually captured their authorized class schedule and wants a deterministic list without querying the live academic system.
---

# List Yonsei Classes

Return one normalized class list from one supplied academic snapshot.

## Run

Pass a JSON object containing `captured_at`, `term`, and a `classes` array:

```bash
python3 "$SKILL_DIR/scripts/list_classes.py" --input academic-classes.json
```

Rows may use English keys or common Korean labels such as `학정번호`, `분반`, `교과목명`, `담당교수`, `학점`, and `강의시간`. For a complete schedule result, supply `meetings` as objects with `day`, `start`, `end`, and optional `location`. An unparsed schedule string is preserved but makes `complete` false.

Read `warnings` before reporting the result. State the snapshot timestamp and term. Never describe the output as current beyond that timestamp.

## Boundaries

- Process only user-provided JSON. Do not log in, fetch live data, or infer enrollment changes.
- Reject credential-shaped fields and non-finite numbers.
- Preserve only recognized class fields; do not echo student identifiers or unrelated profile data.
- Never submit, cancel, or modify registration.
