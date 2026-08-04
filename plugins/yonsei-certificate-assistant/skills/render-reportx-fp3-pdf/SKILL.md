---
name: render-reportx-fp3-pdf
description: Render a decoded ReportX/FastReport VCL prepared-report FP3 XML stream into a local PDF on Windows, macOS, or Linux without native ReportX, a browser, or a physical printer. Use when a Yonsei icert ReportX response has already been decrypted into a primary FP3 component plus image components, when inspecting FP3 classes and resources, or when validating a compatibility PDF before an explicit print. Do not use to create or alter certificate content, render FR3 templates, bypass issuance, or claim that the PDF is an officially verified original.
---

# Render ReportX FP3 to PDF

This is the fine-grained renderer used by `yonsei-certificate-assistant`.
It accepts only already prepared pages. It never executes FastReport scripts,
evaluates expressions, loads external resources, calls a network service, or
submits a print job.

## Inspect first

```bash
python3 "$SKILL_DIR/scripts/fp3_pdf.py" inspect PRIMARY.fp3
```

Inspect reports the source digest, page/object counts, class inventory, and
picture-cache count. It does not print text or image content.

Stop if parsing reports an unknown object class, attribute contract, image
format, font, or ReportX placeholder mapping. Do not replace an unsupported
object with an empty box or rasterize arbitrary HTML as a fallback.

## Render

```bash
python3 "$SKILL_DIR/scripts/fp3_pdf.py" render PRIMARY.fp3 \
  --sidecar COMPONENT-1.bin \
  --output OUTPUT.pdf
```

Use one `--sidecar` per outer ReportX additional component, in response order.
For a standalone FP3 without a ReportX picture cache, a single zero-indexed
picture can consume a supplied sidecar. ReportX prepared pages use one-based
`ImageIndex` values for their XML `picturecache`; zero is reserved for
ReportX-managed placeholders such as `__2DBARCODE__`.

The standalone CLI deliberately cannot guess runtime-only certificate content.
For the Yonsei print profile, use `yonsei-certificate-assistant`; it supplies
strict named bindings for `__LOGO1__`, `__SERIAL__`, and a source-fingerprinted
empty `__SEAL1__`. An unresolved zero-indexed placeholder fails closed.

For an exact institutional face, map every FP3 `Font.Name` to the matching
authorized TrueType file. Do not collapse title and body into one fallback:

```bash
python3 "$SKILL_DIR/scripts/fp3_pdf.py" render PRIMARY.fp3 \
  --sidecar COMPONENT-1.bin \
  --font-map "YonseiB=/path/to/연세제목.TTF" \
  --font-map "연세제목체=/path/to/연세제목.TTF" \
  --font-map "YonseiL=/path/to/연세본문.TTF" \
  --font-map "연세본문체=/path/to/연세본문.TTF" \
  --output OUTPUT.pdf
```

The renderer validates TrueType embedding permissions and character coverage,
then records every embedded font hash in the result. The certificate workflow
uses its bundled authorized Yonsei faces for all text and rejects the result if
another font appears. Generic AppleGothic/Nanum fallback remains available only
for non-certificate FP3 inspection and must not be presented as original
typography.

The output and JSON manifest are written with private permissions. The status
is `rendered_pdf_unverified`: this means the prepared pages were rendered, not
that Yonsei or a receiving institution has verified the PDF.

## Verify before printing

Run both a structural reader and a rasterizer. For example:

```bash
pdfinfo OUTPUT.pdf
pdftoppm -f 1 -singlefile -r 144 -png OUTPUT.pdf PAGE
```

Check:

- page count and A4 geometry match the FP3;
- the complete certificate background is visible;
- transparent overlays do not cover the page;
- ReportX mark, serial/remark text, and 2D-barcode strip occupy their prepared
  boxes;
- there are no missing-glyph boxes, cropped text, blank images, or unexpected
  full-page logos.

Delete private raster previews after inspection. Do not paste certificate
content, ticket fields, or decoded image data into chat or logs.

## Supported contract

The renderer supports the bounded subset established by clean-room analysis
and a live user-authorized issuance:

- `preparedreport`, `previewpages`, `sourcepages`, `dictionary`,
  `picturecache`, and logical page metadata;
- prepared-page aliases and `l`, `t`, `w`, `h`, `u` deltas;
- bands, memo, view, line, shape, checkbox, and picture objects;
- one-based FastReport picture-cache references and the ReportX
  `__2DBARCODE__` additional-component binding;
- exact single-name or page/object-specific runtime picture/text bindings
  supplied by a caller-side profile resolver, with complete multiplicity
  checks for names repeated across prepared pages;
- strict mixed UTF-8/CP949 normalization only for ReportX `Font.Name` and
  `TagStr`;
- JPEG, non-interlaced 8-bit PNG, BI_RGB 8/24/32-bit BMP, indexed BMP
  palettes, transparent color keys, and alpha masks;
- embedded Unicode TrueType fonts, deterministic PDF object ordering, and
  byte-for-byte replay checks in the certificate agent.
- exact per-`Font.Name` mappings so distinct institutional title and body faces
  remain distinct PDF font resources.

Unknown drawable classes and unsupported visual semantics fail closed.
Read `references/fp3-format.md` before extending this contract.

## Validate changes

```bash
python3 -B -m unittest -v tests.test_fp3_pdf
python3 -B -m py_compile "$SKILL_DIR/scripts/fp3_pdf.py"
```

For changes to ReportX placeholder mapping or image composition, also repeat a
normal user-authorized issuance through `yonsei-certificate-assistant` and
raster-check the resulting compatibility PDF. A synthetic fixture alone is
not sufficient.
