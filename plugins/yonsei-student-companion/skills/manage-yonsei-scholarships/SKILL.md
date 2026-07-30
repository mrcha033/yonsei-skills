---
name: manage-yonsei-scholarships
description: Find, rank, track, and help apply for Yonsei scholarships using official notices and the student's authorized Underwood status, eligibility facts, deadlines, and required documents. Use when a student asks which scholarships they can apply for or wants help completing one.
---

# Manage Yonsei Scholarships

Show the best realistic opportunities first and carry one selected application
to the official final confirmation.

## Workflow

1. Search current official Yonsei scholarship notices and follow
   `$connect-yonsei-session` to read the student's visible Underwood scholarship
   application and selection states.
2. Use only eligibility facts the student supplied or the official page shows:
   campus, college, major, year, enrollment, income bracket, grades, credits,
   prior awards, nationality, and special qualifications.
3. Record deadline, benefit or amount, eligibility state, required documents,
   missing documents, overlap restrictions, and application state.
4. Rank the opportunities:

   ```bash
   python3 "$SKILL_DIR/scripts/rank_scholarships.py" --input "<temporary-json>"
   ```

5. Present eligible opportunities first, then uncertain ones with the exact
   fact needing confirmation. Do not call an opportunity eligible when a
   required fact is unknown.
6. For a selected scholarship, open the official form, fill supplied facts,
   attach only student-approved files, show the full submission summary, ask
   for confirmation, submit once, and verify the official received state.

## Boundaries

- Never fabricate household, income, grade, or recommendation information.
- Do not upload sensitive documents before the student selects the scholarship.
- Do not submit, withdraw, or accept an award without action-time confirmation.
