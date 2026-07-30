---
name: list-learnus-deadlines
description: Extract assignment deadlines that are visibly associated with assignment activities in an authorized LearnUs course snapshot. Use when the user asks what is due, wants a course deadline report, or needs dated assignments without unrelated page dates.
---

# List LearnUs Deadlines

Return one result only: assignment deadlines supported by visible course-page associations.

## Workflow

1. When a browser is available, reuse the student's authenticated LearnUs
   profile, select the exact course from **My courses**, and read its visible
   assignment activities. If login appears, invoke `$manage-learnus-session`
   once and resume in the same browser.
2. When an HTML course snapshot is supplied, or the student explicitly chose
   optional terminal mode, parse it with:

   ```bash
   python3 "$SKILL_DIR/scripts/list_deadlines.py" \
     --html "<snapshot>" \
     --base-url "https://ys.learnus.org/course/view.php?id=<course-id>"
   ```

3. Return assignment label, associated deadline, redacted URL, and association
   evidence. Preserve course order.
4. Report assignments with ambiguous or missing dates separately; never promote
   a page-global date to a deadline.
5. If a supplied snapshot returns `login_required`, invoke
   `$manage-learnus-session`. If it is `blocked`, stop.
6. Delete temporary HTML after extraction.

## Boundaries

- Prefer a visible `마감`, `제출기한`, `종료`, or `due` label in the assignment's nearest activity container.
- Associate an unlabelled date only when exactly one date appears in that activity container.
- Do not infer deadlines from filenames, neighboring activities, calendars, or page-global dates.
- Do not submit assignments or claim completion.

Run `python3 "$SKILL_DIR/scripts/verify_deadline_report.py"` after parser changes.
