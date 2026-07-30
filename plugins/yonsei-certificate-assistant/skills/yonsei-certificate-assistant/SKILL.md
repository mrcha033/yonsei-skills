---
name: yonsei-certificate-assistant
description: Clean-room macOS interoperability for Yonsei icert free-print ReportX handoffs. Decodes dzreportx tickets, retrieves and decrypts the ticket-authorized prepared report, materializes the proven ReportX runtime logo and verification-number placeholders, and renders a local compatibility PDF. Use for 인터넷즉시발급 on macOS, localhost :65432 failures, ReportX ticket diagnosis, or an FP3/PDF result. Do not use for paid 전자증명서, forged or modified certificates, automatic printing, password collection, or claims that a compatibility PDF is an officially verified original.
---

# Yonsei Certificate Assistant

Use this skill for the free-print path:

`인터넷증명서 → 인터넷즉시발급 → 프린터 출력`

The implementation is a compatibility experiment for a user's own authenticated
issuance session. It does not create, edit, or certify a document.

## Confirmed protocol

The official page posts `PREVIEWENC` and gives the result to:

`http://127.0.0.1:65432/SSO?PARAM=dzreportx:…`

Static clean-room analysis of the current Yonsei installer and a normal,
user-authorized live issuance established:

```text
dzreportx: strip
→ "||" plaintext diagnostic form, or Base64 + ARIA-192-ECB
→ vendor ARIA-192-ECB key schedule
→ key = first 24 ASCII bytes of md5("10001").hexdigest()
→ little-endian uint32 payload length
→ "|" query separators restored to "&"
→ command URL and URLFile/URLPost fields parsed
```

For `SHOWREPORT` and `SHOWREPORT_PRINTAUTO`, ReportX constructs:

`http://{URLFile}?TPID={TPID}&MIN_NO={MINNO}&GIWAN_NO={GIWAN_NO}`

The current Yonsei ticket uses
`icert.yonsei.ac.kr/ys1.0/jsp/report/sendfile.jsp`. The broker upgrades the
ticket host/path to HTTPS, follows no redirects, and accepts only the tracked
response. URLFile and URLCheck share one in-memory cookie jar, matching the
single WinINet session used by ReportX; cookies are never persisted or exposed.

The accepted non-PDF response has a second recovered container layer:

```text
ARIA-192-ECB key = first 24 ASCII bytes of md5(MINNO).hexdigest()
→ LE32 compressed length + zlib bytes + zero cipher padding
→ zlib inflate
→ LE32 primary length + primary bytes
→ LE32 additional count
→ repeated LE32 length + component bytes
```

The Windows path loads the primary as a FastReport VCL `4.7.109`
prepared-report XML stream with FP3 semantics and uses additional streams as
image sidecars. It has no compiled PDF exporter path. The bundled
`render-reportx-fp3-pdf` skill implements the bounded prepared-page subset
observed in the live Yonsei response.

Before rendering a printable page, ReportX performs two extra mutations:

1. `URLCheck` reserves one 16-character verification number. Its response is
   a 1,000-byte Windows buffer: exactly 16 safe ASCII characters followed only
   by NUL padding. The number is formatted `xxxx-xxxx-xxxx-xxxx` and replaces
   the ten-digit `__SERIAL__` placeholder.
2. `__LOGO1__` receives the `원본` bitmap embedded in the exact official
   `REPORTX.exe`. The skill distributes no vendor image; it extracts and
   validates the asset from the pinned Yonsei installer in the user's cache.

`URLCheck` can allocate state even though it is a GET. The agent writes a
durable no-retry guard before the request. `URLPost`/`printcomplete.jsp` is a
separate completion boundary and is never called merely because a PDF was
rendered.

## Run

Network remains off unless explicitly enabled.

```bash
# First use: download the exact official installer, verify it, and extract
# only the two runtime logo BMPs. Requires innoextract.
python3 "$SKILL_DIR/scripts/icert_print.py" prepare-assets

# Decode only; no remote request
python3 "$SKILL_DIR/scripts/icert_print.py" agent

# Full PDF path. The second flag explicitly permits one URLCheck reservation.
python3 "$SKILL_DIR/scripts/icert_print.py" agent \
  --allow-fetch --reserve-document-number
```

In another terminal:

```bash
python3 "$SKILL_DIR/scripts/icert_print.py" open
# In the browser: authenticate and choose the certificate.
python3 "$SKILL_DIR/scripts/icert_print.py" arm
# Within 120 seconds, click 프린터 출력. The arm is one-shot.
python3 "$SKILL_DIR/scripts/icert_print.py" wait-job
python3 "$SKILL_DIR/scripts/icert_print.py" status
```

