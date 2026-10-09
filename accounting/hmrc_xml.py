import base64
import hashlib
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


GOVTALK_NAMESPACE = "http://www.govtalk.gov.uk/CM/envelope"
TEST_SUBMISSION_URL = "https://test-transaction-engine.tax.service.gov.uk/submission"
TEST_POLL_URL = "https://test-transaction-engine.tax.service.gov.uk/poll"
LIVE_SUBMISSION_URL = "https://transaction-engine.tax.service.gov.uk/submission"
LIVE_POLL_URL = "https://transaction-engine.tax.service.gov.uk/poll"


class HmrcXmlError(RuntimeError):
    pass


class HmrcXmlTransportError(HmrcXmlError):
    def __init__(self, status_code, message, response_body=""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True)
class HmrcXmlProfile:
    filing_type: str
    message_class: str
    enrolment_key_type: str
    requires_irmark: bool = True


XML_PROFILES = {
    "CT600": HmrcXmlProfile("CT600", "HMRC-CT-CT600", "UTR"),
    "CT600_AMENDMENT": HmrcXmlProfile("CT600_AMENDMENT", "HMRC-CT-CT600", "UTR"),
    "FPS": HmrcXmlProfile("FPS", "HMRC-PAYE-RTI-FPS", "TaxOfficeNumber"),
    "EPS": HmrcXmlProfile("EPS", "HMRC-PAYE-RTI-EPS", "TaxOfficeNumber"),
    "CIS300": HmrcXmlProfile("CIS300", "HMRC-CIS-CIS300", "TaxOfficeNumber"),
    "SA100": HmrcXmlProfile("SA100", "HMRC-SA-SA100", "UTR"),
    "SA800": HmrcXmlProfile("SA800", "HMRC-SA-SA800", "UTR"),
    "SA900": HmrcXmlProfile("SA900", "HMRC-SA-SA900", "UTR"),
}


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _parse_xml(xml_text, label):
    try:
        return ET.fromstring(xml_text)
    except (ET.ParseError, TypeError) as exc:
        raise HmrcXmlError(f"{label} is not well-formed XML.") from exc


def _canonical_xml(element):
    serialized = ET.tostring(element, encoding="unicode")
    return ET.canonicalize(xml_data=serialized, strip_text=False)


