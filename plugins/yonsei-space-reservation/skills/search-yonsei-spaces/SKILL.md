---
name: search-yonsei-spaces
description: Read the authorized live Yonsei space page first, then filter and rank current options by date, time containment, minimum capacity, building, and required equipment; use a user-supplied screenshot, pasted table, export, or JSON only when the live page is unavailable or intentionally supplied. Use when a student asks which current spaces match their requirements before preparing a request.
---

# Search Yonsei Spaces

Return rooms that satisfy explicit requirements in one supplied snapshot.

## Prepare the input

When the user attaches a space list or pastes rows, extract only visible room,
date, time, capacity, equipment, and availability fields into a private
temporary JSON file. Do not ask the user to write JSON. Ask for requirements in
ordinary language and preserve the capture time.

## Run

```bash
python3 "$SKILL_DIR/scripts/search_spaces.py" --input spaces.json
```

Example input:

```json
{
  "spaces": [
    {
      "id": "room-1",
      "name": "세미나실",
      "building": "학생회관",
      "date": "2026-07-30",
      "available_start": "13:00",
      "available_end": "17:00",
      "capacity": 20,
      "equipment": ["projector"],
      "available": true
    }
  ],
  "query": {
    "date": "2026-07-30",
    "start": "14:00",
    "end": "16:00",
    "minimum_capacity": 12,
    "required_equipment": ["projector"]
  }
}
```

Rows missing a field needed for the query are reported under
`excluded_unknown`, not treated as matches.

## Boundaries

- Use only an explicit, dated user-supplied snapshot.
- A match is a planning candidate, not a hold or reservation.
- Check the proposal with `$check-yonsei-space-rules`.
- Never send a reservation request or claim live availability.
