---
name: check-rms-budget
description: Check arithmetic and exceptions in a user-provided Yonsei RMS JSON or Excel-transcribed budget snapshot, including allocated, executed, committed, remaining, and optional supplied totals. Use when a researcher wants an offline budget consistency review without querying or changing RMS.
---

# Check RMS Budget

Perform deterministic arithmetic on one supplied RMS budget snapshot.

## Run

Provide `captured_at`, `project_code`, `currency`, and a `budget_lines` array:

```bash
python3 "$SKILL_DIR/scripts/check_rms_budget.py" --input rms-budget.json
```

Each line requires a unique `category`, non-negative `allocated` and `executed`
amounts, and optional non-negative `committed`. Amounts may be JSON numbers or
decimal strings. Optional `supplied_totals` may contain the same three fields
plus `remaining`; mismatches are reported explicitly.

Review `issues`, each line's `calculated_remaining`, and `complete`. Negative
remaining is an arithmetic exception in the supplied snapshot, not a claim
about policy or live RMS state.

## Boundaries

- Process only user-supplied JSON or Excel-transcribed data.
- Reject credentials, high-risk personal or financial identifiers, non-finite values, and duplicate categories.
- Do not infer allowable spending, policy compliance, reimbursement eligibility, or undocumented RMS fields.
- Do not save, approve, submit, transfer, or alter a budget.

Official manual context:
<https://research.yonsei.ac.kr/research/data_manual.do?articleNo=114666&mode=view>
