---
name: search-yonsei-notices
description: Search and filter current official Yonsei University and Sinchon IT service notices, with inclusive publication-date ranges, global cross-source sorting, publisher metadata, excerpts, and direct official links. Use for requests such as finding Yonsei announcements about scholarships, tuition, registration, accounts, security, outages, or notices published during a specific period.
---

# Search Yonsei Notices

Run the plugin-local deterministic search:

```bash
python3 "$SKILL_DIR/scripts/search_yonsei_notices.py" \
  --source all \
  --contains "장학" \
  --from 2026-07-01 \
  --to 2026-07-31 \
  --limit 20
```

Omit filters the user did not request. Treat `--from` and `--to` as inclusive publication dates. Use `--source university` or `--source it` only when the user narrows the board.

Read the JSON `partial` and `errors` fields before reporting results. Return each notice's title, publisher, publication date, and official URL. Distinguish the publication date from any event date mentioned in the title or excerpt.

Do not claim that absence from the bounded official source window proves that no older notice exists. Do not use credentials, VPN, reposts, or search-result snippets.
