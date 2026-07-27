---
name: find-missing-yri-achievements
description: Compare a user-provided reference achievement list with a self-owned YRI JSON or Excel-transcribed snapshot and return identifier-based missing candidates, ambiguous matches, and possible duplicates. Use when a researcher wants an offline reconciliation before reviewing or requesting a YRI change.
---

# Find Missing YRI Achievements

Reconcile two supplied lists without claiming that a record is definitively
absent from the live system.

## Run

Provide `captured_at`, `owner_scope: "self"`, `reference_achievements`, and
`yri_achievements`:

```bash
python3 "$SKILL_DIR/scripts/find_missing_yri_achievements.py" --input reconciliation.json
```

Each row needs a documented YRI `type`. Matching uses DOI first, then KRI ID,
then normalized `type` + `title` + four-digit `year`. ISSN is retained as
context but is not treated as a work-level identifier. Rows without a stable
matching key and rows with multiple candidates remain unresolved.

Report `missing_candidates` as review candidates, not confirmed omissions.
Check `ambiguous_matches`, `possible_duplicates`, `unresolved_references`, and
`complete` before drawing conclusions.

## Boundaries

- Use only user-supplied, self-owned data; do not query YRI, KRI, DOI, or ISSN services.
- Do not invent live fields, fuzzy-match titles, or silently pick an ambiguous record.
- Reject credentials and preserve only declared achievement metadata.
- Do not create, modify, approve, or submit a record.

Official workflow context:
<https://ysrnd.yonsei.ac.kr/main/noticeDetail.do?key=262&type=YRI>
