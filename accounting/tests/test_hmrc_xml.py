from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from django.test import SimpleTestCase

from accounting.hmrc_xml import (
    HmrcXmlError,
    HmrcXmlTransportError,
    XML_PROFILES,
    build_poll_envelope,
    build_submission_envelope,
    calculate_irmark,
    insert_irmark,
    parse_transaction_engine_response,
    send_transaction_engine_xml,
)


BODY_XML = """<Body><IRenvelope><IRheader><IRmark Type=\"generic\"></IRmark></IRheader><Return><Amount>100.00</Amount></Return></IRenvelope></Body>"""


class HmrcXmlDocumentTests(SimpleTestCase):
    def test_all_supported_xml_filing_types_have_distinct_profiles(self):
        self.assertEqual(
            set(XML_PROFILES),
            {"CT600", "CT600_AMENDMENT", "FPS", "EPS", "CIS300", "SA100", "SA800", "SA900"},
        )

    def test_irmark_is_deterministic_base64_sha1_and_excludes_existing_mark(self):
        first = calculate_irmark(BODY_XML)
        changed_mark = BODY_XML.replace("></IRmark>", ">old-value</IRmark>")
        second = calculate_irmark(changed_mark)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 28)

    def test_insert_irmark_requires_exactly_one_target(self):
        output = insert_irmark(BODY_XML)
        root = ET.fromstring(output)
        mark = next(item for item in root.iter() if item.tag.endswith("IRmark"))
        self.assertEqual(mark.attrib["Type"], "generic")
        self.assertEqual(mark.text, calculate_irmark(BODY_XML))

        with self.assertRaisesRegex(HmrcXmlError, "exactly one"):
            insert_irmark("<Body><Return /></Body>")

    def test_submission_envelope_contains_required_protocol_fields(self):
        output = build_submission_envelope(
            filing_type="CT600",
            transaction_id="LEDGER-000001",
            sender_id="test-sender",
            password="test-password",
            enrolment_value="1234567890",
            body_xml=BODY_XML,
            gateway_test=True,
            vendor_id="9999",
        )

        self.assertIn("HMRC-CT-CT600", output)
        self.assertIn("LEDGER-000001", output)
        self.assertIn("<GatewayTest>1</GatewayTest>", output)
        self.assertIn('Type="UTR"', output)
        root = ET.fromstring(output)
        mark = next(item for item in root.iter() if item.tag.endswith("IRmark"))
        self.assertEqual(len(mark.text), 28)

    def test_submission_envelope_rejects_unknown_profile_missing_credentials_and_bad_body(self):
        with self.assertRaisesRegex(HmrcXmlError, "No HMRC XML profile"):
            build_submission_envelope(
                filing_type="UNKNOWN", transaction_id="1", sender_id="x", password="x",
                enrolment_value="x", body_xml=BODY_XML,
            )
        with self.assertRaisesRegex(HmrcXmlError, "password"):
            build_submission_envelope(
                filing_type="SA100", transaction_id="1", sender_id="x", password="",
                enrolment_value="x", body_xml=BODY_XML,
            )
        with self.assertRaisesRegex(HmrcXmlError, "well-formed"):
            build_submission_envelope(
                filing_type="SA100", transaction_id="1", sender_id="x", password="x",
                enrolment_value="x", body_xml="<Body>",
            )

    def test_poll_envelope_requires_correlation_and_uses_poll_qualifier(self):
        output = build_poll_envelope(
            correlation_id="correlation-1", sender_id="sender", password="password", gateway_test=True
        )
        self.assertIn("<Qualifier>poll</Qualifier>", output)
        self.assertIn("correlation-1", output)
        with self.assertRaisesRegex(HmrcXmlError, "Correlation ID"):
            build_poll_envelope(correlation_id="", sender_id="sender", password="password")

    def test_response_parser_distinguishes_pending_accepted_and_rejected(self):
        pending = parse_transaction_engine_response(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>response</Qualifier>"
            "<CorrelationID>abc</CorrelationID></MessageDetails></Header></GovTalkMessage>"
        )
        accepted = parse_transaction_engine_response(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>response</Qualifier>"
            "<CorrelationID /></MessageDetails></Header></GovTalkMessage>"
        )
        rejected = parse_transaction_engine_response(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>error</Qualifier></MessageDetails></Header>"
            "<GovTalkDetails><GovTalkErrors><Error><Number>100</Number><Type>fatal</Type>"
            "<Text>Invalid return</Text></Error></GovTalkErrors></GovTalkDetails></GovTalkMessage>"
        )
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["errors"][0]["number"], "100")

    def test_transport_is_fail_closed_and_handles_success_and_network_errors(self):
        with self.assertRaisesRegex(HmrcXmlError, "disabled"):
            send_transaction_engine_xml("<GovTalkMessage />")

        response = MagicMock()
        response.read.return_value = (
            b"<GovTalkMessage><Header><MessageDetails><Qualifier>response</Qualifier>"
            b"<CorrelationID>abc</CorrelationID></MessageDetails></Header></GovTalkMessage>"
        )
        response.__enter__.return_value = response
        with patch("accounting.hmrc_xml.urllib.request.urlopen", return_value=response) as urlopen:
            result = send_transaction_engine_xml("<GovTalkMessage />", enabled=True)
        self.assertEqual(result["status"], "pending")
        self.assertIn("test-transaction-engine", urlopen.call_args.args[0].full_url)

        with patch("accounting.hmrc_xml.urllib.request.urlopen", side_effect=TimeoutError):
            with self.assertRaisesRegex(HmrcXmlTransportError, "could not be reached"):
                send_transaction_engine_xml("<GovTalkMessage />", enabled=True)
