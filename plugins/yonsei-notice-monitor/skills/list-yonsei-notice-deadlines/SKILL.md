---
name: list-yonsei-notice-deadlines
description: Extract structured application, submission, payment, registration, and event date mentions from a bounded set of official Yonsei University and Sinchon IT notices. Use when a user asks what Yonsei deadlines are upcoming, which dates appear in scholarship or tuition notices, or wants deadline candidates filtered by notice topic, publication window, or deadline window.
---

# Extract Yonsei Notice Deadlines

Run the bounded detail extractor:

```bash
python3 "$SKILL_DIR/scripts/list_yonsei_notice_deadlines.py" \
  --source all \
  --contains "장학" \
  --as-of 2026-07-27 \
  --deadline-from 2026-07-27 \
  --deadline-to 2026-08-31 \
  --limit 10
```

Yearless mentions are anchored to the notice publication date, including only a bounded December-to-January rollover. A shortened dotted range end is recognized only beside a range separator and inherits its explicit or publication-anchored start year. Compact dotted values are not treated as standalone dates. Use `--as-of` when the user asks for upcoming dates; it only controls `upcoming`/`past` classification. `--from` and `--to` filter notice publication dates. `--deadline-from` and `--deadline-to` filter extracted mention dates.

Each mention exposes `range_role` as `start`, `end`, or `single`. When an adjacent `HH:MM` or Korean AM/PM time is present, `time` contains normalized 24-hour time and `time_text` retains the matched source wording. The extractor fetches at most `--limit` official detail pages, with fixed response and text limits. Inspect `detail_status`, `partial`, and `errors`. Quote the short returned `context`, link the official notice, and call results “extracted deadline mentions” rather than authoritative calendar entries. A notice can describe exceptions or multiple cohorts that require reading the source.

Use `--include-all-dates` only when the user also wants event and schedule dates. Use `--no-fetch-details` only for a fast RSS/title-only pass.