No DevTools bridge, cookie export, Windows process, VM, or extra Windows
machine is part of the installed workflow.

Private state is under:

`~/.cache/yonsei-certificate-assistant/{agent.token,jobs,output,reservations,official-assets}`

## Interpret the result exactly

| status | Meaning |
| --- | --- |
| `decoded_network_disabled` | Ticket decoded and URLFile reconstructed; no request made |
| `server_report_official_assets_required` | Live runtime placeholders were found, but pinned official assets were not prepared |
| `server_report_document_number_required` | FP3 was decoded, but URLCheck reservation was not explicitly enabled |
| `document_number_reservation_unknown` | URLCheck started but no valid response was retained; retry is blocked |
| `server_report_saved_unrendered` | Exact server response saved as `.reportx`, but its outer container was not decoded |
| `server_report_decoded_unrendered` | Outer container decoded, but profile or renderer rejected unsupported semantics |
| `server_report_rendered_pdf_unverified` | Runtime placeholders were materialized and a compatibility PDF was rendered; `printcomplete` was not called |
| `server_pdf_saved_unverified` | Exact server response is a complete PDF container; official document verification was not performed |
| `decode_failed` | Ticket failed a strict framing, cipher, URL, command, or host check |
| `transport_failed` | Allowlisted request did not complete |
| `protocol_failed` | Response failed status, redirect, size, identity, or broker checks |

Never call a PDF “official,” “original,” or “verified” from `%PDF` structure
alone. Yonsei original verification and the receiving institution's submission
rules remain separate.

## Physical print

The protocol worker never calls CUPS. Only an already saved PDF container can
be submitted, once, to a named printer with an explicit digest recheck:

```bash
python3 "$SKILL_DIR/scripts/icert_print.py" \
  print-job JOB_ID --printer "PRINTER_NAME" --confirm
```

On successful CUPS submission the current implementation still does not call
`printcomplete`; completion acknowledgement remains intentionally separate
until printer-job completion can be established without ambiguity. An
unrendered `.reportx` response is not printable through this command.

## Security invariants

- Bind loopback only; validate Host and Origin before creating a job.
- Accept an exact icert Origin directly. Require a token-authorized, one-shot,
  120-second `arm` for the official iframe handoff when the browser omits Origin
  on the HTTPS-to-loopback navigation.
- `/SSO` requires a non-empty, valid `dzreportx:` envelope.
- `/GETCRYPTARIA` is unsupported; the official local service has no usable
  decrypt endpoint.
- Browser capture routes are removed.
- Control routes require `X-Agent-Token` and reject browser `Origin`.
- Cache directories are `0700`; token, manifest, and artifact files are `0600`.
- Repair legacy cache permissions on startup and reject a non-regular token
  path.
- Raw tickets, decrypted fields, verification-number values, cookies, and
  rejected response bodies are not persisted in manifests.
- Runtime assets require pinned installer, executable, BMP dimensions, format,
  and hashes. Version drift fails closed.
- URLCheck supports one copy only. A durable ticket-hash guard is written
  before the request; timeout, malformed output, or restart cannot trigger an
  automatic retry.
- The verification number is held only long enough to render the PDF. Manifests
  retain status and length, not the value.
- Redact ticket/response/component fingerprints, private paths, and messages
  from the status/job control response. Preserve only the artifact digest needed
  for an explicit print recheck.
- Network is opt-in, HTTPS-only, exact-host, size-bounded, and redirect-free.
- The HTTP client explicitly disables environment and macOS proxy settings.
- Worker concurrency, submission rate, manifest count, and output bytes are
  bounded; duplicate active ticket hashes share one job.
- A physical print attempt is atomically reserved before CUPS. Timeout or a
  nonzero result is `unknown` and cannot be retried automatically.
- Verification stays `not_performed`; printing never changes that state.
- A PDF result must have a recognized header, terminal EOF marker, bounded
  `startxref` target, catalog root, and object framing. This remains structural
  validation only and never changes the unverified state.

## Validate implementation changes

```bash
python3 -B -m unittest -v \
  tests/test_reportx_protocol.py \
  tests/test_reportx_protocol_v1.py \
  tests/test_reportx_document_v1.py \
  tests/test_reportx_mac_agent.py \
  tests/test_reportx_runtime_profile.py \
  tests/test_fp3_pdf.py
```

See `references/icert-print.md` for binary hashes, offsets, and evidence
boundaries.
