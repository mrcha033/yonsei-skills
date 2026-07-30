---
name: book-yonsei-shuttle
description: Search, reserve, inspect, waitlist, and cancel Yonsei shuttle trips on Windows, macOS, or Linux through the official authenticated shuttle page using origin, destination, date, and time preferences. Use when a student asks to book a Sinchon–International Campus shuttle or manage an existing shuttle reservation.
---

# Book Yonsei Shuttle

Follow the KTX-style sequence: search, shortlist, identify one exact trip,
confirm the write, execute once, and verify the official result.

## Inputs

- origin and destination campus
- travel date
- earliest or preferred departure time
- latest acceptable departure time when relevant
- reservation reason
- whether waitlisting is acceptable

## Workflow

1. Run `scripts/platform_support.py` internally and follow
   `references/cross-platform.md`. Reuse the student's persistent Yonsei browser
   profile and any already open
   official portal tab. Do not start an isolated headless browser. Open:

   `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=shuttle`

2. If login is required, leave the exact official page open and ask the student
   once to sign in there. Resume this workflow in the same browser profile.
   Never ask for the password in chat or inspect browser cookies, storage, or
   saved passwords.
3. Open **예약**, select the departure area and date, and read the live rows.
   Transcribe only the official fields listed in
   `references/official-browser-workflow.md`.
4. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_shuttle_booking.py" --input "<temporary-json>"
   ```

5. Present up to five candidates with selector, vehicle, departure and arrival
   time, route, remaining seats, and waitlist status.
6. After one candidate is unambiguous, reload the official rows and match the
   selector again. Stop if the trip disappeared or any selector field changed.
7. Fill the reservation reason. Immediately before the final reservation or
   waitlist button, ask for confirmation naming the direction, date, time,
   vehicle, and whether it is a seat or waitlist request.
8. Click once. Do not retry an uncertain write.
9. Open **내역/취소** and verify the exact trip appears. Report the official
   seat number or waitlist state when shown.

## Cancellation

Open **내역/취소**, identify the exact existing trip, ask for action-time
confirmation, click once, and verify that it no longer appears in the active
reservation list or that the official page reports cancellation.

## Boundaries

- Never bypass NetFunnel, quotas, reservation dates, role rules, or seat rules.
- Do not poll aggressively.
- Do not treat a prepared selector or button click as success; verify the
  official reservation history.
- If the result after a write is ambiguous, report `verification-required` and
  do not repeat the request.
