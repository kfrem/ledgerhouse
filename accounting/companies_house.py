import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .ixbrl import generate_micro_entity_ixbrl, validate_micro_entity_ixbrl


INITIAL_ACCOUNTS_FILING_SCOPE = (
    ("MicroEntity", "Micro-entity accounts"),
    ("SmallUnaudited", "Small unaudited full accounts"),
    ("SmallUnauditedFilleted", "Small unaudited filleted accounts"),
    ("Dormant", "Dormant company accounts"),
)
INITIAL_ACCOUNTS_FILING_TYPES = {accounts_type for accounts_type, _label in INITIAL_ACCOUNTS_FILING_SCOPE}
# These are presentation/data variants of a declared filing type, not separate
# types LedgerHouse claims to support. They remain valid in scenario testing.
INITIAL_ACCOUNTS_FILING_TYPE_ALIASES = {
    "MicroEntityComparative": "MicroEntity",
    "AmendedMicroEntity": "MicroEntity",
}


class CompaniesHouseApiError(RuntimeError):
    """Raised when Companies House returns a non-success response."""

    def __init__(self, status_code, message, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _local_key_path():
    configured_path = getattr(settings, "COMPANIES_HOUSE_API_KEY_FILE", "")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".companies_house_api_key"


def companies_house_api_key():
    """Resolve the API key from env/settings or a local-only developer file."""
    configured_key = getattr(settings, "COMPANIES_HOUSE_API_KEY", "")
    if configured_key:
        return configured_key.strip()

    key_path = _local_key_path()
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    return ""


def _local_filing_credentials_path():
    configured_path = getattr(settings, "COMPANIES_HOUSE_FILING_CREDENTIALS_FILE", "")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".ledgerhouse" / "companies_house_filing.env"


def _load_key_value_file(path):
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    values = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def companies_house_filing_credentials():
    """Resolve Companies House XML Gateway test credentials without exposing secrets."""
    local_file = _local_filing_credentials_path()
    file_values = _load_key_value_file(local_file)

    def resolve(name, default=""):
        configured = getattr(settings, name, "")
        return str(configured or file_values.get(name) or default).strip()

    presenter_id = resolve("COMPANIES_HOUSE_FILING_PRESENTER_ID")
    authentication_value = resolve("COMPANIES_HOUSE_FILING_AUTHENTICATION_VALUE")
    test_flag = resolve("COMPANIES_HOUSE_FILING_TEST_FLAG", "1")
    package_reference = resolve("COMPANIES_HOUSE_FILING_PACKAGE_REFERENCE")
    product_key = resolve("COMPANIES_HOUSE_FILING_PRODUCT_KEY", "ledgerhouse").lower()
    send_enabled = resolve("COMPANIES_HOUSE_FILING_SEND_ENABLED", "False").lower() in ("true", "1", "yes")
    gateway_url = resolve(
        "COMPANIES_HOUSE_FILING_GATEWAY_URL",
        "https://xmlgw.companieshouse.gov.uk/v1-0/xmlgw/Gateway",
    )
    return {
        "presenter_id": presenter_id,
        "authentication_value": authentication_value,
        "test_flag": test_flag,
        "package_reference": package_reference,
        "product_key": product_key,
        "send_enabled": send_enabled,
        "gateway_url": gateway_url,
        "configured": all([presenter_id, authentication_value, test_flag, package_reference, gateway_url]),
        "local_file": str(local_file),
        "source": "environment" if getattr(settings, "COMPANIES_HOUSE_FILING_PRESENTER_ID", "") else "local file",
    }


def companies_house_status():
    key = companies_house_api_key()
    key_path = _local_key_path()
    filing = companies_house_filing_credentials()
    key_source = "environment" if getattr(settings, "COMPANIES_HOUSE_API_KEY", "") else "local file"
    live_enabled = bool(getattr(settings, "COMPANIES_HOUSE_FILING_LIVE_ENABLED", False))
    live_confirmed = bool(getattr(settings, "COMPANIES_HOUSE_LIVE_APPROVAL_CONFIRMED", False))
    test_mode_only = not (
        filing["configured"]
        and live_enabled
        and live_confirmed
        and filing["test_flag"] == "0"
    )
    return {
        "base_url": settings.COMPANIES_HOUSE_API_BASE_URL,
        "configured": bool(key),
        "key_source": key_source if key else "",
        "local_key_file": str(key_path),
        "api_key_present": bool(key),
        "capabilities": [
            "Company profile lookup",
            "Accounts and confirmation statement dates",
            "Registered office and SIC code review",
        ],
        "filing_enabled": filing["configured"],
        "filing_status": (
            "Live credentials configured; live sending locked"
            if filing["configured"] and filing["test_flag"] == "0" and not filing["send_enabled"]
            else "Live credentials ready"
            if filing["configured"] and filing["test_flag"] == "0"
            else "Test credentials ready"
            if filing["configured"]
            else "Not enabled"
        ),
        "filing_detail": (
            "Accounts filing uses the Companies House XML Gateway live account. "
            "Live sending requires the explicit production safety controls and an authorised client filing."
            if filing["configured"] and filing["test_flag"] == "0"
            else "Accounts filing uses the Companies House XML Gateway test account. "
            "Prepared submissions still require valid XHTML/iXBRL accounts and a "
            "unique six digit submission number before they are safe to send."
        ),
        "accounts_tis_version": "Companies House Accounts TIS supplement 5.9",
        "filing_credentials_file": filing["local_file"],
        "filing_credential_source": filing["source"] if filing["configured"] else "",
        "filing_gateway_url": filing["gateway_url"] if filing["configured"] else "",
        "filing_package_reference_present": bool(filing["package_reference"]),
        "filing_test_flag": filing["test_flag"] if filing["configured"] else "",
        "filing_product_key": filing["product_key"],
        "test_send_enabled": filing["configured"] and filing["send_enabled"] and filing["test_flag"] == "1",
        "live_send_enabled": filing["configured"] and filing["send_enabled"] and filing["test_flag"] == "0",
        "production_safety_lock": "Test mode only" if test_mode_only else "Live filing enabled",
        "production_safety_detail": (
            "Live Companies House filing is blocked locally. Enable it only after Companies House approves the test submissions "
            "and production filing settings are explicitly configured."
            if test_mode_only
            else "Live filing settings are enabled. Use only for approved production clients."
        ),
        "test_mode_only": test_mode_only,
    }


def normalise_company_number(company_number):
    cleaned = re.sub(r"[^0-9A-Za-z]", "", company_number or "").upper()
    if not cleaned:
        raise ValueError("Enter a Companies House company number.")
    if len(cleaned) > 8:
        raise ValueError("Company number must be 8 characters or fewer.")
    if cleaned.isdigit():
        return cleaned.zfill(8)
    return cleaned


def _basic_auth_header(api_key):
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _companies_house_json_request(path, api_key=None):
    key = (api_key or companies_house_api_key()).strip()
    if not key:
        raise CompaniesHouseApiError(
            0,
            "Companies House API key is not configured.",
            {"code": "missing_api_key"},
        )

    url = f"{settings.COMPANIES_HOUSE_API_BASE_URL}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": _basic_auth_header(key),
            "User-Agent": "LedgerHouse/local-companies-house",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            return {
                "status": response.status,
                "payload": json.loads(response_body) if response_body else {},
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        try:
            error_payload = json.loads(error_body)
        except json.JSONDecodeError:
            error_payload = {"message": error_body}
        message = error_payload.get("error") or error_payload.get("message") or str(exc)
        raise CompaniesHouseApiError(exc.code, message, error_payload) from exc


def retrieve_company_profile(company_number, api_key=None):
    normalised_number = normalise_company_number(company_number)
    response = _companies_house_json_request(f"/company/{normalised_number}", api_key=api_key)
    return response["payload"]


def company_profile_snapshot(profile):
    accounts = profile.get("accounts") or {}
    confirmation_statement = profile.get("confirmation_statement") or {}
    address = profile.get("registered_office_address") or {}
    address_lines = [
        address.get("address_line_1"),
        address.get("address_line_2"),
        address.get("locality"),
        address.get("region"),
        address.get("postal_code"),
        address.get("country"),
    ]
    return {
        "company_name": profile.get("company_name") or "",
        "company_number": profile.get("company_number") or "",
        "company_status": profile.get("company_status") or "",
        "company_type": profile.get("type") or "",
        "incorporated_on": profile.get("date_of_creation") or "",
        "accounts_next_due": accounts.get("next_due") or "",
        "accounts_overdue": accounts.get("overdue"),
        "confirmation_next_due": confirmation_statement.get("next_due") or "",
        "confirmation_overdue": confirmation_statement.get("overdue"),
        "sic_codes": profile.get("sic_codes") or [],
        "registered_office": ", ".join(line for line in address_lines if line),
    }


def format_submission_number(number):
    if number < 1 or number > 999999:
        raise ValueError("Companies House submission number must be between 000001 and 999999.")
    return f"{number:06d}"


@transaction.atomic
def next_companies_house_submission_number(product_key=None):
    """Reserve the next number atomically for one configured product.

    A number is never reused after a failed build or rejected submission. This
    preserves the strict incremental sequence required by the XML Gateway.
    """
    from .models import CompaniesHouseFilingSubmission, CompaniesHouseSubmissionSequence

    key = (product_key or companies_house_filing_credentials()["product_key"]).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", key):
        raise CompaniesHouseApiError(0, "Companies House filing product key must contain lowercase letters, numbers, hyphens or underscores.")

    sequence, created = CompaniesHouseSubmissionSequence.objects.select_for_update().get_or_create(
        product_key=key,
        defaults={"last_submission_number": 0},
    )
    if created:
        last_existing = CompaniesHouseFilingSubmission.objects.filter(product_key=key).aggregate(
            Max("submission_number")
        )["submission_number__max"]
        sequence.last_submission_number = last_existing or 0
    if sequence.last_submission_number >= 999999:
        raise CompaniesHouseApiError(0, "Companies House submission number limit reached for this product.")
    sequence.last_submission_number += 1
    sequence.save(update_fields=["last_submission_number", "updated_at"])
    return sequence.last_submission_number


def _filing_company_number(company_number):
    normalised = normalise_company_number(company_number)
    if not normalised.isdigit():
        raise ValueError("This first Companies House filing route supports numeric company numbers only.")
    return normalised


def _govtalk_envelope(credentials, submission_number, body_element, message_class="FormSubmission"):
    if message_class == "Accounts":
        ns = "http://www.govtalk.gov.uk/CM/envelope"
        envelope_version = "2.0"
        root_attrib = {
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": (
                "http://www.govtalk.gov.uk/CM/envelope "
                "http://xmlgw.companieshouse.gov.uk/v1-0/schema/Egov_ch-v2-0.xsd"
            )
        }
    else:
        ns = "http://www.govtalk.gov.uk/schemas/govtalk/govtalkheader"
        envelope_version = "1.0"
        root_attrib = {}

    ET.register_namespace("", ns)
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    gt_ns = "http://www.govtalk.gov.uk/CM/core" if message_class == "Accounts" else "http://www.govtalk.gov.uk/schemas/govtalk/core"
    ET.register_namespace("gt", gt_ns)
    root = ET.Element(f"{{{ns}}}GovTalkMessage", root_attrib)
    ET.SubElement(root, f"{{{ns}}}EnvelopeVersion").text = envelope_version
    header = ET.SubElement(root, f"{{{ns}}}Header")
    details = ET.SubElement(header, f"{{{ns}}}MessageDetails")
    ET.SubElement(details, f"{{{ns}}}Class").text = message_class
    ET.SubElement(details, f"{{{ns}}}Qualifier").text = "request"
    if message_class == "Accounts":
        ET.SubElement(details, f"{{{ns}}}Function").text = "submit"
    ET.SubElement(details, f"{{{ns}}}TransactionID").text = format_submission_number(submission_number)
    ET.SubElement(details, f"{{{ns}}}GatewayTest").text = credentials["test_flag"]
    sender = ET.SubElement(header, f"{{{ns}}}SenderDetails")
    id_auth = ET.SubElement(sender, f"{{{ns}}}IDAuthentication")
    sender_id = hashlib.md5(credentials["presenter_id"].encode("utf-8")).hexdigest()
    authentication_value = hashlib.md5(credentials["authentication_value"].encode("utf-8")).hexdigest()
    ET.SubElement(id_auth, f"{{{ns}}}SenderID").text = sender_id
    auth = ET.SubElement(id_auth, f"{{{ns}}}Authentication")
    ET.SubElement(auth, f"{{{ns}}}Method").text = "clear"
    ET.SubElement(auth, f"{{{ns}}}Value").text = authentication_value
    ET.SubElement(sender, f"{{{ns}}}EmailAddress").text = "info@kafs-ltd.com"
    details_node = ET.SubElement(root, f"{{{ns}}}GovTalkDetails")
    keys = ET.SubElement(details_node, f"{{{ns}}}Keys")
    if message_class == "Accounts":
        ET.SubElement(keys, f"{{{ns}}}Key", {"Type": "FormType"}).text = "Accounts"
        target = ET.SubElement(details_node, f"{{{ns}}}TargetDetails")
        ET.SubElement(target, f"{{{ns}}}Organisation").text = "Companies House"
    body = ET.SubElement(root, f"{{{ns}}}Body")
    body.append(body_element)
    xml_text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if message_class == "Accounts":
        xml_text = _use_default_form_submission_namespace(xml_text)
    return xml_text


def _use_default_form_submission_namespace(xml_text):
    header_ns = "http://xmlgw.companieshouse.gov.uk/Header"
    match = re.search(r'\sxmlns:(ns\d+)="' + re.escape(header_ns) + r'"', xml_text)
    if not match:
        return xml_text
    prefix = match.group(1)
    xml_text = xml_text.replace(match.group(0), "", 1)
    xml_text = xml_text.replace(f"<{prefix}:FormSubmission", f'<FormSubmission xmlns="{header_ns}"')
    xml_text = xml_text.replace(f"</{prefix}:FormSubmission>", "</FormSubmission>")
    xml_text = xml_text.replace(f"<{prefix}:", "<")
    xml_text = xml_text.replace(f"</{prefix}:", "</")
    return xml_text


def _form_submission_element(credentials, draft, company_number, company_name, company_authentication_code):
    ns = "http://xmlgw.companieshouse.gov.uk/Header"
    form_submission = ET.Element(
        f"{{{ns}}}FormSubmission",
        {
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": (
                "http://xmlgw.companieshouse.gov.uk/Header "
                "http://xmlgw.companieshouse.gov.uk/v1-0/schema/forms/FormSubmission-v2-11.xsd"
            )
        },
    )
    header = ET.SubElement(form_submission, f"{{{ns}}}FormHeader")
    ET.SubElement(header, f"{{{ns}}}CompanyNumber").text = company_number
    ET.SubElement(header, f"{{{ns}}}CompanyType").text = "EW"
    ET.SubElement(header, f"{{{ns}}}CompanyName").text = company_name[:160]
    ET.SubElement(header, f"{{{ns}}}CompanyAuthenticationCode").text = company_authentication_code
    ET.SubElement(header, f"{{{ns}}}PackageReference").text = credentials["package_reference"]
    ET.SubElement(header, f"{{{ns}}}Language").text = "EN"
    ET.SubElement(header, f"{{{ns}}}FormIdentifier").text = "Accounts"
    ET.SubElement(header, f"{{{ns}}}SubmissionNumber").text = format_submission_number(draft["_submission_number"])
    ET.SubElement(header, f"{{{ns}}}ContactName").text = "LedgerHouse Filing"
    ET.SubElement(header, f"{{{ns}}}ContactNumber").text = "00000000000"
    ET.SubElement(header, f"{{{ns}}}CustomerReference").text = f"LH{format_submission_number(draft['_submission_number'])}"
    ET.SubElement(form_submission, f"{{{ns}}}DateSigned").text = timezone.localdate().isoformat()
    ET.SubElement(form_submission, f"{{{ns}}}Form")
    ixbrl = draft["ixbrl"]
    document = ET.SubElement(form_submission, f"{{{ns}}}Document")
    ET.SubElement(document, f"{{{ns}}}Data").text = base64.b64encode(ixbrl.encode("utf-8")).decode("ascii")
    ET.SubElement(document, f"{{{ns}}}Date").text = timezone.localdate().isoformat()
    ET.SubElement(document, f"{{{ns}}}Filename").text = "accounts.xhtml"
    ET.SubElement(document, f"{{{ns}}}ContentType").text = "application/xml"
    ET.SubElement(document, f"{{{ns}}}Category").text = "ACCOUNTS"
    return form_submission


