---
name: search-yonsei-spaces
description: Filter and rank a user-supplied Yonsei space availability snapshot by date, time containment, minimum capacity, building, and required equipment. Use after the user exports, pastes, or transcribes official space rows; never claim the result is current availability.
---

# Search Yonsei Spaces

Return rooms that satisfy explicit requirements in one supplied snapshot.

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
