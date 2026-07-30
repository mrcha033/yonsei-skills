---
name: draft-yonsei-attendance-correction
description: Create an unsent Korean attendance-correction draft and evidence checklist from a user-confirmed discrepancy found on the authorized live attendance page; use a screenshot, pasted record, export, or JSON only when the live page is unavailable or intentionally supplied. Use when the user wants a reviewable request draft while official submission, status changes, attendance check-in, and external communication remain disabled.
---

# Draft Yonsei Attendance Correction

Create one deterministic, unsent correction draft.

## Prepare the input

Accept the disputed record and evidence in ordinary language or as an attached
screen. Convert only the confirmed fields to a private temporary JSON file. Do
not ask the user to write JSON, and do not infer a recipient or requested status
that the user did not state.

## Run

```bash
python3 "$SKILL_DIR/scripts/draft_correction.py" --input correction.json
```

Provide `captured_at` and a `correction` object containing course code, title, class date, recorded status, requested status, reason, and an `evidence` array. `recipient` is optional and is never inferred.

Review the structured fields, message text, evidence checklist, and `ready_for_user_review`. The output always states `draft_only: true` and `submitted: false`.

## Boundaries

- Never accept or execute `submit`, `send`, `apply_change`, or automatic-action flags.
- Never enter an attendance code, attest presence, use location or beacon data, or perform check-in.
- Process only user-supplied attachments, statements, or JSON and reject credential/session fields.
- Do not claim a correction was accepted; the user must review and submit through the official path.