def sanitise_companies_house_xml(xml_text):
    return re.sub(r"(<Value>)(.*?)(</Value>)", r"\1REDACTED\3", xml_text, flags=re.DOTALL)


def _gateway_request(xml_text, credentials=None):
    credentials = credentials or companies_house_filing_credentials()
    request = urllib.request.Request(
        credentials["gateway_url"],
        data=xml_text.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml, application/xml",
            "User-Agent": "LedgerHouse/local-companies-house-filing",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise CompaniesHouseApiError(exc.code, f"Companies House XML Gateway HTTP {exc.code}", {"body": body}) from exc
    except urllib.error.URLError as exc:
        raise CompaniesHouseApiError(0, f"Companies House XML Gateway connection failed: {exc}") from exc


def parse_companies_house_gateway_status(response_xml):
    if not response_xml:
        return "Failed", ["Companies House XML Gateway returned an empty response."]
    lowered = response_xml.lower()
    if "no accepted or rejected documents found" in lowered or "no documents in an accepted or rejected state" in lowered:
        return "Pending", []
    if any(token in lowered for token in ["<error", "govtalkerrors", "<reject", "rejected"]):
        messages = []
        try:
            root = ET.fromstring(response_xml.encode("utf-8"))
            for item in root.iter():
                local_name = item.tag.rsplit("}", 1)[-1].lower()
                if local_name in {"text", "description", "message"} and (item.text or "").strip():
                    messages.append(item.text.strip())
        except ET.ParseError:
            messages.append("Companies House XML Gateway returned an error response that was not well-formed XML.")
        return "Rejected", messages or ["Companies House XML Gateway rejected the submission."]
    if "pending" in lowered:
        return "Pending", []
    if "accepted" in lowered:
        return "Accepted", []
    if "acknowledgement" in lowered or "submitted" in lowered:
        return "Pending", []
    return "Failed", [
        "Companies House XML Gateway returned an unrecognised status; no acceptance was recorded."
    ]


def companies_house_rejection_actions(messages):
    actions = []
    for message in messages or []:
        lowered = message.lower()
        if "submission number" in lowered or "duplicate" in lowered or "increment" in lowered:
            actions.append("Use the next unused incremental six digit submission number before retrying.")
        elif "company number" in lowered:
            actions.append("Check the company number against the Companies House profile and preserve leading zeros.")
        elif "authentication" in lowered or "authorisation" in lowered or "authorization" in lowered:
            actions.append("Check the company authentication code and presenter credentials in the local secret store.")
        elif "package reference" in lowered or "package" in lowered:
            actions.append("Check the Companies House test package reference configured for XML Gateway submissions.")
        elif "formidentifier" in lowered or "form identifier" in lowered or "form type" in lowered:
            actions.append("Check the accounts FormSubmission wrapper uses the Accounts form identifier and category.")
        elif "ixbrl" in lowered or "xbrl" in lowered or "taxonomy" in lowered:
            actions.append("Regenerate the XHTML/iXBRL accounts document and run the local validator again.")
        elif "schema" in lowered or "xml" in lowered:
            actions.append("Validate the GovTalk and FormSubmission XML wrapper against the Companies House schema shape.")
        else:
            actions.append("Review the Companies House gateway response and add a specific correction note before retrying.")
    if not actions:
        actions.append("No rejection action is currently needed.")
    return list(dict.fromkeys(actions))


def companies_house_next_local_build_items():
    return [
        {"item": "Poll history ledger", "status": "Built locally", "evidence": "Each status check is persisted against the submission."},
        {"item": "Filing approval gate", "status": "Built locally", "evidence": "Drafts can be assessed for client approval, iXBRL readiness and practice signoff."},
        {"item": "Production safety lock", "status": "Built locally", "evidence": "Local settings default to test-only filing until live approval is explicit."},
        {"item": "Rejection action mapping", "status": "Built locally", "evidence": "Gateway messages are translated into practical correction actions."},
        {"item": "Evidence ZIP export", "status": "Built locally", "evidence": "Reviewer pack can be generated from local records without secrets."},
        {"item": "Scenario matrix export", "status": "Built locally", "evidence": "All local Companies House scenario statuses are written to CSV/JSON."},
        {"item": "Sanitized XML export", "status": "Built locally", "evidence": "Gateway wrappers are stored/exported with authentication values redacted."},
        {"item": "iXBRL sample export", "status": "Built locally", "evidence": "Generated XHTML/iXBRL samples are included for scenario review."},
        {"item": "Submission duplicate guard", "status": "Built locally", "evidence": "Submission numbers are allocated atomically, incrementally and independently for each registered software product."},
        {"item": "Reviewer plain-English pack", "status": "Built locally", "evidence": "Evidence pack explains the controls in non-technical wording."},
        {"item": "Technical reviewer pack", "status": "Built locally", "evidence": "Evidence pack lists commands, models, gateway wrapper and validation boundaries."},
        {"item": "External blocker register", "status": "Built locally", "evidence": "Report separates local completion from Companies House/HMRC/live deployment approval."},
    ]


def companies_house_initial_filing_scope():
    """Return the explicit filing types LedgerHouse is currently prepared to test."""
    return [
        {"accounts_type": accounts_type, "label": label}
        for accounts_type, label in INITIAL_ACCOUNTS_FILING_SCOPE
    ]


def _require_supported_initial_accounts_type(statutory_accounts):
    accounts_type = statutory_accounts.accounts_type
    if accounts_type not in INITIAL_ACCOUNTS_FILING_TYPES | set(INITIAL_ACCOUNTS_FILING_TYPE_ALIASES):
        supported = ", ".join(label for _key, label in INITIAL_ACCOUNTS_FILING_SCOPE)
        raise ValueError(
            f"Accounts type '{accounts_type}' is outside LedgerHouse's declared initial Companies House filing scope. "
            f"Supported types: {supported}."
        )


def assess_companies_house_approval_gate(statutory_accounts, username="practice", signoff=False):
    from .models import ClientApprovalRecord, CompaniesHouseApprovalGate

    approval, _created = ClientApprovalRecord.objects.get_or_create(
        tenant=statutory_accounts.tenant,
        approval_type=ClientApprovalRecord.TYPE_STATUTORY_ACCOUNTS,
        reference=f"CH-{statutory_accounts.period_end}-{statutory_accounts.accounts_type}",
        defaults={
            "title": f"Companies House statutory accounts approval to {statutory_accounts.period_end}",
            "summary": "Client approval record used by the Companies House filing gate.",
            "status": ClientApprovalRecord.STATUS_APPROVED if statutory_accounts.client_approved else ClientApprovalRecord.STATUS_PENDING,
            "requested_by": username,
        },
    )
    if statutory_accounts.client_approved and approval.status != ClientApprovalRecord.STATUS_APPROVED:
        approval.status = ClientApprovalRecord.STATUS_APPROVED
        approval.decided_by = username
        approval.decided_at = timezone.now()
        approval.decision_note = "Approved locally for Companies House test filing readiness."
        approval.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])

    readiness_messages = validate_companies_house_filing_readiness(statutory_accounts)
    if approval.status != ClientApprovalRecord.STATUS_APPROVED:
        readiness_messages.append("Client approval record must be approved before filing signoff.")

    gate, _created = CompaniesHouseApprovalGate.objects.get_or_create(
        tenant=statutory_accounts.tenant,
        statutory_accounts=statutory_accounts,
        defaults={
            "client_approval": approval,
            "client_pack_reference": approval.reference,
        },
    )
    gate.client_approval = approval
    gate.client_pack_reference = approval.reference
    gate.readiness_messages = readiness_messages
    if signoff and not readiness_messages:
        gate.practice_signed_off = True
        gate.practice_signed_off_by = username
        gate.practice_signed_off_at = timezone.now()
    gate.status = (
        CompaniesHouseApprovalGate.STATUS_SIGNED_OFF
        if gate.practice_signed_off and not readiness_messages
        else CompaniesHouseApprovalGate.STATUS_READY
        if not readiness_messages
        else CompaniesHouseApprovalGate.STATUS_BLOCKED
    )
    gate.test_mode_only = companies_house_status()["test_mode_only"]
    gate.save(
        update_fields=[
            "client_approval",
            "client_pack_reference",
            "readiness_messages",
            "practice_signed_off",
            "practice_signed_off_by",
            "practice_signed_off_at",
            "status",
            "test_mode_only",
            "updated_at",
        ]
    )
    return gate


