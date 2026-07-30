# Certificate paths by platform

Detect the host with `prepare_certificate_issue.py`; do not ask a student to
identify technical components.

## Windows

For a PDF result, use the same packaged loopback compatibility printer used on
macOS and Linux. The university's native ICT ReportX component rejects ordinary
PDF virtual printers, so it is not the PDF path. Prepare the pinned runtime
assets from a verified installed `REPORTX.exe` or the verified official
installer, start the local listener, and let the authenticated official page
send its normal `/SSO` handoff. After the PDF is durably saved and its digest
is re-read successfully, notify the official print-completion endpoint once.

Use native ICT ReportX only when the student explicitly requests a named
physical printer. Never run the native listener and the local listener on the
same port at the same time.

## Windows, macOS, and Linux PDF

Use the local loopback compatibility agent as the PDF virtual-printer target
for the student's own authenticated free-print handoff. It saves the prepared
free-print result as a compatibility PDF and may submit an already saved PDF to
a named CUPS printer only after explicit confirmation.
The legacy implementation filename `reportx_mac_agent.py` is retained for
backward compatibility; the supported runtime is Windows, macOS, and Linux.

Require the bundled redistribution-authorized `YonseiB` title face and
`YonseiL` body face before live rendering. Validate their pinned hashes, map
bold or title text to `YonseiB`, map regular or body text to `YonseiL`, and
reject any rendered PDF containing another font. Never produce a live
certificate with a generic Korean fallback.

The default and advertised outcome is the free-print PDF virtual-print result.
The separate paid **전자증명서발급** product is out of scope; never switch to it
unless the student explicitly changes the request.

## Browser-only products

If the current chat product cannot control the student's desktop browser, leave
the exact official page open when possible and stop after the reviewed issuance
summary. Do not ask for a password, OTP, cookie, or exported browser session.
