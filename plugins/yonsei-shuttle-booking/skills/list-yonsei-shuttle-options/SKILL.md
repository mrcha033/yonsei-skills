---
name: list-yonsei-shuttle-options
description: Read the authorized live Yonsei shuttle page first, then normalize, filter, and sort current trips by date, departure area, time window, and minimum remaining seats; use a user-supplied screenshot, pasted table, export, or JSON only when the live page is unavailable or intentionally supplied. Use when a student asks which current shuttle options match their trip without booking yet.
---

# List Yonsei Shuttle Options

Return matching trips from one explicit snapshot.

## Prepare the input

If the user attaches a shuttle screen or pastes rows, transcribe the visible
route, date, time, and seat fields into a private temporary JSON file. Do not
ask the user to write JSON. Preserve the screen timestamp and ask about
unreadable values rather than treating them as available seats.

## Run

```bash
python3 "$SKILL_DIR/scripts/list_shuttle_options.py" --input shuttle.json
```

Input must contain `options` and may contain `filters`:

```json
{
  "options": [
    {
      "busCd": "BUS1",
      "busNm": "신촌 → 국제",
      "stdrDt": "20260728",
      "beginTm": "0830",
      "endTm": "1000",
      "thrstNm": "신촌",
      "remndSeat": 4
    }
  ],
  "filters": {
    "date": "2026-07-28",
    "origin": "신촌",
    "depart_after": "08:00",
    "minimum_remaining_seats": 1
  }
}
```

The runtime understands the official field names exposed by the shuttle client
and a small set of English aliases. It reports rows excluded because a requested
filter could not be evaluated.

## Boundaries

- Treat the input as a dated user-supplied snapshot, never as current seat data.
- Do not infer a destination from a route label unless the input supplies it.
- Use `$check-yonsei-shuttle-seats` for one selected trip.
- Never reserve, cancel, waitlist, or repeatedly poll.
