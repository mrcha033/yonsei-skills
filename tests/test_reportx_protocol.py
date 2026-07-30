from __future__ import annotations

import dataclasses
import hashlib
import sys
import unittest
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
    BundledDecoderRegistry,
    Failed,
    NetworkResponse,
    ProtocolBroker,
    RequestAction,
    SessionContext,
    TicketEnvelope,
)


ALLOWED_URL = "https://icert.yonsei.ac.kr/servlet/YSBS"
POLICY = BrokerPolicy(allowed_hosts=frozenset({"icert.yonsei.ac.kr"}))


class OneActionSession:
    def __init__(self, action: object) -> None:
        self.action = action

    def step(self, event=None):  # noqa: ANN001, ANN201
        return self.action


class AcceptExactResponseSession:
    def step(self, event=None):  # noqa: ANN001, ANN201
        if event is None:
            return RequestAction(
                request_id="report-page",
                method="POST",
                url=ALLOWED_URL,
                headers=(("Content-Type", "application/octet-stream"),),
                body=b"bounded request",
            )
        return AcceptServerResponse(
            request_id=event.request_id,
            expected_sha256=event.body_sha256,
        )


class ReportXProtocolTests(unittest.TestCase):
    def test_ticket_parser_is_opaque_bounded_and_immutable(self) -> None:
        raw = "dzreportx:AbC+/=_-%25"
        ticket = TicketEnvelope.parse(raw)
        self.assertEqual(raw, ticket.as_uri())
        self.assertEqual(hashlib.sha256(raw.encode("ascii")).hexdigest(), ticket.raw_sha256)
        self.assertEqual(
            hashlib.sha256(b"AbC+/=_-%25").hexdigest(),
            ticket.payload_sha256,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ticket.raw_length = 1  # type: ignore[misc]

        invalid = (
            "reportx:abc",
            "dzreportx:",
            "dzreportx:space here",
            "dzreportx:line\nbreak",
            "dzreportx:\N{SNOWMAN}",
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    TicketEnvelope.parse(value)
        with self.assertRaises(ValueError):
            TicketEnvelope.parse("dzreportx:" + ("a" * 8), max_bytes=16)

    def test_context_is_bounded_and_does_not_model_credentials(self) -> None:
        context = SessionContext.from_mapping(
            "https://icert.yonsei.ac.kr",
            {"GIWANNO": "Y", "MINNO": "X"},
        )
        self.assertEqual("X", context.get("MINNO"))
        with self.assertRaises(TypeError):
            context.mapping["MINNO"] = "changed"  # type: ignore[index]
        with self.assertRaises(ValueError):
            SessionContext.from_mapping(
                "https://icert.yonsei.ac.kr",
                {"A": "x" * 4097},
            )
        with self.assertRaises(ValueError):
            SessionContext(
                origin="https://icert.yonsei.ac.kr",
                values=tuple((f"K{index}", "v") for index in range(33)),
            )

    def test_request_transport_policy_rejects_cross_host_http_port_and_method(self) -> None:
        actions = (
            (
                RequestAction("r1", "GET", "http://icert.yonsei.ac.kr/x"),
                "scheme_forbidden",
            ),
            (
                RequestAction("r2", "GET", "https://evil.example/x"),
                "host_forbidden",
            ),
            (
                RequestAction("r3", "GET", "https://icert.yonsei.ac.kr:444/x"),
                "port_forbidden",
            ),
            (
                RequestAction("r4", "PUT", "https://icert.yonsei.ac.kr/x"),
                "method_forbidden",
            ),
            (
                RequestAction(
                    "r5",
                    "GET",
                    "https://icert.yonsei.ac.kr/x",
                    body=b"decoder bytes",
                ),
                "get_body_forbidden",
            ),
        )
        for action, code in actions:
            with self.subTest(code=code):
                broker = ProtocolBroker(OneActionSession(action), POLICY)
                result = broker.start()
                self.assertIsInstance(result, Failed)
                self.assertEqual(code, result.code)
                self.assertIsNone(broker.accepted_artifact)

    def test_decoder_cannot_set_credentials_host_or_proxy_headers(self) -> None:
        for name in (
            "Cookie",
            "Authorization",
            "Host",
            "Proxy-Authorization",
            "Proxy-Whatever",
        ):
            with self.subTest(name=name):
                action = RequestAction(
                    request_id="blocked",
                    method="GET",
                    url=ALLOWED_URL,
                    headers=((name, "secret"),),
                )
                result = ProtocolBroker(OneActionSession(action), POLICY).start()
                self.assertIsInstance(result, Failed)
                self.assertEqual("header_forbidden", result.code)

    def test_redirects_and_untracked_responses_fail_closed(self) -> None:
        request = RequestAction("tracked", "GET", ALLOWED_URL)

        redirected = ProtocolBroker(OneActionSession(request), POLICY)
        self.assertEqual(request, redirected.start())
        result = redirected.receive(
            NetworkResponse.from_bytes(
                request_id="tracked",
                url=ALLOWED_URL,
                status=302,
                headers=(("Location", "https://evil.example/"),),
                body=b"",
            )
        )
        self.assertIsInstance(result, Failed)
        self.assertEqual("redirect_forbidden", result.code)

        changed_url = ProtocolBroker(OneActionSession(request), POLICY)
        changed_url.start()
        result = changed_url.receive(
            NetworkResponse.from_bytes(
                request_id="tracked",
                url=ALLOWED_URL + "?redirected=1",
                status=200,
                body=b"server bytes",
            )
        )
        self.assertIsInstance(result, Failed)
        self.assertEqual("redirect_forbidden", result.code)

        wrong_id = ProtocolBroker(OneActionSession(request), POLICY)
        wrong_id.start()
        result = wrong_id.receive(
            NetworkResponse.from_bytes(
                request_id="not-tracked",
                url=ALLOWED_URL,
                status=200,
                body=b"server bytes",
            )
        )
        self.assertIsInstance(result, Failed)
        self.assertEqual("untracked_response", result.code)

    def test_only_exact_tracked_response_body_can_be_accepted(self) -> None:
        server_bytes = b"%PDF-1.7\nserver-issued bytes stay unchanged\n%%EOF\n"
        broker = ProtocolBroker(AcceptExactResponseSession(), POLICY)
        request = broker.start()
        self.assertIsInstance(request, RequestAction)

        response = NetworkResponse.from_bytes(
            request_id=request.request_id,
            url=request.url,
            status=200,
            headers=(("Content-Type", "application/pdf"),),
            body=server_bytes,
        )
        result = broker.receive(response)
        self.assertIsInstance(result, AcceptServerResponse)
        artifact = broker.accepted_artifact
        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual(server_bytes, artifact.body)
        self.assertEqual(hashlib.sha256(server_bytes).hexdigest(), artifact.sha256)
        self.assertEqual(response.body_sha256, artifact.sha256)
        self.assertEqual("accepted", broker.state)

    def test_response_hash_mismatch_never_reaches_decoder_or_artifact(self) -> None:
        broker = ProtocolBroker(AcceptExactResponseSession(), POLICY)
        request = broker.start()
        assert isinstance(request, RequestAction)
        response = NetworkResponse(
            request_id=request.request_id,
            url=request.url,
            status=200,
            headers=(),
            body=b"real body",
            body_sha256="0" * 64,
        )
        result = broker.receive(response)
        self.assertIsInstance(result, Failed)
        self.assertEqual("response_hash_mismatch", result.code)
        self.assertIsNone(broker.accepted_artifact)

    def test_decoder_cannot_emit_arbitrary_artifact_bytes(self) -> None:
        malicious = ProtocolBroker(
            OneActionSession(b"%PDF-1.7\nforged by decoder\n%%EOF\n"),
            POLICY,
        )
        result = malicious.start()
        self.assertIsInstance(result, Failed)
        self.assertEqual("invalid_decoder_action", result.code)
        self.assertIsNone(malicious.accepted_artifact)
        self.assertNotIn("body", {item.name for item in dataclasses.fields(AcceptServerResponse)})

        untracked = ProtocolBroker(
            OneActionSession(
                AcceptServerResponse("never-requested", hashlib.sha256(b"x").hexdigest())
            ),
            POLICY,
        )
        result = untracked.start()
        self.assertIsInstance(result, Failed)
        self.assertEqual("untracked_accept", result.code)
        self.assertIsNone(untracked.accepted_artifact)

    def test_registry_has_only_the_source_bundled_decoder(self) -> None:
        registry = BundledDecoderRegistry()
        self.assertEqual(("reportx-1.0-cleanroom",), registry.decoder_ids)
        ticket = TicketEnvelope.parse("dzreportx:opaque")
        context = SessionContext.from_mapping(
            "https://icert.yonsei.ac.kr",
            {},
        )
        result = registry.open(ticket, context)
        self.assertEqual("Failed", type(result).__name__)
        self.assertFalse(hasattr(registry, "load_path"))
        self.assertFalse(hasattr(registry, "register"))


if __name__ == "__main__":
    unittest.main()
