from __future__ import annotations

import binascii
import io
import re
import struct
import sys
import unittest
import zlib
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = (
    ROOT
    / "plugins"
    / "yonsei-certificate-assistant"
    / "skills"
    / "render-reportx-fp3-pdf"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

import fp3_pdf  # noqa: E402
from fp3_pdf import (  # noqa: E402
    FP3RenderError,
    decode_image,
    parse_fp3,
    render_fp3_pdf,
    validate_pdf,
)


try:  # Optional independent validation; the project does not depend on pypdf.
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - depends on the developer environment.
    PdfReader = None


MINIMAL_FP3 = b"""\
<preparedreport>
  <previewpages>
    <page0>
      <b1 l="5" t="7" h="48">
        <m1 l="4" t="6" w="120" h="20" u="Prepared text"/>
      </b1>
    </page0>
  </previewpages>
  <sourcepages>
    <TfrxReportPage Name="ReportPage" PaperWidth="210" PaperHeight="297"
      LeftMargin="10" TopMargin="12">
      <TfrxReportTitle Name="Band1" Left="10" Top="20" Width="160" Height="40">
        <TfrxMemoView Name="Memo1" Left="2" Top="3" Width="100" Height="18"
          Text="source text" Font.Name="Fixture Sans" Font.Height="-16"
          WordWrap="1"/>
      </TfrxReportTitle>
    </TfrxReportPage>
  </sourcepages>
  <dictionary>
    <b1 name="Page0.Band1"/>
    <m1 name="Page0.Memo1"/>
  </dictionary>
</preparedreport>
"""


def _picture_fp3() -> bytes:
    return b"""\
<preparedreport>
  <previewpages>
    <page0><p1/></page0>
  </previewpages>
  <sourcepages>
    <TfrxReportPage Name="ReportPage" PaperWidth="210" PaperHeight="297">
      <TfrxPictureView Name="Picture1" Left="12" Top="18" Width="48" Height="30"
        ImageIndex="0" Color="255" Transparent="0"
        Frame.Typ="15" Frame.Width="1" Frame.Color="0"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary><p1 name="Page0.Picture1"/></dictionary>
</preparedreport>
"""


def _two_memo_fp3() -> bytes:
    return """\
<preparedreport>
  <previewpages>
    <page0>
      <b1>
        <m1 u="ASCII first"/>
        <m2 u="연세"/>
      </b1>
    </page0>
  </previewpages>
  <sourcepages>
    <TfrxReportPage Name="ReportPage" PaperWidth="210" PaperHeight="297">
      <TfrxReportTitle Name="Band1" Left="0" Top="0" Width="300" Height="100">
        <TfrxMemoView Name="Memo1" Left="0" Top="0" Width="150" Height="30"
          Font.Name="Tahoma" Font.Height="-16"/>
        <TfrxMemoView Name="Memo2" Left="0" Top="32" Width="150" Height="30"
          Font.Name="Tahoma" Font.Height="-16"/>
      </TfrxReportTitle>
    </TfrxReportPage>
  </sourcepages>
  <dictionary>
    <b1 name="Page0.Band1"/>
    <m1 name="Page0.Memo1"/>
    <m2 name="Page0.Memo2"/>
  </dictionary>
</preparedreport>
""".encode("utf-8")


def _unknown_class_fp3() -> bytes:
    return b"""\
<preparedreport>
  <previewpages><page0><r1/></page0></previewpages>
  <sourcepages>
    <TfrxReportPage Name="ReportPage" PaperWidth="210" PaperHeight="297">
      <TfrxRichView Name="Rich1" Left="0" Top="0" Width="10" Height="10"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary><r1 name="Page0.Rich1"/></dictionary>
</preparedreport>
"""


def _reportx_profile_fp3() -> bytes:
    cache = (_rgb_png(), _bmp24(), _bmp8())
    items = "".join(
        f'<item stream="{value.hex().upper()}"/>'
        for value in cache
    )
    return f"""\
<preparedreport>
  <previewpages>
    <page0>
      <p1 ImageIndex="1"/><p2 ImageIndex="2"/><p3 ImageIndex="3"/>
      <seal ImageIndex="0"/><logo ImageIndex="0"/>
      <barcode ImageIndex="0"/><hidden u="do not paint"/>
      <memo u="spaced"/>
    </page0>
  </previewpages>
  <sourcepages>
    <TfrxReportPage Name="Page" PaperWidth="210" PaperHeight="297">
      <TfrxPictureView Name="__BACK__" Left="0" Top="0"
        Width="200" Height="250" Transparent="True"
        KeepAspectRatio="False" Center="True"/>
      <TfrxPictureView Name="Picture1" Left="5" Top="5"
        Width="190" Height="240" Transparent="True" Center="True"/>
      <TfrxPictureView Name="__MARK__" Left="80" Top="8"
        Width="40" Height="40" Transparent="True" Center="True"/>
      <TfrxPictureView Name="__SEAL1__" Left="130" Top="180"
        Width="25" Height="25"/>
      <TfrxPictureView Name="__LOGO1__" Left="10" Top="260"
        Width="20" Height="10" PrintOnly="True"/>
      <TfrxPictureView Name="__2DBARCODE__" Left="35" Top="260"
        Width="160" Height="10" PrintOnly="True"/>
      <TfrxMemoView Name="Hidden" Left="0" Top="0" Width="20"
        Height="10" Printable="False"/>
      <TfrxMemoView Name="Memo" Left="10" Top="250" Width="180"
        Height="10" Font.Name="Arial" CharSpacing="-0.3"
        WordWrap="False"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary>
    <p1 name="Page0.__BACK__"/><p2 name="Page0.Picture1"/>
    <p3 name="Page0.__MARK__"/><seal name="Page0.__SEAL1__"/>
    <logo name="Page0.__LOGO1__"/>
    <barcode name="Page0.__2DBARCODE__"/>
    <hidden name="Page0.Hidden"/><memo name="Page0.Memo"/>
  </dictionary>
  <picturecache>{items}</picturecache>
</preparedreport>
""".encode("utf-8")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big")
        + kind
        + payload
        + (binascii.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def _png(
    width: int,
    height: int,
    color_type: int,
    scanlines: bytes,
    *,
    chunks_before_idat: tuple[tuple[bytes, bytes], ...] = (),
) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", ihdr),
            *(
                _png_chunk(kind, payload)
                for kind, payload in chunks_before_idat
            ),
            _png_chunk(b"IDAT", zlib.compress(scanlines, 9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _rgb_png() -> bytes:
    # One unfiltered scanline containing two RGB pixels.
    return _png(2, 1, 2, b"\x00\xff\x00\x00\x00\x00\xff")


def _bmp24() -> bytes:
    width = 1
    height = 1
    row = b"\x1e\x14\x0a\x00"  # BGR=(30,20,10), padded to four bytes.
    header_size = 54
    file_size = header_size + len(row)
    return b"".join(
        (
            struct.pack("<2sIHHI", b"BM", file_size, 0, 0, header_size),
            struct.pack(
                "<IiiHHIIiiII",
                40,
                width,
                height,
                1,
                24,
                0,
                len(row),
                2835,
                2835,
                0,
                0,
            ),
            row,
        )
    )


def _bmp32() -> bytes:
    width = 2
    height = 1
    # Bottom-up BGRA: (R,G,B,A)=(10,20,30,40), then (40,50,60,255).
    row = bytes((30, 20, 10, 40, 60, 50, 40, 255))
    header_size = 54
    file_size = header_size + len(row)
    return b"".join(
        (
            struct.pack("<2sIHHI", b"BM", file_size, 0, 0, header_size),
            struct.pack(
                "<IiiHHIIiiII",
                40,
                width,
                height,
                1,
                32,
                0,
                len(row),
                2835,
                2835,
                0,
                0,
            ),
            row,
        )
    )


def _bmp8() -> bytes:
    width = 2
    height = 1
    palette = bytes(
        (
            30, 20, 10, 0,
            60, 50, 40, 0,
        )
    )
    row = b"\x00\x01\x00\x00"
    pixel_offset = 14 + 40 + len(palette)
    file_size = pixel_offset + len(row)
    return b"".join(
        (
            struct.pack("<2sIHHI", b"BM", file_size, 0, 0, pixel_offset),
            struct.pack(
                "<IiiHHIIiiII",
                40,
                width,
                height,
                1,
                8,
                0,
                len(row),
                2835,
                2835,
                2,
                0,
            ),
            palette,
            row,
        )
    )


def _pdf_objects(pdf: bytes) -> dict[int, bytes]:
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(
            rb"(?m)^([0-9]+) 0 obj\n(.*?)\nendobj\n",
            pdf,
            flags=re.DOTALL,
        )
    }


def _page_content(pdf: bytes) -> tuple[bytes, bytes]:
    objects = _pdf_objects(pdf)
    page_body = next(
        body
        for body in objects.values()
        if b"/Type /Page " in body
    )
    match = re.search(rb"/Contents ([0-9]+) 0 R", page_body)
    if match is None:
        raise AssertionError("page has no content reference")
    stream_body = objects[int(match.group(1))]
    dictionary, remainder = stream_body.split(b"\nstream\n", 1)
    payload, end = remainder.rsplit(b"\nendstream", 1)
    if end:
        raise AssertionError("unexpected bytes after page stream")
    if b"/Filter /FlateDecode" in dictionary:
        payload = zlib.decompress(payload)
    return page_body, payload


def _assert_balanced_pdf_dictionary(
    test: unittest.TestCase,
    dictionary: bytes,
) -> None:
    depth = 0
    for token in re.findall(rb"<<|>>", dictionary):
        depth += 1 if token == b"<<" else -1
        test.assertGreaterEqual(depth, 0, dictionary)
    test.assertEqual(0, depth, dictionary)


class FP3PDFTests(unittest.TestCase):
    def test_reportx_profile_uses_one_based_cache_and_barcode_sidecar(self) -> None:
        source = _reportx_profile_fp3()
        model = parse_fp3(source)
        self.assertEqual(3, len(model.picture_cache))
        self.assertEqual(7, len(model.pages[0].objects))
        logo = bytearray(_bmp8())
        logo[-4:] = b"\x01\x00\x00\x00"
        rendered = render_fp3_pdf(
            source,
            (_bmp8(),),
            runtime_pictures={"__LOGO1__": bytes(logo)},
            official_empty_pictures=frozenset({"__SEAL1__"}),
        )
        self.assertEqual(5, rendered.image_count)
        self.assertEqual(7, rendered.object_count)
        _, content = _page_content(rendered.pdf)
        self.assertEqual(5, len(re.findall(rb"/Im[0-9]+ Do", content)))
        self.assertIn(b"-0.225 Tc", content)
        self.assertNotIn(b"do not paint", content)

    def test_reportx_ansi_font_and_tag_attributes_are_normalized(self) -> None:
        mixed = MINIMAL_FP3.replace(
            b'Font.Name="Fixture Sans"',
            b'Font.Name="' + "바탕체".encode("cp949") + b'"',
        ).replace(
            b'WordWrap="1"',
            b'WordWrap="1" TagStr="' + "발급 문서".encode("cp949") + b'"',
        )
        model = parse_fp3(mixed)
        self.assertEqual("바탕체", model.pages[0].objects[0].attrs["Font.Name"])
        self.assertEqual("발급 문서", model.pages[0].objects[0].attrs["TagStr"])

    def test_invalid_bytes_outside_legacy_attributes_fail_closed(self) -> None:
        malformed = MINIMAL_FP3.replace(
            b'Text="source text"',
            b'Text="' + "문서".encode("cp949") + b'"',
        )
        with self.assertRaisesRegex(
            FP3RenderError,
            "invalid UTF-8 outside supported ANSI attributes",
        ):
            parse_fp3(malformed)

    def test_vcl_alias_source_dictionary_parse_and_render(self) -> None:
        model = parse_fp3(MINIMAL_FP3)
        self.assertEqual(1, len(model.pages))
        self.assertEqual(
            (("TfrxMemoView", 1), ("TfrxReportTitle", 1)),
            model.class_inventory,
        )
        page = model.pages[0]
        self.assertAlmostEqual(210 * fp3_pdf.MM_TO_PT, page.width_pt)
        self.assertAlmostEqual(297 * fp3_pdf.MM_TO_PT, page.height_pt)
        self.assertAlmostEqual(10 * fp3_pdf.MM_TO_PT, page.margin_left_pt)
        self.assertAlmostEqual(12 * fp3_pdf.MM_TO_PT, page.margin_top_pt)
        self.assertEqual(1, len(page.objects))
        memo = page.objects[0]
        self.assertEqual("TfrxMemoView", memo.class_name)
        self.assertEqual((9.0, 13.0, 120.0, 20.0), (
            memo.x,
            memo.y,
            memo.width,
            memo.height,
        ))
        self.assertEqual("Prepared text", memo.text)

        no_local_fonts = {"korean-fallback": ()}
        with mock.patch.object(
            fp3_pdf,
            "_FONT_CANDIDATES",
            no_local_fonts,
        ):
            rendered = render_fp3_pdf(MINIMAL_FP3)
        validate_pdf(rendered.pdf)
        self.assertEqual(1, rendered.page_count)
        self.assertEqual(1, rendered.object_count)
        self.assertEqual(0, rendered.image_count)
        self.assertTrue(rendered.pdf.startswith(b"%PDF-1.7\n"))
        self.assertTrue(rendered.pdf.endswith(b"%%EOF\n"))

    def test_nonprintable_prepared_object_is_excluded(self) -> None:
        source = MINIMAL_FP3.replace(
            b'WordWrap="1"',
            b'WordWrap="1" Printable="False"',
        )
        model = parse_fp3(source)
        self.assertEqual(0, len(model.pages[0].objects))
        self.assertEqual(1, model.excluded_nonprintable_count)

    def test_render_is_byte_for_byte_deterministic(self) -> None:
        no_local_fonts = {"korean-fallback": ()}
        with mock.patch.object(
            fp3_pdf,
            "_FONT_CANDIDATES",
            no_local_fonts,
        ):
            first = render_fp3_pdf(MINIMAL_FP3)
            second = render_fp3_pdf(MINIMAL_FP3)
        self.assertEqual(first.pdf, second.pdf)
        self.assertEqual(first.pdf_sha256, second.pdf_sha256)
        self.assertEqual(first.manifest(), second.manifest())

    def test_multiple_memo_font_resources_are_not_dropped(self) -> None:
        tahoma = Path("/System/Library/Fonts/Supplemental/Tahoma.ttf")
        korean = Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf")
        if not tahoma.is_file() or not korean.is_file():
            self.skipTest("Tahoma and AppleGothic regression fonts unavailable")
        tahoma_face = fp3_pdf.TrueTypeFont(tahoma)
        korean_face = fp3_pdf.TrueTypeFont(korean)
        if tahoma_face.supports("연세") or not korean_face.supports("연세"):
            self.skipTest("local fonts do not expose the resource-split case")
        candidates = {
            "tahoma": (str(tahoma),),
            "korean-fallback": (str(korean),),
        }
        with mock.patch.object(fp3_pdf, "_FONT_CANDIDATES", candidates):
            rendered = render_fp3_pdf(_two_memo_fp3())
        page_body, content = _page_content(rendered.pdf)
        resources = re.search(rb"/Font <<(.*?)>>", page_body, re.DOTALL)
        self.assertIsNotNone(resources)
        assert resources is not None
        self.assertIn(b"/F1 ", resources.group(1))
        self.assertIn(b"/F2 ", resources.group(1))
        self.assertIn(b"/F1 ", content)
        self.assertIn(b"/F2 ", content)
        self.assertEqual(2, len(rendered.font_files))

    def test_korean_serif_aliases_share_one_embedded_face(self) -> None:
        serif = Path("/System/Library/Fonts/Supplemental/AppleMyungjo.ttf")
        if not serif.is_file():
            self.skipTest("AppleMyungjo regression font unavailable")
        source = _two_memo_fp3().replace(
            b'Font.Name="Tahoma"',
            'Font.Name="바탕"'.encode("utf-8"),
            1,
        ).replace(
            b'Font.Name="Tahoma"',
            'Font.Name="바탕체"'.encode("utf-8"),
            1,
        )
        rendered = render_fp3_pdf(source)
        page_body, content = _page_content(rendered.pdf)
        resources = re.search(rb"/Font <<(.*?)>>", page_body, re.DOTALL)
        self.assertIsNotNone(resources)
        assert resources is not None
        self.assertIn(b"/F1 ", resources.group(1))
        self.assertNotIn(b"/F2 ", resources.group(1))
        self.assertIn(b"/F1 ", content)
        self.assertEqual(1, len(rendered.font_files))

    def test_png_decode_parms_remains_a_nested_pdf_dictionary(self) -> None:
        rendered = render_fp3_pdf(_picture_fp3(), (_rgb_png(),))
        image_body = next(
            body
            for body in _pdf_objects(rendered.pdf).values()
            if b"/Subtype /Image" in body and b"/DecodeParms" in body
        )
        dictionary = image_body.split(b"\nstream\n", 1)[0]
        _assert_balanced_pdf_dictionary(self, dictionary)
        self.assertRegex(
            dictionary,
            rb"/DecodeParms << /Predictor 15 /Colors 3 "
            rb"/BitsPerComponent 8 /Columns 2 >> "
            rb"/Interpolate false /Length [0-9]+",
        )

    def test_picture_fill_image_and_frame_paint_in_visual_order(self) -> None:
        rendered = render_fp3_pdf(_picture_fp3(), (_bmp24(),))
        _, content = _page_content(rendered.pdf)
        fill = content.find(b" re f Q\n")
        image = content.find(b"/Im1 Do")
        frame = content.find(b" RG ", image + 1)
        self.assertGreaterEqual(fill, 0, content)
        self.assertGreaterEqual(image, 0, content)
        self.assertGreaterEqual(frame, 0, content)
        self.assertLess(fill, image, content)
        self.assertLess(image, frame, content)

    def test_picture_defaults_keep_aspect_without_implicit_centering(self) -> None:
        rendered = render_fp3_pdf(_picture_fp3(), (_bmp24(),))
        _, content = _page_content(rendered.pdf)
        # 48x30 logical pixels become a 36x22.5-point frame. The default
        # KeepAspectRatio=True draws the square at 22.5 points, and the
        # default Center=False retains the frame's left edge at 9 points.
        self.assertIn(b"22.5 0 0 22.5 9 ", content)
        image_body = next(
            body
            for body in _pdf_objects(rendered.pdf).values()
            if b"/Subtype /Image" in body and b"/ColorSpace /DeviceRGB" in body
        )
        self.assertIn(b"/Interpolate false", image_body)

        high_quality = _picture_fp3().replace(
            b' ImageIndex="0"',
            b' ImageIndex="0" HightQuality="True"',
        )
        rendered_high = render_fp3_pdf(high_quality, (_bmp24(),))
        high_image = next(
            body
            for body in _pdf_objects(rendered_high.pdf).values()
            if b"/Subtype /Image" in body and b"/ColorSpace /DeviceRGB" in body
        )
        self.assertIn(b"/Interpolate true", high_image)

        wide = render_fp3_pdf(_picture_fp3(), (_rgb_png(),))
        _, wide_content = _page_content(wide.pdf)
        matrix = re.search(
            rb"36 0 0 18 9 ([0-9.]+) cm /Im1 Do",
            wide_content,
        )
        self.assertIsNotNone(matrix)
        assert matrix is not None
        frame_bottom = (
            297 * fp3_pdf.MM_TO_PT
            - 18 * fp3_pdf.PX_TO_PT
            - 30 * fp3_pdf.PX_TO_PT
        )
        self.assertAlmostEqual(
            frame_bottom + 4.5,
            float(matrix.group(1)),
            places=5,
        )

    def test_indexed_bmp_palette_and_bottom_up_rows_are_preserved(self) -> None:
        image = decode_image(_bmp8())
        self.assertEqual(2, image.width)
        self.assertEqual(1, image.height)
        self.assertEqual(
            b"[/Indexed /DeviceRGB 1 <0A141E28323C>]",
            image.colorspace,
        )
        self.assertEqual(b"\x00\x01", zlib.decompress(image.data))
        keyed = decode_image(
            _bmp8(),
            transparent_color=(40, 50, 60),
        )
        self.assertIsNotNone(keyed.alpha)
        assert keyed.alpha is not None
        self.assertEqual(b"\xff\x00", zlib.decompress(keyed.alpha))

    def test_dtd_and_entities_are_rejected_when_padded_or_utf16(self) -> None:
        entity_document = MINIMAL_FP3.replace(
            b"<preparedreport>",
            b'<!DOCTYPE preparedreport [<!ENTITY payload "boom">]>'
            b"<preparedreport>",
            1,
        ).replace(b"Prepared text", b"&payload;", 1)
        cases = {
            "ordinary": entity_document,
            "past_probe_window": b" " * 5000 + entity_document,
            "utf16_le": b"\xff\xfe"
            + entity_document.decode("utf-8").encode("utf-16-le"),
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    FP3RenderError,
                    "DTD|entities",
                ):
                    parse_fp3(data)

    def test_bmp32_reserved_byte_is_not_mistaken_for_alpha(self) -> None:
        image = decode_image(_bmp32())
        self.assertEqual((2, 1, b"/DeviceRGB", 8), (
            image.width,
            image.height,
            image.colorspace,
            image.bits,
        ))
        self.assertEqual(
            bytes((10, 20, 30, 40, 50, 60)),
            zlib.decompress(image.data),
        )
        # BI_RGB's fourth byte is reserved.  Treating it as alpha would make
        # otherwise ordinary 32-bit Windows bitmaps unexpectedly transparent.
        self.assertIsNone(image.alpha)

    def test_bmp32_explicit_alpha_bitfields_fail_closed_until_supported(
        self,
    ) -> None:
        bitfields = bytearray(_bmp32())
        bitfields[30:34] = (3).to_bytes(4, "little")  # BI_BITFIELDS
        with self.assertRaises(FP3RenderError):
            decode_image(bytes(bitfields))

    def test_png_trns_is_not_silently_discarded(self) -> None:
        transparent_rgb = _png(
            1,
            1,
            2,
            b"\x00\x01\x02\x03",
            chunks_before_idat=((b"tRNS", b"\x00\x01\x00\x02\x00\x03"),),
        )
        with self.assertRaises(FP3RenderError):
            decode_image(transparent_rgb)

    def test_png_pixel_limit_and_scanline_size_fail_closed(self) -> None:
        oversized = _png(
            fp3_pdf.MAX_IMAGE_PIXELS + 1,
            1,
            2,
            b"\x00",
        )
        wrong_scanline = _png(2, 1, 2, b"\x00\x01\x02\x03")
        for label, data in (
            ("pixel_limit", oversized),
            ("scanline_size", wrong_scanline),
        ):
            with self.subTest(label=label):
                with self.assertRaises(FP3RenderError):
                    decode_image(data)

    def test_unknown_drawable_class_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            FP3RenderError,
            "unsupported FP3 object class TfrxRichView",
        ):
            parse_fp3(_unknown_class_fp3())

    def test_unknown_attributes_and_ambiguous_values_fail_closed(self) -> None:
        cases = (
            (
                "unknown_visual_attribute",
                MINIMAL_FP3.replace(
                    b'WordWrap="1"',
                    b'WordWrap="1" DropShadow="True"',
                ),
            ),
            (
                "invalid_boolean",
                MINIMAL_FP3.replace(
                    b'WordWrap="1"',
                    b'WordWrap="sometimes"',
                ),
            ),
            (
                "fractional_integer",
                _picture_fp3().replace(
                    b'Frame.Typ="15"',
                    b'Frame.Typ="1.5"',
                ),
            ),
            (
                "duplicate_section",
                MINIMAL_FP3.replace(
                    b"</preparedreport>",
                    b"<dictionary/></preparedreport>",
                ),
            ),
        )
        for label, data in cases:
            with self.subTest(label=label):
                with self.assertRaises(FP3RenderError):
                    parse_fp3(data)

    @unittest.skipUnless(PdfReader is not None, "pypdf is not installed")
    def test_optional_strict_pypdf_parse(self) -> None:
        rendered = render_fp3_pdf(_picture_fp3(), (_rgb_png(),))
        assert PdfReader is not None
        reader = PdfReader(io.BytesIO(rendered.pdf), strict=True)
        self.assertEqual(1, len(reader.pages))
        page = reader.pages[0]
        self.assertAlmostEqual(
            210 * fp3_pdf.MM_TO_PT,
            float(page.mediabox.width),
            delta=1e-5,
        )
        self.assertAlmostEqual(
            297 * fp3_pdf.MM_TO_PT,
            float(page.mediabox.height),
            delta=1e-5,
        )


if __name__ == "__main__":
    unittest.main()
