---
name: book-yonsei-shuttle
description: Search, reserve, inspect, waitlist, and cancel Yonsei shuttle trips on Windows, macOS, or Linux through the official authenticated shuttle page using origin, destination, date, and time preferences, with internal access recovery. Use when a student asks to book a Sinchon–International Campus shuttle, manage an existing reservation, or continue either task after the official page fails to open.
---

# Book Yonsei Shuttle

Follow the KTX-style sequence: search, shortlist, identify one exact trip,
confirm the write, execute once, and verify the official result.

## Preferred command path

Call `yonsei_student` with `intent: "shuttle"` and put origin, destination,
date, time window, and reason in `request`. Present candidates from
`primary_result`. After the student confirms one, repeat with its opaque
`selection_id`, the requested action, and `confirmed: true`. Never expose DOM
labels or row-matching terms.

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
3. If the official page does not open or the expected shuttle controls are
   missing, run the bundled read-only recovery check internally:

   ```bash
   python3 "$SKILL_DIR/scripts/diagnose_shuttle_access.py"
   ```

   Use it only to distinguish direct connectivity, an authentication boundary,
   and a changed or unavailable official client. Do not expose a separate
   diagnostic workflow to the student. Continue the original booking request
   automatically when the page becomes usable; otherwise explain the one
   concrete recovery step.
4. Open **예약**, select the departure area and date, and read the live rows.
   Transcribe only the official fields listed in
   `references/official-browser-workflow.md`.
   Also read the active outbound and return trips for that date so the
   one-round-trip-per-day rule can be checked.
5. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_shuttle_booking.py" --input "<temporary-json>"
   ```

6. Present up to five candidates with selector, vehicle, departure and arrival
   time, route, remaining seats, and waitlist status.
7. After one candidate is unambiguous, reload the official rows and match the
   selector again. Stop if the trip disappeared or any selector field changed.
8. Fill the reservation reason. Immediately before the final reservation or
   waitlist button, ask for confirmation naming the direction, date, time,
   vehicle, and whether it is a seat or waitlist request.
9. Click once. Do not retry an uncertain write.
10. Open **내역/취소** and verify the exact trip appears. Report the official
   seat number or waitlist state when shown.

## Cancellation

Open **내역/취소**, identify the exact existing trip, ask for action-time
confirmation, click once, and verify that it no longer appears in the active
reservation list or that the official page reports cancellation.

## Boundaries

- Apply the displayed rules: one round trip per day, and cancellation or
  rebooking only until 20 minutes before departure.
- Never bypass NetFunnel, quotas, reservation dates, role rules, or seat rules.
- The internal access check may fetch only the fixed official entry and public
  client module. It must never submit SSO, call shuttle service endpoints,
  connect a VPN, or invoke any `save...` operation.
- Do not poll aggressively.
- Do not treat a prepared selector or button click as success; verify the
  official reservation history.
- If the result after a write is ambiguous, report `verification-required` and
  do not repeat the request.
