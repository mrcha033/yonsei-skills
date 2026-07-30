---
name: manage-yonsei-teaching-credential
description: Track Yonsei teaching-credential eligibility, required courses, aptitude and personality tests, first aid, teaching practicum, sexual-violence prevention training, applications, and issuance steps. Use when a student asks whether 교직이수 is on track or what remains.
---

# Manage Yonsei Teaching Credential

Combine the student's authorized Underwood state with the current official
rules for their admission year, college, department, and teaching subject.

## Workflow

1. Follow `$connect-yonsei-session` and read the visible teaching-credential
   application and progress menus. Ask for admission year, program, and
   teaching subject only when not shown.
2. Obtain the current official requirements for that exact profile. Capture
   course credits, required courses, aptitude and personality tests, first-aid
   training, teaching practicum, prevention training, grades, applications, and
   other explicitly listed requirements.
3. Keep completed, in-progress, scheduled, missing, and unknown items separate.
4. Calculate the advisory progress:

   ```bash
   python3 "$SKILL_DIR/scripts/calculate_teaching_credential.py" --input "<temporary-json>"
   ```

5. Show what is complete, the next dated action, and what must be confirmed by
   the department or teaching-profession office.
6. For an application or practicum request, prepare the official form, show the
   full summary, ask for confirmation immediately before submission, act once,
   and verify the official state.

## Boundaries

- Never infer eligibility from completed courses alone.
- Do not trigger an official diagnosis or submit an application unless the
  student explicitly requests it.
- Keep the result advisory until the responsible Yonsei office confirms it.
