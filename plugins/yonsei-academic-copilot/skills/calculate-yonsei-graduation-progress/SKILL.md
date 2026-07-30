---
name: calculate-yonsei-graduation-progress
description: Calculate Yonsei graduation progress from a student-supplied transcript and official entry-year, college, and major requirements. Use when a student asks what graduation requirements are complete, what credits or required courses remain, or whether a planned course can fill a requirement.
---

# Calculate Yonsei Graduation Progress

Use the deterministic calculator instead of estimating requirements from memory.

## Workflow

1. Ask for the student's campus, college, major or majors, admission year, and special track only when they are not already clear.
2. Obtain the official requirement table for that exact program and entry year. Start with `references/official-sources.md`, then prefer the current Yonsei university catalog or the department's official page. Record each source URL and its checked date.
3. Accept a transcript PDF, screenshot, spreadsheet, pasted table, or JSON. Extract only course code, title, credits, completion status, grade, and requirement categories. Do not ask the student to write JSON.
4. Build the private temporary input described in `references/input-format.md`.
5. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/calculate_graduation_progress.py" --input "<temporary-json>"
   ```

6. Present completed, in-progress, and remaining requirements separately. Show which source supports each rule.
7. Mark the result as advisory when a category, transfer credit, repeated course, exception, or official source is unresolved. Never claim that the calculation is an official graduation audit.

## Rules

- Match the student's admission year and program before calculating.
- Do not silently reuse another department's requirements.
- Count a course once toward total earned credits. Requirement-category overlap is allowed only when the supplied official rule explicitly permits it.
- Treat in-progress courses separately from completed courses.
- Preserve waivers and non-course requirements as explicit facts; do not infer them.
- Direct the student to the department office or official portal audit for final confirmation.
