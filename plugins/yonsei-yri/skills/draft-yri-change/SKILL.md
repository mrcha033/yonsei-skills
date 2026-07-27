---
name: draft-yri-change
description: Build a structured, offline draft of a Yonsei YRI achievement modification request from user-supplied before and after values. Use when a researcher has identified an issue in their own YRI snapshot and wants a reviewable field-level change draft without saving or submitting anything.
---

# Draft YRI Change

Create a reviewable modification-request draft; never operate YRI.

## Run

Provide `captured_at`, `owner_scope: "self"`, and a `change` object:

```bash
python3 "$SKILL_DIR/scripts/draft_yri_change.py" --input yri-change.json
```

`change` requires `requested_action: "request-modification"`, a `record` with
`record_id`, documented YRI `type`, and `title`, plus `before`, `after`, and a
plain-language `reason`. The offline contract permits changes only to `title`,
`year`, `kri_id`, `issn`, `doi`, and `note`. Optional `attachments` are labels
only; the script does not read files.

Review the generated field-level `changes` and `draft_text`. The output is not
a YRI form payload and must not be described as submitted.

## Boundaries

- Use only the user's own supplied record snapshot.
- Reject submit, send, save, delete, approve, or execute directives.
- Do not change approval state or infer undocumented live-system fields.
- Do not log in, open YRI, write files, or submit a modification request.

Official workflow context:
<https://ysrnd.yonsei.ac.kr/main/noticeDetail.do?key=262&type=YRI>
