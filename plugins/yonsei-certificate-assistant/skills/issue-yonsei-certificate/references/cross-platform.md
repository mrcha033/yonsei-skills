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

## Startup and one-minute hot path

Run `icert_print.py start` immediately when the skill is invoked. It emits the
official Portal URL and the complete one-batch intake shape, then validates the
cached pinned assets or prepares them and starts the local agent. It does not
open or manipulate any browser window. Codex Computer Use must reuse the
student's current browser for the visible official login and portal route; do
not use a CLI-launched profile, Orca, AppleScript, JXA, or coordinate clicks.

While cold setup runs, settle certificate type, language, one-copy output,
transcript rank inclusion, transcript 4.5 conversion inclusion, and any named
physical printer. Purpose is optional. Ask for login completion and issuance
authorization in the same initial pause when the visible official page requires
login. A fully specified prompt that already commands issuance is the
authorization. Validate the resulting review internally without asking for a
second reply. After that, use only
`icert_print.py issue --request ... --output ... --confirm`; there are no
routine mid-flow questions or separate doctor/open/arm/wait/copy steps.

The one-minute objective starts only after the student is visibly logged in,
the complete request is confirmed, and pinned assets are cached. The issue
command binds the browser handoff to its returned `arm_id`, follows only the
matching job, accepts a newly completed or digest-backed safely reused PDF,
verifies the private and exported digests, and refuses to overwrite a different
destination file.
It performs no cold download and uses one command-start deadline capped at 55
seconds so PDF export retains margin. Treat this as the implementation budget,
not live performance evidence until measured on a representative issuance.

## Browser-only products

If the current chat product cannot control the student's desktop browser, leave
the official Portal URL in the handoff and stop after the reviewed issuance
summary. Do not launch another browser profile and do not ask for a password,
OTP, cookie, or exported browser session.
