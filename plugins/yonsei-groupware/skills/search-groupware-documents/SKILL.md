---
name: search-groupware-documents
description: Search whitelisted metadata and supplied summaries in an explicit user-supplied groupware document export covering official incoming or outgoing documents, electronic approvals, external administrative-network documents, e-SOP, SMS, FAX, or messenger records. Use only for offline JSON or Excel-transcribed JSON exports explicitly scoped for this search; never search live groupware or unrelated content.
---

# Search Groupware Documents

Search only an export the user explicitly supplied for this task. General groupware or mailbox search is out of scope.

## Workflow

1. Require:
   - `schema_version`: `yonsei-offline-snapshot/v1`
   - `source_kind`: `user_supplied_json` or `excel_transcribed_json`
   - `export_scope`: `explicit_user_supplied_export`
   - `records`: whitelisted document metadata
2. Require `.xlsx` content to be exported or transcribed to JSON first.
3. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/search_groupware_documents.py" \
     --input /path/to/documents.json \
     --query "research agreement" \
     --document-type official_document_inbound
   ```

4. Return structured matches and identify the matched whitelisted fields. Do not expand the search beyond the export.

## Safety contract

- Reject unknown fields rather than indexing or echoing them.
- Do not ingest attachment bodies, complete message bodies, recipient addresses, phone or fax numbers, credentials, or access-control data.
- Never download, open, share, forward, submit, send, fax, message, approve, reject, or delete.
- Do not call a zero-result search proof that no such live document exists.
- Stop on an implicit or missing export scope, duplicate document ID, unsupported document type, malformed keywords, or invalid snapshot.
