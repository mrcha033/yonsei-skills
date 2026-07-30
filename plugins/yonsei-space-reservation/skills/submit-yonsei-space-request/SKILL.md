---
name: submit-yonsei-space-request
description: Search and submit a Yonsei space reservation request through the official authenticated space system using date, time, headcount, purpose, building, and equipment preferences. Use after the student asks to actually apply for a classroom or campus space, not merely draft the request.
---

# Submit Yonsei Space Request

Use the official browser form and separate preparation from the final
submission.

## Workflow

1. Open `https://space.yonsei.ac.kr/` in a browser that can use the student's
   session.
2. If login is required, leave the official page open and ask the student to
   sign in there. Never request the password in chat or inspect cookies, local
   storage, or saved passwords.
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
