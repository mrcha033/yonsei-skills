---
name: summarize-yonsei-grades
description: Summarize a user-provided Yonsei grade screenshot, pasted table, export, or JSON into attempted credits, earned credits, GPA credits, a conservative 4.3-scale calculation, and displayed-versus-calculated GPA checks. Use for an authorized term-grade snapshot without querying or changing the live system.
---

# Summarize Yonsei Grades

Return one term-grade summary from a supplied snapshot.

## Prepare the input

When the user supplies a screenshot, PDF, spreadsheet, or pasted table,
transcribe only course, credit, grade, term, capture time, and displayed GPA
fields into a private temporary JSON file. Do not ask the user to create JSON.
Ask about unreadable credits or grades instead of guessing.

## Run

```bash
python3 "$SKILL_DIR/scripts/summarize_grades.py" --input grades.json
```

Provide `captured_at`, `term`, and `grades`. Each grade row needs a course code, title, credits, and final grade. The script recognizes Yonsei-style letter grades, `P`/`NP`, `S`/`U`, `W`, and pending `I`. Pending results make the final GPA incomplete. If `displayed_gpa` is supplied, the script reports whether it agrees with the calculation.

Report `calculation_notes`, `complete`, and any GPA discrepancy. Keep calculated and displayed values distinct.

## Boundaries

- Process only the supplied attachment, pasted data, or snapshot; do not claim live or official transcript status.
- Reject unknown grades, credential-shaped fields, and non-finite credits.
- Do not infer repeated-course replacement, major GPA, honors, graduation eligibility, or institution-specific exceptions not present in the snapshot.
- Never submit an academic request or modify a grade.
