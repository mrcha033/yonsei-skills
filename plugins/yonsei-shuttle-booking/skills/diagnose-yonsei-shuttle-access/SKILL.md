---
name: diagnose-yonsei-shuttle-access
description: Probe the fixed official Yonsei shuttle entry and public client module, classify direct reachability and the authentication boundary, and enumerate observed read versus write endpoints without credentials. Use for stale portal links, access failures, or unsupported VPN assumptions.
---

# Diagnose Yonsei Shuttle Access

Return one bounded, read-only service diagnosis.

## Run

```bash
python3 "$SKILL_DIR/scripts/diagnose_shuttle_access.py"
```

For a deterministic offline check of a previously downloaded official module:

```bash
python3 "$SKILL_DIR/scripts/diagnose_shuttle_access.py" --module-file shtlrm0020.clx.js
```

Report entry reachability, module reachability, official read/write endpoint
names, and whether authenticated data access or VPN need remains unverified.

## Boundaries

- Fetch only the fixed Yonsei entry and client-module URLs.
- Do not submit SSO forms, accept credentials, connect a VPN, or call service endpoints.
- A public shell or module proves direct connectivity, not logged-in seat access.
- Never invoke any `save...` endpoint.
