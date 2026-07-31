---
name: check-yonsei-shuttle-seats
description: Read one selected trip on the authorized live Yonsei shuttle page first and classify seats, waitlist-only, sold-out, or unknown status using official client fields; use a user-supplied screenshot, pasted row, export, or JSON only when the live page is unavailable or intentionally supplied. Use after selecting an exact trip; never use for aggressive polling or booking.
---

# Check Yonsei Shuttle Seats

Return one conservative seat-status verdict.

## Prepare the input

Accept an attached shuttle screen or a pasted row and extract only the selected
trip into a private temporary JSON file. Do not ask the user to write JSON.
Keep missing flags unknown and preserve when the screen was captured.

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
