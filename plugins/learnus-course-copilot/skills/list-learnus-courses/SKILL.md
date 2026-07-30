---
name: list-learnus-courses
description: Read the authorized user's live LearnUs dashboard first and return the visible course index as a deduplicated structured list; use a user-supplied screenshot, pasted page, export, or JSON only when the live page is unavailable or intentionally supplied. Use when the user asks which LearnUs courses they have, wants course URLs or IDs, or needs a course selected for a later task.
---

# List LearnUs Courses

Return one result only: the visible course index. Do not collect deadlines or materials.

## Preferred command path

Call `yonsei_student` with `intent: "learnus"` and use the courses in
`primary_result`. If login is required, call `yonsei_bridge_connect` once and
resume after the visible login.

## Workflow

1. When a browser is available, reuse the student's authenticated LearnUs
   profile and open `https://ys.learnus.org/my/`. If login appears, invoke
   `$manage-learnus-session` once and resume in the same browser.
2. Read the visible course cards from the authorized **My courses** dashboard.
   Do not navigate into every course.
3. When an HTML dashboard snapshot is supplied, or the student explicitly chose
   optional terminal mode, parse it with:

   ```bash
   python3 "$SKILL_DIR/scripts/list_courses.py" \
     --html "<snapshot>" \
     --base-url "https://ys.learnus.org/my/"
   ```

4. Return each course name, stable course ID when present, and redacted LearnUs
   URL. Preserve the dashboard order.
5. If a supplied snapshot returns `login_required`, invoke
   `$manage-learnus-session`. If it is `blocked`, report the access or
   maintenance boundary without treating it as authenticated.
6. Delete temporary HTML after extracting the result.

## Boundaries

- Do not infer enrollment from arbitrary links outside an authenticated dashboard-shaped page.
- Do not use the base URL itself as authentication evidence.
- Do not return deadlines, files, completion, grades, or attendance.
- Keep signed query values out of output.

Run `python3 "$SKILL_DIR/scripts/verify_course_index.py"` after parser changes.
