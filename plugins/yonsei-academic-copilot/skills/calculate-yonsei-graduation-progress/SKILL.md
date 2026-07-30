---
name: calculate-yonsei-graduation-progress
description: Read the student's authorized Underwood credit-progress table and calculate advisory Yonsei graduation progress from official entry-year, college, and major requirements. Use when a student asks what graduation requirements are complete, what credits or required courses remain, or whether a planned course can fill a requirement.
---

# Calculate Yonsei Graduation Progress

Use the deterministic calculator instead of estimating requirements from memory.

## Workflow

1. Ask for the student's campus, college, major or majors, admission year, and special track only when they are not already clear.
2. Follow `$connect-yonsei-session` and read the existing Underwood
   credit-progress table. Capture first, second, and third major; minor; micro
   major; track or depth; requirement; earned; in-progress; recognized;
   substituted; cross-recognized; missing; and total remaining values.
3. Do not press the official **자가진단** action automatically. Read an existing
   result; trigger a new official diagnosis only when the student explicitly
   asks and confirms that action.
4. Obtain the official requirement table for that exact program and entry year. Start with `references/official-sources.md`, then prefer the current Yonsei university catalog or the department's official page. Record each source URL and its checked date.
5. Accept a transcript PDF, screenshot, spreadsheet, pasted table, or JSON when
   a live authorized record is unavailable. Extract only course code, title,
   credits, completion status, grade, and requirement categories. Do not ask
   the student to write JSON.
6. Build the private temporary input described in `references/input-format.md`.
7. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/calculate_graduation_progress.py" --input "<temporary-json>"
   ```

8. Present the official snapshot, completed, in-progress, and remaining
   requirements separately. Show which source supports each rule.
9. Preserve the Underwood warning that special department requirements may be
   incomplete. Mark the result as advisory when a category, transfer credit,
   repeated course, exception, or official source is unresolved. Never claim
   that the calculation is an official graduation audit.

## Rules

- Match the student's admission year and program before calculating.
- Do not silently reuse another department's requirements.
- Count a course once toward total earned credits. Requirement-category overlap is allowed only when the supplied official rule explicitly permits it.
- Treat in-progress courses separately from completed courses.
- Preserve waivers and non-course requirements as explicit facts; do not infer them.
- Direct the student to the department office or official portal audit for final confirmation.
