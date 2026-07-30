# Yonsei icert ReportX clean-room notes

## Current official source snapshot

The implementation is pinned to the installer linked by the Yonsei icert
site, not to the separate public `uni.webminwon.com` package.

| Asset | Evidence |
| --- | --- |
| Yonsei installer | `https://icert.yonsei.ac.kr/ys1.0/module/ICT_REPORTX_SETUP.exe` |
| installer size/hash | 4,336,176 bytes; SHA-256 `6c37e0bdaef63aba8377fd902a01c350adbc3f849fa0afe9a9cf222ea888f673` |
| installer bundle version | `1.0.0.29` |
| extracted `REPORTX.exe` | 3,782,856 bytes; file version `1.0.0.28`; SHA-256 `ceae3b3ca03656bf2b8bddde2abba7e4d016ad5a42dde3a9d332d29b56959cd5` |
| FastReport runtime | VCL `4.7.109` |

The PE and installer were statically extracted; the Windows binaries were not
executed. A normal user-authorized live issuance on 2026-07-27 validated the
encrypted ticket, URLFile response, outer document container, FP3 stream,
runtime object mutations, and local PDF output. This does not make the local
PDF an officially verified original.

## Browser handoff

Yonsei `reportx.js` posts `COMMAND=PREVIEWENC` to `/servlet/YSBS`. The JSON
response contains an encrypted value `res`, which becomes:

```text
http://127.0.0.1:65432/SSO?PARAM=dzreportx:{res}
```

The loopback service supports `/SSO`, `/SSO_ETC`, health/status controls, and
an explicit print command. `/GETCRYPTARIA` has no operational compatibility
handler. Capture/bridge/cookie-import routes are intentionally absent.

An exact icert Origin can submit directly. An originless HTTPS-to-loopback
navigation requires a token-authorized one-shot arm, valid for 120 seconds.

## Ticket cipher and parser

The ticket is either a `||` plaintext diagnostic body or strict Base64 over
vendor ARIA-192-ECB. The key is:

```python
hashlib.md5(b"10001").hexdigest().encode("ascii")[:24]
# b"d89f3a35931c386956c1a402"
```

The vendor cipher is not byte-for-byte RFC ARIA. Its W3 schedule uses a mutable
second-byte latch:

```python
w3 = bytearray(FO(w2, C3))
for index in range(16):
    w3[index] = w1[index] ^ w3[1]
```

Index 1 overwrites the latch, so indices 2 through 15 consume the new value.
This behavior is present in the current Yonsei binary and the public
`1.0.0.36` binary. The deterministic official-binary test vector is recorded
in `tests/test_reportx_protocol_v1.py`.

After decryption:

```text
uint32-le clear length
→ strict CP949 command URL
→ "|" separators restored to "&"
→ duplicate-free query fields
```

Request-bearing fields are restricted to safe ASCII. Korean display-only
fields may remain CP949.

## URLFile and outer document

Current live tickets use:

```text
icert.yonsei.ac.kr/ys1.0/jsp/report/sendfile.jsp
```

For `SHOWREPORT` and `SHOWREPORT_PRINTAUTO`:

```text
GET https://{URLFile}?TPID={TPID}&MIN_NO={MINNO}&GIWAN_NO={GIWAN_NO}
```

The official client spells the transport `http://`; the clean-room broker
upgrades the exact allowlisted host/path to HTTPS. It follows no redirects,
uses no environment proxy, and bounds every response.

The non-PDF body has a second encrypted container:

```text
vendor ARIA-192-ECB
key = md5(MINNO).hexdigest().encode("ascii")[:24]
→ uint32-le compressed length + zlib bytes + zero cipher padding
→ zlib inflate
→ uint32-le primary length + FP3 bytes
→ uint32-le additional count
→ repeated uint32-le length + image bytes
```

The primary is FastReport prepared-report XML (`preparedreport`), not an FR3
design template. Additional components bind runtime pictures such as
`__2DBARCODE__`.

URLFile and URLCheck run through one in-memory cookie jar. This matches the
single WinINet session in ReportX and is required by the current Yonsei server.
The jar is discarded after one worker job.

## Runtime logo

`__LOGO1__` is not present in FP3, picturecache, or the outer components.
ReportX copies a `TImage.Picture` from the named RCDATA
`TREPORTVIEWERFORM`.

| Variant | Exact resource |
| --- | --- |
| landscape `ImgOnebon` | BMP 260×130×8, 33,894 bytes, SHA-256 `70e13e549af365b0c0c7cd0556e7458bb4278c67a98d8fa7f2e68675dbbb3a50` |
| portrait `ImgOnebon1` | BMP 130×260×8, 34,414 bytes, SHA-256 `e53ebaa130b33cdec70d2a9ad10f13960e8f114af1512f16f61527b234a83c9d` |

