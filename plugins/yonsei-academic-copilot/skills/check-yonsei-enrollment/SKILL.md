---
name: check-yonsei-enrollment
description: Normalize enrollment and academic-status fields from a user-provided Yonsei Academic Information System screenshot, pasted table, export, or JSON, identify missing term-registration evidence, and flag explicit contradictions. Use for a captured 재학, 휴학, 수료, 졸업, or 제적 status without querying the live system or inferring eligibility.
---

# Check Yonsei Enrollment

Return one status report from one supplied academic snapshot.

## Prepare the input

When the user supplies a screen capture, PDF, spreadsheet, or pasted table,
extract only the status fields needed for this check into a private temporary
JSON file. Do not ask the user to write JSON. Redact or omit student numbers and
contact details before running the script.

## Run

```bash
python3 "$SKILL_DIR/scripts/check_enrollment.py" --input enrollment.json
```

Provide `captured_at`, `term`, and an `enrollment` object. The object must include `status`; add `registered_for_term` for a complete current-term registration report. Optional whitelisted fields include program, college, major, year level, and expected graduation.

Report contradictions and unknowns exactly. A historical snapshot is evidence only for its capture time.

## Boundaries

- Process only user-supplied attachments, pasted data, or JSON and reject credential or session fields.
- Do not return student numbers, addresses, phone numbers, or other unrecognized profile fields.
- Do not infer eligibility for graduation, scholarships, registration, visas, services, or benefits.
- Never submit leave, return, graduation, enrollment, or personal-information changes.