def build_companies_house_accounts_submission_xml(
    statutory_accounts,
    company_number,
    company_name,
    company_authentication_code,
    submission_number,
):
    _require_supported_initial_accounts_type(statutory_accounts)
    credentials = companies_house_filing_credentials()
    if not credentials["configured"]:
        raise CompaniesHouseApiError(0, "Companies House filing credentials are not configured.")
    filing_number = _filing_company_number(company_number)
    ixbrl = generate_micro_entity_ixbrl(statutory_accounts, filing_number, company_name)
    draft = {"_submission_number": submission_number, "ixbrl": ixbrl}
    form_submission = _form_submission_element(
        credentials,
        draft,
        filing_number,
        company_name,
        company_authentication_code,
    )
    return _govtalk_envelope(credentials, submission_number, form_submission, message_class="Accounts")


def validate_companies_house_filing_readiness(statutory_accounts):
    messages = []
    if statutory_accounts.accounts_type not in INITIAL_ACCOUNTS_FILING_TYPES | set(INITIAL_ACCOUNTS_FILING_TYPE_ALIASES):
        messages.append(
            f"Accounts type '{statutory_accounts.accounts_type}' is outside LedgerHouse's declared initial Companies House filing scope."
        )
    if not statutory_accounts.client_approved:
        messages.append("Client approval is required before Companies House test filing.")
    if statutory_accounts.status != statutory_accounts.STATUS_READY_FOR_FILING:
        messages.append("Statutory accounts draft must be marked Ready for filing.")
    if not statutory_accounts.ixbrl_ready:
        messages.append("Valid XHTML/iXBRL accounts must be produced and validator-checked before gateway submission.")
    return messages


