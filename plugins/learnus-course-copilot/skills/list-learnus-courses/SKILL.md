---
name: list-learnus-courses
description: Extract the authorized user's visible LearnUs course index from a dashboard snapshot as a deduplicated structured list. Use when the user asks which LearnUs courses they have, wants course URLs or IDs, or needs a course selected for a later task.
---

# List LearnUs Courses

Return one result only: the visible course index. Do not collect deadlines or materials.

## Workflow

1. If an HTML dashboard snapshot is not supplied, use the sibling session client:

   ```bash
   python3 "$SKILL_DIR/../manage-learnus-session/scripts/learnus_headless.py" fetch \
     --url "https://ys.learnus.org/my/" \
     --output "<fresh secure temporary path>"
   ```

2. Parse the snapshot:

   ```bash
   python3 "$SKILL_DIR/scripts/list_courses.py" \
     --html "<snapshot>" \
     --base-url "https://ys.learnus.org/my/"
   ```

3. Return each course name, stable course ID when present, and redacted LearnUs URL. Preserve the dashboard order.
4. If the result is `login_required`, invoke `$manage-learnus-session`. If it is `blocked`, report the access or maintenance boundary without treating it as authenticated.
5. Delete temporary HTML after extracting the result.

## Boundaries

- Do not infer enrollment from arbitrary links outside an authenticated dashboard-shaped page.
- Do not use the base URL itself as authentication evidence.
- Do not return deadlines, files, completion, grades, or attendance.
- Keep signed query values out of output.

Run `python3 "$SKILL_DIR/scripts/verify_course_index.py"` after parser changes.
