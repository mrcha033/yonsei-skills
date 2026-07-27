---
name: check-rms-participants
description: Check a privacy-minimized, user-provided Yonsei RMS participant snapshot for project-period bounds, duplicate assignments, missing allocation data, and overlapping allocation above 100 percent. Use when a researcher wants an offline participant consistency review without querying or changing RMS.
---

# Check RMS Participants

Check declared participant periods and allocations within one supplied project.

## Run

Provide `captured_at`, `project_code`, `project_period`, and `participants`:

```bash
python3 "$SKILL_DIR/scripts/check_rms_participants.py" --input rms-participants.json
```

`project_period` and every participant assignment use ISO `start_date` and
`end_date`. Each assignment requires a locally chosen, pseudonymous
`participant_key` and `role`; `status` and `allocation_percent` are optional.
Do not include names, contact details, student or employee IDs, government
identifiers, or financial identifiers.

The checker reports assignments outside the project period, exact duplicate
assignments, and overlapping supplied allocations above 100 percent. Missing
allocation values remain in `unknowns`; they are never guessed.

## Boundaries

- Process only user-supplied JSON or Excel-transcribed data.
- Treat role and status labels as opaque snapshot values; do not infer RMS policy.
- Reject credentials and direct identifiers rather than echoing them.
- Do not invite, remove, approve, save, or submit a participant change.

Official manual context:
<https://research.yonsei.ac.kr/research/data_manual.do?articleNo=114666&mode=view>