def _create_companies_house_submission_record(
    statutory_accounts,
    company_number,
    company_name,
    company_authentication_code,
    created_by="",
):
    from .models import CompaniesHouseFilingSubmission

    _require_supported_initial_accounts_type(statutory_accounts)
    credentials = companies_house_filing_credentials()
    submission_number = next_companies_house_submission_number(credentials["product_key"])
    request_xml = build_companies_house_accounts_submission_xml(
        statutory_accounts,
        company_number,
        company_name,
        company_authentication_code,
        submission_number,
    )
    readiness_messages = validate_companies_house_filing_readiness(statutory_accounts)
    ixbrl_text = generate_micro_entity_ixbrl(
        statutory_accounts,
        _filing_company_number(company_number),
        company_name,
    )
    ixbrl_validation = validate_micro_entity_ixbrl(
        ixbrl_text,
        statutory_accounts,
        _filing_company_number(company_number),
    )
    if not ixbrl_validation.passed:
        readiness_messages.extend(ixbrl_validation.messages)
    company_authentication_hint = (
        f"ends {company_authentication_code[-2:]}" if company_authentication_code else "not supplied"
    )
    return CompaniesHouseFilingSubmission.objects.create(
        tenant=statutory_accounts.tenant,
        statutory_accounts=statutory_accounts,
        product_key=credentials["product_key"],
        submission_number=submission_number,
        company_number=_filing_company_number(company_number),
        company_name=company_name[:160],
        form_identifier="Accounts",
        package_reference=credentials["package_reference"],
        gateway_test=int(credentials["test_flag"] or 1),
        company_authentication_hint=company_authentication_hint,
        status=CompaniesHouseFilingSubmission.STATUS_PREPARED,
        request_xml_sanitised=sanitise_companies_house_xml(request_xml),
        validation_messages=readiness_messages,
        created_by=created_by,
    )


