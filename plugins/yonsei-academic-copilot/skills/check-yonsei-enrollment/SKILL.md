---
name: check-yonsei-enrollment
description: Normalize the enrollment and academic-status fields in a user-provided Yonsei Academic Information System JSON snapshot, identify missing term-registration evidence, and flag explicit status contradictions. Use for checking a captured 재학, 휴학, 수료, 졸업, or 제적 status without querying the live system or inferring eligibility.
---

# Check Yonsei Enrollment

Return one status report from one supplied academic snapshot.

## Run

```bash
python3 "$SKILL_DIR/scripts/check_enrollment.py" --input enrollment.json
```

Provide `captured_at`, `term`, and an `enrollment` object. The object must include `status`; add `registered_for_term` for a complete current-term registration report. Optional whitelisted fields include program, college, major, year level, and expected graduation.

Report contradictions and unknowns exactly. A historical snapshot is evidence only for its capture time.

## Boundaries

- Process only supplied JSON and reject credential or session fields.
- Do not return student numbers, addresses, phone numbers, or other unrecognized profile fields.
- Do not infer eligibility for graduation, scholarships, registration, visas, services, or benefits.
- Never submit leave, return, graduation, enrollment, or personal-information changes.
