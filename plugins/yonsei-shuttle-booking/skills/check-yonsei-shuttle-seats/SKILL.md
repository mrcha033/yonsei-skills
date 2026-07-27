---
name: check-yonsei-shuttle-seats
description: Classify seats, waitlist-only status, sold-out status, or unknown status for one user-supplied Yonsei shuttle row using the official client field names. Use after selecting one exact trip from a dated official-screen snapshot; never use for live polling or booking.
---

# Check Yonsei Shuttle Seats

Return one conservative seat-status verdict.

## Run

```bash
python3 "$SKILL_DIR/scripts/check_shuttle_seats.py" --input trip.json
```

Supply one object under `trip`. Include its date, time, route or bus identifier,
`remndSeat`, `resveYn`, and `resveWaitYn` where visible.

The verdict is:

- `seats-available`
- `waitlist-only`
- `sold-out`
- `reservation-closed`
- `unknown`

## Boundaries

- Label the observation as a user-supplied snapshot and preserve its timestamp.
- Return `unknown` when flags or remaining-seat counts conflict or are absent.
- Never treat the result as a reservation receipt.
- Never reserve, cancel, waitlist, spoof eligibility, or poll repeatedly.