@transaction.atomic
def prepare_companies_house_test_submission(
    statutory_accounts,
    company_number,
    company_name,
    company_authentication_code,
    created_by="",
):
    return _create_companies_house_submission_record(
        statutory_accounts,
        company_number,
        company_name,
        company_authentication_code,
        created_by=created_by,
    )


def submit_companies_house_test_submission(
    statutory_accounts,
    company_number,
    company_name,
    company_authentication_code,
    created_by="",
):
    credentials = companies_house_filing_credentials()
    if credentials["test_flag"] != "1":
        raise CompaniesHouseApiError(
            0,
            "Companies House test submission refused because the configured credentials are for live filing.",
        )
    if not credentials["send_enabled"]:
        raise CompaniesHouseApiError(
            0,
            "Companies House test sending is locked. Review the local evidence pack before explicitly enabling a controlled test run.",
        )
    request_xml = ""
    with transaction.atomic():
        submission = _create_companies_house_submission_record(
            statutory_accounts,
            company_number,
            company_name,
            company_authentication_code,
            created_by=created_by,
        )
        if submission.validation_messages:
            submission.status = submission.STATUS_FAILED
            submission.save(update_fields=["status", "updated_at"])
            return submission
        request_xml = build_companies_house_accounts_submission_xml(
            statutory_accounts,
            company_number,
            company_name,
            company_authentication_code,
            submission.submission_number,
        )

    try:
        _status_code, response_xml = _gateway_request(request_xml)
        gateway_status, gateway_messages = parse_companies_house_gateway_status(response_xml)
        submission.status = gateway_status
        submission.response_xml = sanitise_companies_house_xml(response_xml)
        submission.validation_messages = gateway_messages
        submission.submitted_at = timezone.now()
        submission.save(
            update_fields=[
                "status",
                "response_xml",
                "validation_messages",
                "submitted_at",
                "updated_at",
            ]
        )
    except CompaniesHouseApiError as exc:
        submission.status = submission.STATUS_FAILED
        response_xml = (exc.payload or {}).get("body", "")
        if response_xml:
            submission.response_xml = sanitise_companies_house_xml(response_xml)
        submission.validation_messages = [str(exc)]
        submission.submitted_at = timezone.now()
        submission.save(
            update_fields=[
                "status",
                "response_xml",
                "validation_messages",
                "submitted_at",
                "updated_at",
            ]
        )
    return submission


