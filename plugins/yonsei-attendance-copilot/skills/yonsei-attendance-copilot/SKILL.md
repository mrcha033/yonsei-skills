---
name: yonsei-attendance-copilot
description: Inspect and summarize the user's authorized Yonsei electronic attendance records without performing attendance check-ins or spoofing presence. Use for attendance history, absence or lateness review, discrepancy preparation, electronic roster access, or ysrollbook.yonsei.ac.kr diagnostics.
---

# Yonsei Attendance Copilot

Operate read-only. Never enter an attendance code, attest presence, spoof a device or location, or submit a correction request on the user's behalf.

## Workflow

1. Validate the official entry:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" show attendance --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe attendance --json
   ```

2. Open it in the authenticated browser and ask the user to complete SSO there if needed. Never request credentials in chat.
3. Inspect only the requested course and date range. Record the displayed status, class date, update time when available, and the exact page inspected.
4. Summarize absences, lateness, or discrepancies. For a correction, prepare a draft containing the user's evidence and the official contact or request path, but let the user submit it.
5. Treat direct HTTPS success as reachability evidence only. Diagnose post-login errors before concluding that another network path is required, and do not launch a VPN client.
