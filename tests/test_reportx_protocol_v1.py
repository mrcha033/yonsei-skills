from __future__ import annotations

import base64
import hashlib
import sys
import unittest
import urllib.parse
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

from reportx_protocol import (  # noqa: E402
    AcceptServerResponse,
    BrokerPolicy,
    NetworkResponse,
    ProtocolBroker,
    RequestAction,
    SessionContext,
    TicketEnvelope,
)
from reportx_protocol_v1 import (  # noqa: E402
    ReportXProtocolV1Decoder,
    TicketDecodeError,
    _reportx_key,
    aria_decrypt_block,
    aria_encrypt_block,
    build_document_number_action,
    parse_document_number_response,
    parse_reportx_ticket,
    reportx_aria_decrypt_block,
    reportx_aria_encrypt_block,
)


RFC_PLAINTEXT = bytes.fromhex("00112233445566778899aabbccddeeff")
RFC_VECTORS = (
    (
        "000102030405060708090a0b0c0d0e0f",
        "d718fbd6ab644c739da95f3be6451778",
    ),
    (
        "000102030405060708090a0b0c0d0e0f1011121314151617",
        "26449c1805dbe7aa25a468ce263a9e79",
    ),
    (
        "000102030405060708090a0b0c0d0e0f"
        "101112131415161718191a1b1c1d1e1f",
        "f92bd7c79fb72e2f2b8f80c1972d24fc",
    ),
)
CLEAR_URL = (
    "http://fixture.invalid/SHOWREPORT_PRINTAUTO?"
    "URLFile=uni.webminwon.com/servlet/WMINDEX"
    "|URLPost=post.invalid/print-completion"
    "|TPID=T-SYNTH"
    "|MINNO=M-SYNTH"
    "|GIWAN_NO=000000"
    "|Printable=1"
)
EXPECTED_REQUEST = (
    "https://uni.webminwon.com/servlet/WMINDEX?"
    "TPID=T-SYNTH&MIN_NO=M-SYNTH&GIWAN_NO=000000"
)


def encrypted_ticket(clear: bytes) -> TicketEnvelope:
    framed = len(clear).to_bytes(4, "little") + clear
    framed += b"\0" * (-len(framed) % 16)
    ciphertext = b"".join(
        reportx_aria_encrypt_block(
            framed[offset : offset + 16],
            _reportx_key(),
        )
        for offset in range(0, len(framed), 16)
    )
    return TicketEnvelope.parse(
        "dzreportx:" + base64.b64encode(ciphertext).decode("ascii")
    )


