---
name: submit-yonsei-space-request
description: Search and submit a Yonsei space reservation request on Windows, macOS, or Linux through the official authenticated space system using date, time, headcount, purpose, building, and equipment preferences. Use after the student asks to actually apply for a classroom or campus space, not merely draft the request.
---

# Submit Yonsei Space Request

Use the official browser form and separate preparation from the final
submission.

## Preferred command path

Call `yonsei_student` with `intent: "space"`. Put date, start/end time,
headcount, purpose, building, equipment, organizer, and contact in `request`;
never pass screen labels. After selection, repeat with its `selection_id`,
`action: "submit"`, and `confirmed: true`. Report only `primary_result`.

## Workflow

1. Run `scripts/platform_support.py` internally and follow
   `references/cross-platform.md`. Reuse the student's persistent Yonsei browser
   profile and any already open
   official portal tab. Do not start an isolated headless browser. Open
   `https://space.yonsei.ac.kr/`.
2. If login is required, leave the exact official page open and ask the student
   once to sign in there. Resume this workflow in the same browser profile.
   Never request the password in chat or inspect cookies, local storage, or
   saved passwords.
3. Collect date, start and end time, headcount, purpose, preferred building,
   required equipment, organizer, and contact information.
4. Search the official page. Transcribe the exact selected room, displayed
   capacity, available interval, fee when shown, and any required agreement.
5. Run `$check-yonsei-space-rules`, then `$prepare-yonsei-space-request`.
6. Build the reviewed action summary:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_space_submission.py" --input "<temporary-json>"
   ```

7. Stop when the result is not `ready_for_confirmation`.
8. Fill the official form, but do not click the final application button yet.
9. Immediately before submission, ask for confirmation naming the room, date,
   time, headcount, purpose, displayed fee, and contact information being sent.
10. Submit once. Do not automatically retry an uncertain response.
11. Verify the request in the official application history and report its
    request number and status. Do not describe a submitted request as approved.

## Boundaries

- Never bypass date limits, restricted periods, affiliation priority, capacity,
  fees, approval, or permit requirements.
- Do not make a payment without a separate explicit request and action-time
  confirmation.
- If the official history does not show the request, report
  `verification-required` and do not submit it again.
- Treat approval, payment, and permit printing as later stages.
