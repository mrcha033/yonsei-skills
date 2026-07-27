---
name: summarize-rms-project
description: Normalize a user-provided Yonsei RMS JSON or Excel-transcribed project snapshot into a privacy-minimized summary of project identity, period, budget, participant counts, and supplied workflow state. Use when a researcher needs an offline project overview without querying or changing RMS.
---

# Summarize RMS Project

Summarize one supplied RMS project snapshot and expose internal contradictions.

## Run

Provide `captured_at`, optional `source_format`, and a `project` object:

```bash
python3 "$SKILL_DIR/scripts/summarize_rms_project.py" --input rms-project.json
```

The declared `project` contract requires `project_code`, `title`, `status`,
`period` (`start_date`, `end_date`), `budget` (`currency`, `total`, `executed`,
optional `committed` and `remaining`), `workflow` (`stage`, optional
`pending_action`), and `participants`. Each participant needs a pseudonymous
`participant_key`, `role`, and optional `status`. Do not include names or
institutional identifiers.

Amounts may be JSON numbers or decimal strings and are returned as decimal
strings. Review `issues` and `complete`; the workflow values remain the
snapshot's opaque labels, not interpreted live states.

## Boundaries

- Process only user-supplied JSON or Excel-transcribed data.
- Reject credentials, government identifiers, bank accounts, and tax identifiers.
- Do not query RMS, infer undocumented fields, or expose participant keys in output.
- Do not save, approve, submit, or alter any project or workflow.

Official manual context:
<https://research.yonsei.ac.kr/research/data_manual.do?articleNo=114666&mode=view>
