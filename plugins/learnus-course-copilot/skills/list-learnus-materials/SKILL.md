---
name: list-learnus-materials
description: Extract the files, folders, resources, and visible media entries from an authorized LearnUs course snapshot as a structured material list. Use when the user asks for lecture slides, readings, recordings, resource links, or a per-course material inventory.
---

# List LearnUs Materials

Return one result only: the visible material inventory. Do not download or redistribute resources.

## Workflow

1. Obtain the exact authorized course page with the sibling session client when no snapshot is supplied:

   ```bash
   python3 "$SKILL_DIR/../manage-learnus-session/scripts/learnus_headless.py" fetch \
     --url "https://ys.learnus.org/course/view.php?id=<course-id>" \
     --output "<fresh secure temporary path>"
   ```

2. Parse the snapshot:

   ```bash
   python3 "$SKILL_DIR/scripts/list_materials.py" \
     --html "<snapshot>" \
     --base-url "https://ys.learnus.org/course/view.php?id=<course-id>"
   ```

3. Return label, material kind, redacted URL, and visible availability state. Preserve course order.
4. If the result is `login_required`, invoke `$manage-learnus-session`. If it is `blocked`, stop.
5. Delete temporary HTML after extraction.

## Boundaries

- Include visible files, Moodle resources and folders, and visible VOD/media activities.
- Exclude assignments from the material result.
- Treat a media URL as a visible reference, not permission to bypass playback controls.
- Do not download an entire course or expose signed query values.

Run `python3 "$SKILL_DIR/scripts/verify_material_list.py"` after parser changes.