def submit_companies_house_live_submission(
    statutory_accounts,
    company_number,
    company_name,
    company_authentication_code,
    created_by="",
):
    """Send one authorised live filing only after every production gate is explicit."""
    credentials = companies_house_filing_credentials()
    if credentials["test_flag"] != "0":
        raise CompaniesHouseApiError(0, "Companies House live submission refused because the configured credentials are for test filing.")
    if not getattr(settings, "COMPANIES_HOUSE_LIVE_APPROVAL_CONFIRMED", False):
        raise CompaniesHouseApiError(0, "Companies House live submission is blocked until written approval is recorded in production configuration.")
    if not getattr(settings, "COMPANIES_HOUSE_FILING_LIVE_ENABLED", False):
        raise CompaniesHouseApiError(0, "Companies House live submission is locked until the release manager enables production filing.")
    if not credentials["send_enabled"]:
        raise CompaniesHouseApiError(0, "Companies House live submission is locked. Enable sending only for a controlled authorised filing.")
    if not company_authentication_code or not created_by:
        raise CompaniesHouseApiError(0, "Companies House live submission requires a client authentication code and an identified authorised operator.")

    request_xml = ""
    with transaction.atomic():
        submission = _create_companies_house_submission_record(
            statutory_accounts,
            company_number,
            company_name,
            company_authentication_code,
            created_by=created_by,
        )
        if submission.validation_messages:
            submission.status = submission.STATUS_FAILED
            submission.save(update_fields=["status", "updated_at"])
            return submission
        request_xml = build_companies_house_accounts_submission_xml(
            statutory_accounts,
            company_number,
            company_name,
            company_authentication_code,
            submission.submission_number,
        )

    try:
        _status_code, response_xml = _gateway_request(request_xml)
        gateway_status, gateway_messages = parse_companies_house_gateway_status(response_xml)
        submission.status = gateway_status
        submission.response_xml = sanitise_companies_house_xml(response_xml)
        submission.validation_messages = gateway_messages
    except CompaniesHouseApiError as exc:
        submission.status = submission.STATUS_FAILED
        response_xml = (exc.payload or {}).get("body", "")
        if response_xml:
            submission.response_xml = sanitise_companies_house_xml(response_xml)
        submission.validation_messages = [str(exc)]
    submission.submitted_at = timezone.now()
    submission.save(
        update_fields=["status", "response_xml", "validation_messages", "submitted_at", "updated_at"]
    )
    return submission


