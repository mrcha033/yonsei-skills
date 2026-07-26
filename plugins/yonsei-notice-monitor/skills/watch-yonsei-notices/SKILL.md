---
name: watch-yonsei-notices
description: Detect newly listed, changed, and no-longer-visible notices across the current bounded official Yonsei University and Sinchon IT notice windows using a user-selected JSON state file. Use for recurring Yonsei notice checks, monitoring a topic, comparing with a prior run, or building a local read-only notice watch without credentials.
---

# Detect Yonsei Notice Changes

Require the user to choose or approve an explicit state path. Then establish or compare a baseline:

```bash
python3 "$SKILL_DIR/scripts/watch_yonsei_notices.py" \
  --source all \
  --contains "메일" \
  --state "/explicit/user-approved/path/yonsei-mail-notices.json"
```

The first run sets `initialized: true`, writes the baseline, and intentionally returns no `added` alerts. Later runs report `added`, `updated`, and `missing_from_current_window`. Use `--dry-run` to compare without replacing the state.

Read `partial`, `errors`, `source_health_issues`, and `state_write_blocked_reason` before reporting changes. A partial fetch never replaces a healthy baseline. A source that suddenly parses zero items after a healthy non-empty baseline is reported as `suspicious_empty_source`; its baseline is retained because the official page may have changed shape. A genuinely empty first run is still allowed to establish a baseline. Never describe `missing_from_current_window` as deletion: an item can merely have rolled out of a source's bounded recent window.

Keep separate state files for different source, topic, or date filters. The command rejects a changed query for an existing state path; use another path, or pass `--reset` only when the user explicitly asks to replace that baseline.

Do not invent a default state location or persist anything unless `--state` is explicitly supplied. This workflow is public, read-only, and requires neither credentials nor VPN.
