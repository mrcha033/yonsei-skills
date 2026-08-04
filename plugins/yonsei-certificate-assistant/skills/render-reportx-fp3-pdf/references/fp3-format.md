# ReportX FP3 compatibility notes

## Evidence boundary

The input is a FastReport VCL prepared report, not an FR3 design template.
ReportX loads the decoded primary component through the prepared-page preview
loader and prints it through the GDI path. The compatibility renderer consumes
only the data already present in that prepared report.

The renderer must not:

- run `OnBeforePrint`, `OnAfterPrint`, or any FastScript expression;
- fetch a font, picture, URL, or linked object;
- invent content for a missing picture or font;
- treat successful PDF parsing as official-document verification.

## Container layout

The primary component is XML with this high-level shape:

```text
preparedreport
├── previewpages/pageN
├── sourcepages/TfrxReportPage
├── dictionary
├── picturecache/item[@stream]
└── logicalpagenumbers
```

Dictionary entries map short preview tags to named source-page objects.
Preview attributes are deltas over the source object. ReportX can emit
`Font.Name` and `TagStr` through a CP949 ANSI property inside an otherwise
UTF-8 XML document; only those two attributes receive strict repair.

## Picture mapping

`ImageIndex` in the prepared-page XML is one-based:

```text
1 → picturecache item 0
2 → picturecache item 1
3 → picturecache item 2
```

An index of zero is not picture-cache item zero. In the observed ReportX
profile it identifies a runtime-managed placeholder. The outer ReportX
additional component is bound in order to `__2DBARCODE__` zero-index
placeholders.

The remaining live Yonsei placeholders have distinct contracts:

- `__LOGO1__`: ReportX injects `ImgOnebon` (260×130) when width exceeds
  height, otherwise `ImgOnebon1` (130×260). The two bitmaps are extracted
  from the exact-hash official `REPORTX.exe`; they are not in FP3 or the outer
  response. Ticket `Param_5=1` suppresses the object.
- `__SERIAL__`: URLCheck supplies one 16-character document number, rendered
  as four groups of four. The literal ten-digit source placeholder must never
  reach PDF output.
- `__SEAL1__`: the client adjusts geometry but injects no image. It may remain
  empty only when the exact source fingerprint is present: zero index,
  `Tag=3`, non-empty `TagStr`, and a same-page resolved `__MARK__` with the
  same in-memory `TagStr`. Any other unresolved seal fails closed.

Runtime bindings preserve prepared-page identity. A single-occurrence legacy
binding may use an exact name, but repeated names use an exact
`(page_index, object_index, Name)` target for every occurrence. The complete
target set for that name must equal the objects in the prepared report; a
missing target, an unexpected extra occurrence, or a mismatched name fails
closed. This permits two pages to use different logo orientations or serial
templates without applying one page's value to the other. Binding values and
opaque `TagStr` metadata are never logged.

This distinction is visually load-bearing. Treating indices as zero-based
causes a full-page institutional mark to cover the certificate.

`Transparent=True` uses `TransparentColor`, with white as the ReportX default.
For DCT/JPEG streams the PDF image color-key mask preserves the compressed
image. PNG and BMP resources receive a bounded alpha mask.

## Prepared attribute contract

Attribute validation runs after the source object and preview delta are merged.
This matters when a preview value replaces a source value, such as the
observed `CharSpacing=-0.3` source becoming `CharSpacing=0` in the prepared
instance.

The renderer has class-specific allowlists for page, band, memo, picture,
line, shape, checkbox, and generic-view attributes. Boolean and integer values
are parsed strictly; unknown attributes and enum values fail closed.

The following observed properties are accepted only as prepared-page no-ops:

- `AllowExpressions=False` and `Wysiwyg=False`;
- `ParentFont=False` with a complete explicit font tuple;
- `AutoWidth=True` only for a single-line, non-wrapped, left-aligned,
  transparent memo whose rendered text already fits its prepared box;
- `Align=baCenter` only as the exact observed component enum; the live
  prepared coordinates were independently raster-checked;
- `OnBeforePrint` and `OnAfterPrint` only as bounded event identifiers. They
  are never invoked by the renderer.

`Printable=False` objects are excluded. `PrintOnly=True` objects are included
because this renderer has print intent.

## Units and page coordinates

FastReport prepared object coordinates are 96-DPI logical pixels and are
converted with:

```text
points = pixels × 72 / 96
```

Paper size and margins are millimeters:

```text
points = millimeters × 72 / 25.4
```

FastReport top-left coordinates are converted to the PDF bottom-left
coordinate system per page.

## Fail-closed extension process

For every new class or visual attribute:

1. capture only class/attribute names and non-sensitive geometry from a
   user-authorized prepared report;
2. locate the matching FastReport or ReportX draw behavior;
3. add a sanitized fixture that makes omission visibly detectable;
4. validate with an independent PDF parser and rasterizer;
5. compare the raster at object-box level;
6. keep the output `unverified` until official original verification is
   performed separately.
