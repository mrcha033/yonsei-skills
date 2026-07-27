---
name: list-yri-achievements
description: Normalize a user-provided, self-owned Yonsei YRI JSON or Excel-transcribed snapshot into a deterministic achievement list grouped by official achievement type and supplied approval state. Use when a researcher wants to review their own YRI records without logging in or querying the live system.
---

# List YRI Achievements

List only the records present in one supplied YRI snapshot.

## Run

Prepare JSON with `captured_at`, `owner_scope: "self"`, optional
`source_format` (`json` or `excel-transcribed`), and an `achievements` array:

```bash
python3 "$SKILL_DIR/scripts/list_yri_achievements.py" --input yri-snapshot.json
```

Each achievement requires `type`, `title`, and `approval_status`. Supported
types are the documented YRI categories: 논문, 저역서, 전시작품, 연구비,
지식재산, 기술이전, 수상, 학술활동, and 보고서. English canonical type names
shown in the script output are also accepted. `year`, `record_id`, `kri_id`,
`issn`, and `doi` are optional.

Read `warnings` and `complete` before reporting. State the snapshot timestamp;
never present it as live YRI state.

## Boundaries

- Process only a user-provided snapshot scoped to the user's own achievements.
- Do not log in, fetch YRI, verify KRI/ISSN externally, or infer absent records.
- Reject credential or session fields and preserve only the declared record fields.
- Do not create, modify, approve, or submit a YRI record.

Official workflow context:
<https://ysrnd.yonsei.ac.kr/main/noticeDetail.do?key=262&type=YRI>
