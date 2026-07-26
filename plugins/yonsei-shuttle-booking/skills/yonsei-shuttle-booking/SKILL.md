---
name: yonsei-shuttle-booking
description: Check official Yonsei Sinchon and International Campus shuttle options and prepare a reservation or cancellation with an explicit final confirmation. Use for shuttle timetables, seat availability, campus direction, boarding date, booking, cancellation, or shuttle SSO access.
---

# Yonsei Shuttle Booking

Use the official SSO entry and require confirmation immediately before a reservation or cancellation changes state.

## Workflow

1. Resolve and probe the stable shuttle entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show shuttle --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe shuttle --json
   ```

2. Open the authenticated browser flow. Never reuse a stale `requestTimeStr` URL or request credentials in chat.
3. Collect direction, boarding point, date, departure time, arrival estimate, seat status, eligibility, and cancellation conditions.
4. Present the exact proposed trip. Ask for explicit confirmation containing direction, date, time, and passenger before clicking the final reservation or cancellation control.
5. After action, verify the reservation list or official receipt page. Report failure without repeating the submission blindly.

Do not hoard seats, bypass booking limits, automate high-frequency polling, or launch a VPN client. Diagnose an actual authenticated network failure first.
