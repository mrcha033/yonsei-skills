from __future__ import annotations

import hashlib
import sys
import unittest
import zlib
from pathlib import Path


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

from reportx_document_v1 import (  # noqa: E402
    MAX_ADDITIONAL_COMPONENTS,
    ReportXDocumentError,
    decode_reportx_document,
    decrypt_reportx_response,
    inflate_reportx_response,
    parse_reportx_document_frame,
    reportx_document_key,
)
from reportx_protocol_v1 import reportx_aria_encrypt_block  # noqa: E402


def document_frame(primary: bytes, additional: tuple[bytes, ...]) -> bytes:
    parts = [
        len(primary).to_bytes(4, "little"),
        primary,
        len(additional).to_bytes(4, "little"),
    ]
    for item in additional:
        parts.extend((len(item).to_bytes(4, "little"), item))
    return b"".join(parts)


def encrypted_response(
    primary: bytes,
    additional: tuple[bytes, ...],
    *,
    min_no: str,
) -> bytes:
    compressed = zlib.compress(document_frame(primary, additional))
    framed = len(compressed).to_bytes(4, "little") + compressed
    padded = framed + b"\0" * (-len(framed) % 16)
    key = reportx_document_key(min_no)
    return b"".join(
        reportx_aria_encrypt_block(padded[offset : offset + 16], key)
        for offset in range(0, len(padded), 16)
    )


class ReportXDocumentV1Tests(unittest.TestCase):
    def test_minno_key_is_lowercase_md5_hex_aria_192(self) -> None:
        expected = hashlib.md5(b"M-SYNTH").hexdigest().encode("ascii")[:24]
        key = reportx_document_key("M-SYNTH")
        self.assertEqual(expected, key)
        self.assertEqual(24, len(key))
        self.assertEqual(key.lower(), key)

    def test_synthetic_response_roundtrips_recovered_pipeline(self) -> None:
        primary = b"PRIMARY-REPORT-STREAM"
        additional = (b"PART-ONE", b"\x00\x01\x02PART-TWO")
        response = encrypted_response(primary, additional, min_no="M-SYNTH")
        bundle = decode_reportx_document(response, "M-SYNTH")
        self.assertEqual(primary, bundle.primary)
        self.assertEqual(additional, bundle.additional)
        self.assertEqual(3, bundle.component_count)
        self.assertEqual(hashlib.sha256(primary).hexdigest(), bundle.primary_sha256)

    def test_wrong_minno_and_non_block_response_fail_closed(self) -> None:
        response = encrypted_response(b"PRIMARY", (), min_no="RIGHT")
        with self.assertRaises(ReportXDocumentError):
            decode_reportx_document(response, "WRONG")
        with self.assertRaises(ReportXDocumentError):
            decode_reportx_document(response[:-1], "RIGHT")

    def test_decrypted_length_frame_and_cipher_padding_are_strict(self) -> None:
        compressed = zlib.compress(document_frame(b"PRIMARY", ()))
        framed = len(compressed).to_bytes(4, "little") + compressed
        key = reportx_document_key("M-SYNTH")

        def encrypt(cleartext: bytes) -> bytes:
            padded = cleartext + b"\0" * (-len(cleartext) % 16)
            return b"".join(
                reportx_aria_encrypt_block(padded[offset : offset + 16], key)
                for offset in range(0, len(padded), 16)
            )

        self.assertEqual(
            compressed,
            decrypt_reportx_response(encrypt(framed), "M-SYNTH"),
        )
        malformed = (
            (len(compressed) + 32).to_bytes(4, "little") + compressed,
            len(compressed).to_bytes(4, "little") + compressed + b"\x01",
            b"\0\0\0\0",
        )
        for cleartext in malformed:
            with self.subTest(cleartext=cleartext[:8]):
                with self.assertRaises(ReportXDocumentError):
                    decrypt_reportx_response(encrypt(cleartext), "M-SYNTH")

    def test_zlib_stream_rejects_truncation_and_trailing_data(self) -> None:
        compressed = zlib.compress(document_frame(b"PRIMARY", ()))
        self.assertEqual(
            document_frame(b"PRIMARY", ()),
            inflate_reportx_response(compressed),
        )
        for malformed in (compressed[:-1], compressed + b"\0"):
            with self.subTest(length=len(malformed)):
                with self.assertRaises(ReportXDocumentError):
                    inflate_reportx_response(malformed)

    def test_component_framing_rejects_truncation_trailing_and_count_bomb(self) -> None:
        valid = document_frame(b"PRIMARY", (b"PART",))
        for malformed in (
            valid[:-1],
            valid + b"X",
            len(b"PRIMARY").to_bytes(4, "little") + b"PRIMARY"
            + (MAX_ADDITIONAL_COMPONENTS + 1).to_bytes(4, "little"),
        ):
            with self.subTest(length=len(malformed)):
                with self.assertRaises(ReportXDocumentError):
                    parse_reportx_document_frame(malformed)


if __name__ == "__main__":
    unittest.main()
