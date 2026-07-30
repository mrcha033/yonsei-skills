---
name: list-learnus-materials
description: Extract the files, folders, resources, and visible media entries from an authorized LearnUs course snapshot as a structured material list. Use when the user asks for lecture slides, readings, recordings, resource links, or a per-course material inventory.
---

# List LearnUs Materials

Return one result only: the visible material inventory. Do not download or redistribute resources.

## Workflow

1. When a browser is available, reuse the student's authenticated LearnUs
   profile, select the exact course from **My courses**, and read its visible
   resource activities. If login appears, invoke `$manage-learnus-session`
   once and resume in the same browser.
2. When an HTML course snapshot is supplied, or the student explicitly chose
   optional terminal mode, parse it with:

   ```bash
   python3 "$SKILL_DIR/scripts/list_materials.py" \
     --html "<snapshot>" \
     --base-url "https://ys.learnus.org/course/view.php?id=<course-id>"
   ```

3. Return label, material kind, redacted URL, and visible availability state.
   Preserve course order.
4. If a supplied snapshot returns `login_required`, invoke
   `$manage-learnus-session`. If it is `blocked`, stop.
5. Delete temporary HTML after extraction.

## Boundaries

- Include visible files, Moodle resources and folders, and visible VOD/media activities.
- Exclude assignments from the material result.
- Treat a media URL as a visible reference, not permission to bypass playback controls.
- Do not download an entire course or expose signed query values.

Run `python3 "$SKILL_DIR/scripts/verify_material_list.py"` after parser changes.