def poll_companies_house_submission_status(submission, username="practice"):
    if not submission.submission_number:
        raise CompaniesHouseApiError(0, "Submission number is missing.")
    request_xml = build_get_submission_status_xml(submission.submission_number)
    _status_code, response_xml = _gateway_request(request_xml)
    gateway_status, gateway_messages = parse_companies_house_gateway_status(response_xml)
    submission.status = gateway_status
    submission.response_xml = sanitise_companies_house_xml(response_xml)
    submission.validation_messages = gateway_messages
    submission.save(update_fields=["status", "response_xml", "validation_messages", "updated_at"])

    from .models import AuditEvent, CompaniesHouseSubmissionPoll

    CompaniesHouseSubmissionPoll.objects.create(
        tenant=submission.tenant,
        submission=submission,
        submission_number=submission.submission_number,
        status=gateway_status,
        response_xml=sanitise_companies_house_xml(response_xml),
        messages=gateway_messages,
        polled_by=username,
    )

    AuditEvent.objects.create(
        tenant=submission.tenant,
        event_type="CompaniesHouseStatusPolled",
        username=username,
        description=f"Companies House submission {submission.submission_number:06d} status polled: {gateway_status}.",
        details={
            "submission_number": f"{submission.submission_number:06d}",
            "status": gateway_status,
            "message_count": len(gateway_messages),
        },
    )
    return submission


def build_get_submission_status_xml(submission_number=None):
    credentials = companies_house_filing_credentials()
    if not credentials["configured"]:
        raise CompaniesHouseApiError(0, "Companies House filing credentials are not configured.")
    ns = "http://xmlgw.companieshouse.gov.uk"
    request = ET.Element(f"{{{ns}}}GetSubmissionStatus")
    ET.SubElement(request, f"{{{ns}}}PresenterID").text = credentials["presenter_id"]
    if submission_number:
        ET.SubElement(request, f"{{{ns}}}SubmissionNumber").text = format_submission_number(submission_number)
    return _govtalk_envelope(credentials, submission_number or 1, request, message_class="GetSubmissionStatus")
