from __future__ import annotations

import hashlib
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = (
    ROOT
    / "plugins"
    / "yonsei-certificate-assistant"
    / "skills"
    / "yonsei-certificate-assistant"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

import reportx_runtime_profile as profile  # noqa: E402
from fp3_pdf import render_fp3_pdf  # noqa: E402


def _bmp8(width: int = 2, height: int = 1) -> bytes:
    palette = bytes((255, 255, 255, 0, 30, 20, 10, 0))
    stride = (width + 3) & ~3
    row = bytes((1,) * width) + b"\0" * (stride - width)
    pixels = row * height
    pixel_offset = 14 + 40 + len(palette)
    file_size = pixel_offset + len(pixels)
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
                len(pixels),
                2835,
                2835,
                2,
                0,
            ),
            palette,
            pixels,
        )
    )


def _runtime_fp3() -> bytes:
    mark = _bmp8()
    return f"""\
<preparedreport>
  <previewpages>
    <page0><mark ImageIndex="1"/><seal ImageIndex="0"/>
      <logo ImageIndex="0"/><serial/></page0>
  </previewpages>
  <sourcepages>
    <TfrxReportPage Name="Page" PaperWidth="210" PaperHeight="297">
      <TfrxPictureView Name="__MARK__" Left="80" Top="10"
        Width="40" Height="40" Tag="3" TagStr="same-proof"/>
      <TfrxPictureView Name="__SEAL1__" Left="130" Top="180"
        Width="25" Height="25" Tag="3" TagStr="same-proof"/>
      <TfrxPictureView Name="__LOGO1__" Left="10" Top="260"
        Width="20" Height="10" PrintOnly="True"/>
      <TfrxMemoView Name="__SERIAL__" Left="10" Top="10"
        Width="180" Height="10" PrintOnly="True" Font.Name="Arial"
        Text="[원본확인번호 : 0000000000]"/>
    </TfrxReportPage>
  </sourcepages>
  <dictionary>
    <mark name="Page0.__MARK__"/><seal name="Page0.__SEAL1__"/>
    <logo name="Page0.__LOGO1__"/><serial name="Page0.__SERIAL__"/>
  </dictionary>
  <picturecache><item stream="{mark.hex().upper()}"/></picturecache>
</preparedreport>
""".encode("utf-8")


class ReportXRuntimeProfileTests(unittest.TestCase):
    def test_runtime_bindings_materialize_logo_serial_and_proven_empty_seal(
        self,
    ) -> None:
        fp3 = _runtime_fp3()
        assets = profile.OfficialAssets(
            landscape=_bmp8(4, 2),
            portrait=_bmp8(2, 4),
        )
        with self.assertRaises(profile.DocumentNumberRequired):
            profile.build_runtime_bindings(fp3, assets)
        bindings = profile.build_runtime_bindings(
            fp3,
            assets,
            ("A1B2C3D4E5F6G7H8",),
        )
        self.assertEqual({"__LOGO1__"}, set(bindings.pictures))
        self.assertEqual(
            "[원본확인번호 : A1B2-C3D4-E5F6-G7H8]",
            bindings.text["__SERIAL__"],
        )
        self.assertEqual(
            frozenset({"__SEAL1__"}),
            bindings.official_empty_pictures,
        )
        rendered = render_fp3_pdf(
            fp3,
            runtime_pictures=bindings.pictures,
            runtime_text=bindings.text,
            official_empty_pictures=bindings.official_empty_pictures,
        )
        self.assertEqual(1, rendered.page_count)
        self.assertEqual(2, rendered.image_count)

    def test_param5_hide_policy_suppresses_only_the_runtime_logo(self) -> None:
        fp3 = _runtime_fp3()
        assets = profile.OfficialAssets(_bmp8(4, 2), _bmp8(2, 4))
        bindings = profile.build_runtime_bindings(
            fp3,
            assets,
            ("1234567890ABCDEF",),
            hide_logo=True,
        )
        self.assertEqual({}, bindings.pictures)
        self.assertEqual(
            frozenset({"__LOGO1__", "__SEAL1__"}),
            bindings.official_empty_pictures,
        )

    def test_pinned_outer_hash_and_inner_bmp_hash_are_both_required(self) -> None:
        first = _bmp8(4, 2)
        second = _bmp8(2, 4)
        blob = b"PREFIX" + first + b"GAP" + second + b"SUFFIX"
        layout = {
            "landscape": {
                "offset": len(b"PREFIX"),
                "length": len(first),
                "width": 4,
                "height": 2,
                "sha256": hashlib.sha256(first).hexdigest(),
            },
            "portrait": {
                "offset": len(b"PREFIX") + len(first) + len(b"GAP"),
                "length": len(second),
                "width": 2,
                "height": 4,
                "sha256": hashlib.sha256(second).hexdigest(),
            },
        }
        with (
            mock.patch.object(profile, "OFFICIAL_REPORTX_BYTES", len(blob)),
            mock.patch.object(
                profile,
                "OFFICIAL_REPORTX_SHA256",
                hashlib.sha256(blob).hexdigest(),
            ),
            mock.patch.object(profile, "_ASSET_LAYOUT", layout),
        ):
            assets = profile.extract_official_assets(blob)
            self.assertEqual(first, assets.landscape)
            self.assertEqual(second, assets.portrait)
            with self.assertRaises(profile.ReportXProfileError):
                profile.extract_official_assets(blob[:-1] + b"Y")


if __name__ == "__main__":
    unittest.main()
