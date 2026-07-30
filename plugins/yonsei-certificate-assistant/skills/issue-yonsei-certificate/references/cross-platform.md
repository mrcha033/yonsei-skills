# Certificate paths by platform

Detect the host with `prepare_certificate_issue.py`; do not ask a student to
identify technical components.

## Windows

Use the university's official free-print page and native ICT ReportX component.
Open the official installer only when the diagnostic reports that the listener
is absent. Continue in the same authenticated browser profile. Use the official
ReportX printer selection, then verify the result shown by the official page.

Do not start the local compatibility agent by default on Windows.

## macOS and Linux

Use the local loopback compatibility agent for the student's own authenticated
free-print handoff. It saves an unverified compatibility PDF and may submit an
already saved PDF to a named CUPS printer only after explicit confirmation.
The legacy implementation filename `reportx_mac_agent.py` is retained for
backward compatibility; the supported runtime is macOS and Linux.

Require the bundled redistribution-authorized `YonseiB` title face and
`YonseiL` body face before live rendering. Validate their pinned hashes, map
bold or title text to `YonseiB`, map regular or body text to `YonseiL`, and
reject any rendered PDF containing another font. Never produce a live
certificate with a generic Korean fallback.

If a signed electronic original is required, route the student to the official
paid **전자증명서발급** browser product instead. Do not describe a compatibility
PDF or a print capture as that signed product.

## Browser-only products

If the current chat product cannot control the student's desktop browser, leave
the exact official page open when possible and stop after the reviewed issuance
summary. Do not ask for a password, OTP, cookie, or exported browser session.
