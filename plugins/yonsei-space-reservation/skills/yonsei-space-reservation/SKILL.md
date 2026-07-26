---
name: yonsei-space-reservation
description: Search Yonsei space availability and prepare a reservation, change, or cancellation with explicit confirmation before submission. Use for rooms, campus spaces, dates, capacities, equipment, registered groups, reservation rules, or space.yonsei.ac.kr access.
---

# Yonsei Space Reservation

Search first and stop immediately before any reservation state change.

## Workflow

1. Validate the official HTTPS entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show space --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe space --json
   ```

2. Establish requester role, campus, date and time, capacity, purpose, equipment, accessibility, and acceptable alternatives.
3. Open the authenticated browser, inspect current availability and rules, and preserve the source timestamp.
4. Present room, date, start and end time, requester or group, purpose, fee or deposit, cancellation policy, and any administrator review.
5. Ask for explicit confirmation of those exact values before the final reservation, change, or cancellation submission.
6. Verify the official request status afterward; do not treat a button click or spinner as confirmation.

Never request credentials or payment details in chat. Do not launch a VPN client; diagnose a post-login network failure before considering any network requirement.