The landscape form is selected when `Height < Width`; otherwise the portrait
form is used. Ticket `Param_5 == "1"` sets the object width to zero and hides
it. Missing, empty, or `"0"` shows it; other values fail closed.

`prepare-assets` downloads or accepts the exact installer, verifies the outer
installer and `REPORTX.exe`, extracts both BMP ranges, validates each BMP
header/dimension/compression/hash, and stores them with private permissions.
No vendor bitmap is distributed in the plugin.

## Verification-number reservation

Before the GDI print call, ReportX requests:

```text
GET https://{URLCheck}
  ?MIN_NO={MINNO}
  &RECEIVE_TYPE={RECEIVE_TYPE}
  &RECEIVE_TARGET={RECEIVE_TARGET}
```

Current URLCheck is:

```text
icert.yonsei.ac.kr/ys1.0/jsp/report/senddocno.jsp
```

The body is a fixed 1,000-byte Windows buffer:

```text
16 ASCII alphanumeric document-number bytes + 984 NUL bytes
```

Only that exact shape, or an exact unpadded 16-byte form, is accepted. ReportX
formats the value as `xxxx-xxxx-xxxx-xxxx` and replaces `__SERIAL__` or its
page variants. The original ten-digit placeholder is rejected from final
output.

Despite using GET, URLCheck can allocate a document number. The agent:

1. validates FP3 placeholders and official assets locally;
2. writes a durable ticket-hash no-retry guard;
3. performs URLCheck once;
4. retains the value only in memory through PDF rendering;
5. records status/length/response shape, never the value or its digest.

A timeout, malformed response, or crash after step 2 is `unknown`; the same
ticket cannot be retried automatically.

## `__SEAL1__`, `__MARK__`, and print rules

The client has no asset-injection path for `__SEAL1__`; it only adjusts seal
geometry. It must not receive `__MARK__` or picturecache item zero.

An empty seal is accepted only for the observed source fingerprint:

- `TfrxPictureView`, `ImageIndex=0`, `Tag=3`;
- non-empty `TagStr`;
- a same-page resolved `__MARK__` with the same in-memory `TagStr`.

The `TagStr` value is never logged. Any other unresolved seal fails closed.

GDI printing excludes `Visible=False` and `Printable=False`. `PrintOnly=True`
objects are included in the print pass; this covers `__SERIAL__`,
`__LOGO1__`, and `__2DBARCODE__`. Object order remains the prepared-page
order. `ImageIndex` is one-based; zero is a runtime placeholder.

## PDF renderer and validation

The Windows binary has no working PDF exporter in this path. It prints
FastReport prepared pages to GDI. The independent renderer therefore:

- parses bounded FP3 XML without scripts, expressions, external files, or URLs;
- maps picturecache indices one-based;
- binds the external barcode, official runtime logo, serial text, and
  source-fingerprinted empty seal separately;
- embeds authorized local TrueType fonts;
- produces deterministic PDF 1.7 bytes;
- performs a second byte-for-byte replay in the agent.

The live validation covered a one-page Korean Yonsei certificate with nine
printable objects, three picturecache resources, one external barcode
component, the runtime logo, and the reserved verification number. Independent
`pdfinfo`, `pypdf`, and `pdftoppm` checks confirmed:

- one unencrypted A4 page;
- no JavaScript, form, open action, or embedded attachment;
- five image XObjects;
- one formatted verification number and no ten-digit placeholder;
- a nonblank raster with expected full-page, seal, footer-logo, and barcode
  regions.

No Windows GDI golden raster was available, so pixel-identical equivalence to
the vendor client is not claimed.

## Completion and physical printing boundary

After the synchronous FastReport print call returns, the Windows client sends:

```text
GET http://{URLPost}
  ?TPID={TPID}
  &SYSTEM_IP={local IPv4}
  &P_MODEL={printer model}
  &MIN_DOC_NO={same 16-character number}
  &RECEIVE_TYPE={RECEIVE_TYPE}
```

Current URLPost is `printcomplete.jsp`. The vendor ignores its response and
does not independently prove spool completion. The clean-room agent therefore
does not call URLPost after PDF rendering. CUPS submission remains an explicit,
digest-checked, one-attempt action, and completion acknowledgement is left
unimplemented rather than risking false consumption.

## Evidence boundary

The generated PDF is a compatibility rendering of data returned during the
user's authenticated issuance. Structural success does not prove Yonsei
original verification, digital-signature status, or acceptance by a receiving
institution. Use the official original-verification service for that separate
question.