def calculate_irmark(body_xml):
    """Calculate the generic HMRC IRmark over Body, excluding IRmark nodes."""
    body = _parse_xml(body_xml, "The HMRC submission body")
    if _local_name(body.tag) != "Body":
        raise HmrcXmlError("The IRmark input must be an HMRC Body element.")

    for parent in body.iter():
        for child in list(parent):
            if _local_name(child.tag) == "IRmark":
                parent.remove(child)

    digest = hashlib.sha1(_canonical_xml(body).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def insert_irmark(body_xml):
    body = _parse_xml(body_xml, "The HMRC submission body")
    if _local_name(body.tag) != "Body":
        raise HmrcXmlError("The IRmark input must be an HMRC Body element.")
    targets = [element for element in body.iter() if _local_name(element.tag) == "IRmark"]
    if len(targets) != 1:
        raise HmrcXmlError("The HMRC submission body must contain exactly one IRmark element.")
    targets[0].set("Type", "generic")
    targets[0].text = calculate_irmark(body_xml)
    return ET.tostring(body, encoding="unicode")


def build_submission_envelope(
    *,
    filing_type,
    transaction_id,
    sender_id,
    password,
    enrolment_value,
    body_xml,
    gateway_test=True,
    vendor_id="",
):
    """Wrap an already schema-built HMRC body in a Transaction Engine envelope.

    This function deliberately does not invent a service body. The caller must
    supply XML produced from the current official service schema.
    """
    profile = XML_PROFILES.get(filing_type)
    if not profile:
        raise HmrcXmlError(f"No HMRC XML profile is registered for {filing_type}.")
    required = {
        "transaction ID": transaction_id,
        "sender ID": sender_id,
        "password": password,
        "enrolment value": enrolment_value,
    }
    missing = [label for label, value in required.items() if not str(value or "").strip()]
    if missing:
        raise HmrcXmlError(f"Missing HMRC envelope field(s): {', '.join(missing)}.")
    if len(str(transaction_id)) > 32:
        raise HmrcXmlError("The HMRC transaction ID must not exceed 32 characters.")

    prepared_body = insert_irmark(body_xml) if profile.requires_irmark else body_xml
    body = _parse_xml(prepared_body, "The HMRC submission body")

    ET.register_namespace("", GOVTALK_NAMESPACE)
    root = ET.Element(f"{{{GOVTALK_NAMESPACE}}}GovTalkMessage")
    ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}EnvelopeVersion").text = "2.0"
    header = ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}Header")
    details = ET.SubElement(header, f"{{{GOVTALK_NAMESPACE}}}MessageDetails")
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Class").text = profile.message_class
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Qualifier").text = "request"
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Function").text = "submit"
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}TransactionID").text = str(transaction_id)
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}CorrelationID")
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Transformation").text = "XML"
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}GatewayTest").text = "1" if gateway_test else "0"

    sender = ET.SubElement(header, f"{{{GOVTALK_NAMESPACE}}}SenderDetails")
    identity = ET.SubElement(sender, f"{{{GOVTALK_NAMESPACE}}}IDAuthentication")
    ET.SubElement(identity, f"{{{GOVTALK_NAMESPACE}}}SenderID").text = str(sender_id)
    authentication = ET.SubElement(identity, f"{{{GOVTALK_NAMESPACE}}}Authentication")
    ET.SubElement(authentication, f"{{{GOVTALK_NAMESPACE}}}Method").text = "clear"
    ET.SubElement(authentication, f"{{{GOVTALK_NAMESPACE}}}Value").text = str(password)

    talk_details = ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}GovTalkDetails")
    keys = ET.SubElement(talk_details, f"{{{GOVTALK_NAMESPACE}}}Keys")
    key = ET.SubElement(keys, f"{{{GOVTALK_NAMESPACE}}}Key", {"Type": profile.enrolment_key_type})
    key.text = str(enrolment_value)
    if vendor_id:
        channel = ET.SubElement(talk_details, f"{{{GOVTALK_NAMESPACE}}}ChannelRouting")
        ET.SubElement(channel, f"{{{GOVTALK_NAMESPACE}}}Channel", {"Version": "1.0", "Product": "LedgerHouse"}).text = str(vendor_id)

    root.append(body)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def build_poll_envelope(*, correlation_id, sender_id, password, gateway_test=True):
    if not all(str(value or "").strip() for value in (correlation_id, sender_id, password)):
        raise HmrcXmlError("Correlation ID, sender ID and password are required for polling.")
    ET.register_namespace("", GOVTALK_NAMESPACE)
    root = ET.Element(f"{{{GOVTALK_NAMESPACE}}}GovTalkMessage")
    ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}EnvelopeVersion").text = "2.0"
    header = ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}Header")
    details = ET.SubElement(header, f"{{{GOVTALK_NAMESPACE}}}MessageDetails")
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Qualifier").text = "poll"
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}CorrelationID").text = str(correlation_id)
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}Transformation").text = "XML"
    ET.SubElement(details, f"{{{GOVTALK_NAMESPACE}}}GatewayTest").text = "1" if gateway_test else "0"
    sender = ET.SubElement(header, f"{{{GOVTALK_NAMESPACE}}}SenderDetails")
    identity = ET.SubElement(sender, f"{{{GOVTALK_NAMESPACE}}}IDAuthentication")
    ET.SubElement(identity, f"{{{GOVTALK_NAMESPACE}}}SenderID").text = str(sender_id)
    authentication = ET.SubElement(identity, f"{{{GOVTALK_NAMESPACE}}}Authentication")
    ET.SubElement(authentication, f"{{{GOVTALK_NAMESPACE}}}Method").text = "clear"
    ET.SubElement(authentication, f"{{{GOVTALK_NAMESPACE}}}Value").text = str(password)
    ET.SubElement(root, f"{{{GOVTALK_NAMESPACE}}}GovTalkDetails")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def parse_transaction_engine_response(xml_text):
    root = _parse_xml(xml_text, "The HMRC Transaction Engine response")
    values = {}
    errors = []
    for element in root.iter():
        name = _local_name(element.tag)
        if name in {"Qualifier", "CorrelationID", "TransactionID", "GatewayTimestamp"}:
            values[name] = (element.text or "").strip()
        if name == "Error":
            item = {_local_name(child.tag): (child.text or "").strip() for child in element}
            errors.append({
                "number": item.get("Number", ""),
                "type": item.get("Type", ""),
                "text": item.get("Text", ""),
                "location": item.get("Location", ""),
            })
    qualifier = values.get("Qualifier", "").lower()
    if errors or qualifier == "error":
        status = "rejected"
    elif qualifier in {"response", "acknowledgement"} and values.get("CorrelationID"):
        status = "pending"
    elif qualifier in {"response", "acknowledgement"}:
        status = "accepted"
    else:
        status = "unknown"
    return {
        "status": status,
        "qualifier": qualifier,
        "correlation_id": values.get("CorrelationID", ""),
        "transaction_id": values.get("TransactionID", ""),
        "gateway_timestamp": values.get("GatewayTimestamp", ""),
        "errors": errors,
    }


def send_transaction_engine_xml(xml_text, *, environment="sandbox", poll=False, timeout=30, enabled=False):
    if not enabled:
        raise HmrcXmlError("HMRC XML transport is disabled until official test credentials and schema evidence are verified.")
    if environment not in {"sandbox", "production"}:
        raise HmrcXmlError("HMRC XML environment must be sandbox or production.")
    _parse_xml(xml_text, "The outbound HMRC XML document")
    if environment == "sandbox":
        url = TEST_POLL_URL if poll else TEST_SUBMISSION_URL
    else:
        url = LIVE_POLL_URL if poll else LIVE_SUBMISSION_URL
    request = urllib.request.Request(
        url,
        data=xml_text.encode("utf-8"),
        headers={"Content-Type": "application/xml", "Accept": "application/xml"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HmrcXmlTransportError(exc.code, "HMRC rejected the XML transport request.", body) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise HmrcXmlTransportError(503, "HMRC XML transport could not be reached; no filing status was changed.") from exc
    return parse_transaction_engine_response(response_text)