class ReportXProtocolV1Tests(unittest.TestCase):
    def _reservation_ticket(self):
        clear = (
            "http://fixture.invalid/SHOWREPORT?"
            "URLFile=icert.yonsei.ac.kr/ys1.0/jsp/report/sendfile.jsp"
            "|URLCheck=icert.yonsei.ac.kr/ys1.0/jsp/report/senddocno.jsp"
            "|URLPost=icert.yonsei.ac.kr/ys1.0/jsp/report/printcomplete.jsp"
            "|TPID=T-SYNTH|MINNO=M-SYNTH|GIWAN_NO=000000"
            "|Copies=1|RECEIVE_TYPE=WEB|RECEIVE_TARGET="
        )
        return parse_reportx_ticket(
            TicketEnvelope.parse("dzreportx:||" + clear)
        )

    def test_rfc_5794_vectors_cover_all_key_sizes(self) -> None:
        for key_hex, ciphertext_hex in RFC_VECTORS:
            with self.subTest(key_bits=len(key_hex) * 4):
                key = bytes.fromhex(key_hex)
                ciphertext = bytes.fromhex(ciphertext_hex)
                self.assertEqual(
                    ciphertext,
                    aria_encrypt_block(RFC_PLAINTEXT, key),
                )
                self.assertEqual(
                    RFC_PLAINTEXT,
                    aria_decrypt_block(ciphertext, key),
                )

    def test_reverse_engineered_reportx_key_is_lowercase_aria_192(self) -> None:
        expected = hashlib.md5(b"10001").hexdigest().encode("ascii")[:24]
        self.assertEqual(b"d89f3a35931c386956c1a402", expected)
        self.assertEqual(expected, _reportx_key())

    def test_vendor_key_schedule_matches_official_reportx_vector(self) -> None:
        # Non-sensitive deterministic vector executed directly against
        # REPORTX.exe 1.0.0.36 and the Yonsei package 1.0.0.29 binary.
        ciphertext = bytes.fromhex("c716c04bff77bb4c2f5559dfc2c268e5")
        self.assertEqual(
            ciphertext,
            reportx_aria_encrypt_block(
                RFC_PLAINTEXT,
                b"d89f3a35931c386956c1a402",
            ),
        )
        self.assertEqual(
            RFC_PLAINTEXT,
            reportx_aria_decrypt_block(
                ciphertext,
                b"d89f3a35931c386956c1a402",
            ),
        )

    def test_plaintext_diagnostic_ticket_parses_without_crypto(self) -> None:
        ticket = TicketEnvelope.parse("dzreportx:||" + CLEAR_URL)
        parsed = parse_reportx_ticket(ticket)
        self.assertFalse(parsed.encrypted)
        self.assertEqual("SHOWREPORT_PRINTAUTO", parsed.command)
        self.assertEqual(EXPECTED_REQUEST, parsed.request_url)
        self.assertEqual("M-SYNTH", parsed.get("MINNO"))

    def test_report_fetch_uses_urlfile_and_ignores_urlpost(self) -> None:
        ticket = TicketEnvelope.parse("dzreportx:||" + CLEAR_URL)
        parsed = parse_reportx_ticket(ticket)
        self.assertEqual(
            "uni.webminwon.com/servlet/WMINDEX",
            parsed.get("URLFile"),
        )
        self.assertEqual("post.invalid/print-completion", parsed.get("URLPost"))
        self.assertEqual(EXPECTED_REQUEST, parsed.request_url)
        self.assertNotIn("post.invalid", parsed.request_url)

    def test_synthetic_encrypted_frame_roundtrips(self) -> None:
        parsed = parse_reportx_ticket(encrypted_ticket(CLEAR_URL.encode("ascii")))
        self.assertTrue(parsed.encrypted)
        self.assertEqual(EXPECTED_REQUEST, parsed.request_url)

    def test_cp949_display_field_does_not_change_request_fields(self) -> None:
        clear = (CLEAR_URL + "|DISPLAY=재학증명서").encode("cp949")
        parsed = parse_reportx_ticket(encrypted_ticket(clear))
        self.assertEqual(EXPECTED_REQUEST, parsed.request_url)
        self.assertEqual("재학증명서", parsed.get("DISPLAY"))

    def test_current_yonsei_sendfile_endpoint_is_allowlisted_exactly(self) -> None:
        clear = CLEAR_URL.replace(
            "uni.webminwon.com/servlet/WMINDEX",
            "icert.yonsei.ac.kr/ys1.0/jsp/report/sendfile.jsp",
        )
        parsed = parse_reportx_ticket(
            encrypted_ticket(clear.encode("ascii"))
        )
        self.assertEqual(
            "icert.yonsei.ac.kr",
            urllib.parse.urlsplit(parsed.request_url).hostname,
        )

    def test_document_number_reservation_action_is_exact_and_one_copy(self) -> None:
        action = build_document_number_action(self._reservation_ticket())
        self.assertEqual("GET", action.method)
        self.assertEqual("reportx-document-number", action.request_id)
        parsed = urllib.parse.urlsplit(action.url)
        self.assertEqual("https", parsed.scheme)
        self.assertEqual("icert.yonsei.ac.kr", parsed.hostname)
        self.assertEqual(
            "/ys1.0/jsp/report/senddocno.jsp",
            parsed.path,
        )
        self.assertEqual(
            {
                "MIN_NO": ["M-SYNTH"],
                "RECEIVE_TYPE": ["WEB"],
                "RECEIVE_TARGET": [""],
            },
            urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
        )

    def test_document_number_response_is_exactly_one_16_char_value(self) -> None:
        action = build_document_number_action(self._reservation_ticket())
        response = NetworkResponse.from_bytes(
            request_id=action.request_id,
            url=action.url,
            status=200,
            headers=(("Content-Type", "text/plain"),),
            body=b"A1B2C3D4E5F6G7H8",
        )
        self.assertEqual(
            "A1B2C3D4E5F6G7H8",
            parse_document_number_response(response),
        )
        self.assertEqual(
            "A1B2C3D4E5F6G7H8",
            parse_document_number_response(
                NetworkResponse.from_bytes(
                    request_id=action.request_id,
                    url=action.url,
                    status=200,
                    headers=(),
                    body=b"A1B2C3D4E5F6G7H8" + b"\0" * 984,
                )
            ),
        )
        for body in (
            b"short",
            b"Bad request",
            b"<html>error</html>",
            b"A" * 17,
            b"A1B2C3D4E5F6G7H8" + b"\0" * 2,
            b"A1B2C3D4E5F6G7H8" + b"\0" * 985,
        ):
            with self.subTest(body=body):
                with self.assertRaises(TicketDecodeError):
                    parse_document_number_response(
                        NetworkResponse.from_bytes(
                            request_id=action.request_id,
                            url=action.url,
                            status=200,
                            headers=(),
                            body=body,
                        )
                    )
        with self.assertRaises(TicketDecodeError):
            parse_document_number_response(
                NetworkResponse.from_bytes(
                    request_id=action.request_id,
                    url=action.url,
                    status=200,
                    headers=(),
                    body=b"A1B2C3D4E5F6G7H8\0\0X",
                )
            )

    def test_urlfile_and_command_are_fail_closed(self) -> None:
        cross_host = CLEAR_URL.replace(
            "URLFile=uni.webminwon.com/servlet/WMINDEX",
            "URLFile=file.invalid/servlet/WMINDEX",
        )
        unsupported = CLEAR_URL.replace(
            "SHOWREPORT_PRINTAUTO",
            "SHOWREPORT_UPDATE",
        )
        for clear in (cross_host, unsupported):
            with self.subTest(clear=clear):
                with self.assertRaises(TicketDecodeError):
                    parse_reportx_ticket(
                        TicketEnvelope.parse("dzreportx:||" + clear)
                    )

    def test_encrypted_frame_rejects_truncation_length_and_padding(self) -> None:
        with self.assertRaises(TicketDecodeError):
            parse_reportx_ticket(TicketEnvelope.parse("dzreportx:AAAA"))

        clear = CLEAR_URL.encode("ascii")
        too_long = (len(clear) + 100).to_bytes(4, "little") + clear
        too_long += b"\0" * (-len(too_long) % 16)
        ciphertext = b"".join(
            reportx_aria_encrypt_block(
                too_long[offset : offset + 16],
                _reportx_key(),
            )
            for offset in range(0, len(too_long), 16)
        )
        with self.assertRaises(TicketDecodeError):
            parse_reportx_ticket(
                TicketEnvelope.parse(
                    "dzreportx:" + base64.b64encode(ciphertext).decode("ascii")
                )
            )

        framed = len(clear).to_bytes(4, "little") + clear + b"\x01"
        framed += b"\0" * (-len(framed) % 16)
        ciphertext = b"".join(
            reportx_aria_encrypt_block(
                framed[offset : offset + 16],
                _reportx_key(),
            )
            for offset in range(0, len(framed), 16)
        )
        with self.assertRaises(TicketDecodeError):
            parse_reportx_ticket(
                TicketEnvelope.parse(
                    "dzreportx:" + base64.b64encode(ciphertext).decode("ascii")
                )
            )

    def test_decoder_and_broker_accept_only_exact_remote_response(self) -> None:
        ticket = encrypted_ticket(CLEAR_URL.encode("ascii"))
        context = SessionContext.from_mapping(
            "https://icert.yonsei.ac.kr",
            {},
        )
        session = ReportXProtocolV1Decoder().open(ticket, context)
        broker = ProtocolBroker(
            session,
            BrokerPolicy(allowed_hosts=frozenset({"uni.webminwon.com"})),
        )
        action = broker.start()
        self.assertIsInstance(action, RequestAction)
        assert isinstance(action, RequestAction)
        self.assertEqual(EXPECTED_REQUEST, action.url)
        body = b"opaque server-issued ReportX response"
        result = broker.receive(
            NetworkResponse.from_bytes(
                request_id=action.request_id,
                url=action.url,
                status=200,
                headers=(("Content-Type", "application/octet-stream"),),
                body=body,
            )
        )
        self.assertIsInstance(result, AcceptServerResponse)
        assert broker.accepted_artifact is not None
        self.assertEqual(body, broker.accepted_artifact.body)
        self.assertEqual(hashlib.sha256(body).hexdigest(), broker.accepted_artifact.sha256)


if __name__ == "__main__":
    unittest.main()
