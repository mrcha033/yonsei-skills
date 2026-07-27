---
name: prepare-yonsei-space-request
description: Build a complete but unsent Yonsei space reservation draft and evidence checklist from explicit applicant, room, time, headcount, purpose, and equipment details. Use after rule checking and before the user manually reviews the official form; never submit or imply approval.
---

# Prepare Yonsei Space Request

Return a structured draft and missing-field checklist.

## Run

```bash
python3 "$SKILL_DIR/scripts/prepare_space_request.py" --input request.json
```

Required fields are `applicant_type`, `organizer`, `contact`, `space_id`,
`space_name`, `date`, `start`, `end`, `headcount`, and `purpose`.
`equipment` and `notes` are optional arrays or text.

The runtime returns `ready_for_user_review`, never `submitted`.

## Boundaries

- First run `$check-yonsei-space-rules` and attach its verdict under `rule_report`.
- Keep contact details in the user's local input; do not repeat them in chat unless needed.
- Require the user to review the exact official form immediately before any future submission.
- Never submit, pay, approve, or claim a hold.
