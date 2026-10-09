import json
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from .models import HmrcFilingCase, HmrcServiceApproval
from .hmrc_income_tax import income_tax_subscription_status


@dataclass(frozen=True)
class HmrcServiceDefinition:
    code: str
    name: str
    transport: str
    documentation_url: str
    filing_types: tuple[str, ...]
    description: str
    default_status: str


HMRC_SERVICES = {
    HmrcServiceApproval.SERVICE_VAT_MTD: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_VAT_MTD,
        name="VAT (Making Tax Digital)",
        transport=HmrcServiceApproval.TRANSPORT_REST_OAUTH,
        documentation_url="https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/vat-api/1.0",
        filing_types=("VAT_RETURN",),
        description="VAT obligations, returns and liabilities using taxpayer-authorised REST APIs.",
        default_status=HmrcServiceApproval.STATUS_CREDENTIALS_REQUESTED,
    ),
    HmrcServiceApproval.SERVICE_CORPORATION_TAX: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_CORPORATION_TAX,
        name="Corporation Tax Online",
        transport=HmrcServiceApproval.TRANSPORT_XML_GATEWAY,
        documentation_url="https://developer.service.hmrc.gov.uk/api-documentation/docs/api/xml/Corporation%20Tax%20Online",
        filing_types=("CT600", "CT600_AMENDMENT"),
        description="Company tax returns and amendments using the HMRC XML gateway.",
        default_status=HmrcServiceApproval.STATUS_DEVELOPMENT,
    ),
    HmrcServiceApproval.SERVICE_PAYE_RTI: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_PAYE_RTI,
        name="PAYE Online / RTI",
        transport=HmrcServiceApproval.TRANSPORT_XML_GATEWAY,
        documentation_url="https://developer.service.hmrc.gov.uk/api-documentation/docs/api/xml/PAYE%20Online",
        filing_types=("FPS", "EPS"),
        description="Full Payment Submissions and Employer Payment Summaries using the HMRC XML gateway.",
        default_status=HmrcServiceApproval.STATUS_DEVELOPMENT,
    ),
    HmrcServiceApproval.SERVICE_CIS: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_CIS,
        name="Construction Industry Scheme Online",
        transport=HmrcServiceApproval.TRANSPORT_XML_GATEWAY,
        documentation_url="https://developer.service.hmrc.gov.uk/api-documentation/docs/api/xml/Construction%20Industry%20Scheme%20Online",
        filing_types=("CIS300",),
        description="Subcontractor verification and monthly CIS returns using the HMRC XML gateway.",
        default_status=HmrcServiceApproval.STATUS_DEVELOPMENT,
    ),
    HmrcServiceApproval.SERVICE_INCOME_TAX_MTD: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_INCOME_TAX_MTD,
        name="Income Tax (Making Tax Digital)",
        transport=HmrcServiceApproval.TRANSPORT_REST_OAUTH,
        documentation_url="https://developer.service.hmrc.gov.uk/guides/income-tax-mtd-end-to-end-service-guide/",
        filing_types=("QUARTERLY_UPDATE", "ANNUAL_SUMMARY"),
        description="Business income, expenses, adjustments and finalisation using taxpayer-authorised REST APIs.",
        default_status=HmrcServiceApproval.STATUS_DEVELOPMENT,
    ),
    HmrcServiceApproval.SERVICE_SELF_ASSESSMENT: HmrcServiceDefinition(
        code=HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
        name="Self Assessment Online",
        transport=HmrcServiceApproval.TRANSPORT_XML_GATEWAY,
        documentation_url="https://developer.service.hmrc.gov.uk/api-documentation/docs/api/xml/Self%20Assessment%20Online",
        filing_types=("SA100", "SA800", "SA900"),
        description="Individual, partnership and trust returns using the HMRC XML gateway.",
        default_status=HmrcServiceApproval.STATUS_DEVELOPMENT,
    ),
}


class HmrcSubmissionBlocked(RuntimeError):
    pass


def ensure_hmrc_service_approvals():
    approvals = []
    for definition in HMRC_SERVICES.values():
        defaults = {
            "transport": definition.transport,
            "application_name": "LedgerHouse",
            "status": definition.default_status,
        }
        approval, _ = HmrcServiceApproval.objects.get_or_create(service=definition.code, defaults=defaults)
        changed = False
        if approval.transport != definition.transport:
            approval.transport = definition.transport
            changed = True
        if changed:
            approval.save(update_fields=["transport", "updated_at"])
        approvals.append(approval)
    return approvals


def get_case_payload(case):
    if not case.encrypted_payload:
        return {}
    try:
        payload = json.loads(case.encrypted_payload)
    except json.JSONDecodeError as exc:
        raise ValueError("The stored HMRC filing payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("The stored HMRC filing payload must be a JSON object.")
    return payload


def set_case_payload(case, payload):
    if not isinstance(payload, dict):
        raise ValueError("HMRC filing payload must be a dictionary.")
    case.encrypted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _required(payload, fields):
    errors = []
    for field, label in fields:
        value = payload.get(field)
        if value is None or value == "" or value == []:
            errors.append(f"{label} is required.")
    return errors


def _digits(value, length, label):
    if not re.fullmatch(rf"\d{{{length}}}", str(value or "")):
        return [f"{label} must contain exactly {length} digits."]
    return []


def _money(value, label, allow_negative=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return [f"{label} must be a valid monetary amount."]
    if not allow_negative and amount < 0:
        return [f"{label} cannot be negative."]
    if amount.as_tuple().exponent < -2:
        return [f"{label} cannot have more than two decimal places."]
    return []


def _validate_ct600(payload):
    errors = _required(
        payload,
        (
            ("company_tax_reference", "Corporation Tax UTR"),
            ("company_number", "Company number"),
            ("accounting_period_start", "Accounting period start"),
            ("accounting_period_end", "Accounting period end"),
            ("taxable_profit", "Taxable profit"),
            ("corporation_tax_due", "Corporation Tax due"),
            ("accounts_ixbrl_ready", "iXBRL accounts confirmation"),
            ("computations_ixbrl_ready", "iXBRL computations confirmation"),
        ),
    )
    errors += _digits(payload.get("company_tax_reference"), 10, "Corporation Tax UTR")
    for field, label in (("taxable_profit", "Taxable profit"), ("corporation_tax_due", "Corporation Tax due")):
        errors += _money(payload.get(field), label)
    if payload.get("accounts_ixbrl_ready") is not True:
        errors.append("Statutory accounts must be available as validated iXBRL.")
    if payload.get("computations_ixbrl_ready") is not True:
        errors.append("Tax computations must be available as validated iXBRL.")
    return errors


def _validate_fps(payload):
    errors = _required(
        payload,
        (
            ("paye_reference", "PAYE reference"),
            ("accounts_office_reference", "Accounts Office reference"),
            ("payment_date", "Payment date"),
            ("employees", "Employee payment records"),
        ),
    )
    employees = payload.get("employees") or []
    if not isinstance(employees, list):
        return errors + ["Employee payment records must be a list."]
    for index, employee in enumerate(employees, start=1):
        if not isinstance(employee, dict):
            errors.append(f"Employee {index} must be an object.")
            continue
        errors += [
            f"Employee {index}: {message}"
            for message in _required(
                employee,
                (
                    ("payroll_id", "payroll ID"),
                    ("taxable_pay", "taxable pay"),
                    ("paye_tax", "PAYE tax"),
                    ("employee_ni", "employee National Insurance"),
                ),
            )
        ]
        for field, label in (
            ("taxable_pay", "taxable pay"),
            ("paye_tax", "PAYE tax"),
            ("employee_ni", "employee National Insurance"),
        ):
            errors += [f"Employee {index}: {message}" for message in _money(employee.get(field), label)]
    return errors


def _validate_eps(payload):
    errors = _required(
        payload,
        (
            ("paye_reference", "PAYE reference"),
            ("accounts_office_reference", "Accounts Office reference"),
            ("tax_year", "Tax year"),
            ("tax_month", "Tax month"),
        ),
    )
    try:
        tax_month = int(payload.get("tax_month"))
        if tax_month < 1 or tax_month > 12:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Tax month must be between 1 and 12.")
    return errors


def _validate_cis300(payload):
    errors = _required(
        payload,
        (
            ("paye_reference", "PAYE reference"),
            ("tax_year", "Tax year"),
            ("tax_month", "Tax month"),
            ("subcontractors", "Subcontractor payment records"),
        ),
    )
    subcontractors = payload.get("subcontractors") or []
    if not isinstance(subcontractors, list):
        return errors + ["Subcontractor payment records must be a list."]
    for index, subcontractor in enumerate(subcontractors, start=1):
        errors += [
            f"Subcontractor {index}: {message}"
            for message in _required(
                subcontractor,
                (("utr", "UTR"), ("gross_payment", "gross payment"), ("deduction", "deduction")),
            )
        ]
        errors += [f"Subcontractor {index}: {message}" for message in _digits(subcontractor.get("utr"), 10, "UTR")]
        for field, label in (("gross_payment", "gross payment"), ("deduction", "deduction")):
            errors += [f"Subcontractor {index}: {message}" for message in _money(subcontractor.get(field), label)]
    return errors


def _validate_income_tax_mtd(payload):
    errors = _required(
        payload,
        (
            ("nino", "National Insurance number"),
            ("business_id", "HMRC business ID"),
            ("tax_year", "Tax year"),
            ("period_start", "Period start"),
            ("period_end", "Period end"),
            ("income", "Income"),
            ("expenses", "Expenses"),
        ),
    )
    for field, label in (("income", "Income"), ("expenses", "Expenses")):
        errors += _money(payload.get(field), label)
    return errors


def _validate_self_assessment(payload):
    errors = _required(
        payload,
        (("utr", "Self Assessment UTR"), ("tax_year", "Tax year"), ("declaration", "Taxpayer declaration")),
    )
    errors += _digits(payload.get("utr"), 10, "Self Assessment UTR")
    if payload.get("declaration") is not True:
        errors.append("The taxpayer declaration must be confirmed before filing.")
    return errors


VALIDATORS = {
    (HmrcServiceApproval.SERVICE_CORPORATION_TAX, "CT600"): _validate_ct600,
    (HmrcServiceApproval.SERVICE_CORPORATION_TAX, "CT600_AMENDMENT"): _validate_ct600,
    (HmrcServiceApproval.SERVICE_PAYE_RTI, "FPS"): _validate_fps,
    (HmrcServiceApproval.SERVICE_PAYE_RTI, "EPS"): _validate_eps,
    (HmrcServiceApproval.SERVICE_CIS, "CIS300"): _validate_cis300,
    (HmrcServiceApproval.SERVICE_INCOME_TAX_MTD, "QUARTERLY_UPDATE"): _validate_income_tax_mtd,
    (HmrcServiceApproval.SERVICE_INCOME_TAX_MTD, "ANNUAL_SUMMARY"): _validate_income_tax_mtd,
    (HmrcServiceApproval.SERVICE_SELF_ASSESSMENT, "SA100"): _validate_self_assessment,
    (HmrcServiceApproval.SERVICE_SELF_ASSESSMENT, "SA800"): _validate_self_assessment,
    (HmrcServiceApproval.SERVICE_SELF_ASSESSMENT, "SA900"): _validate_self_assessment,
}


def validate_hmrc_filing_case(case):
    if case.period_end < case.period_start:
        return ["The filing period end must not be earlier than its start date."], []
    definition = HMRC_SERVICES.get(case.service)
    if not definition:
        return ["The selected HMRC service is not supported by LedgerHouse."], []
    if case.filing_type not in definition.filing_types:
        return [f"{case.filing_type} is not a supported filing type for {definition.name}."], []
    if case.service == HmrcServiceApproval.SERVICE_VAT_MTD:
        return ["VAT returns must use the existing VAT review and HMRC VAT workspace."], []
    try:
        payload = get_case_payload(case)
    except ValueError as exc:
        return [str(exc)], []
    validator = VALIDATORS.get((case.service, case.filing_type))
    if not validator:
        return ["No validated filing profile is registered for this filing type."], []
    warnings = [
        "Local preflight validates LedgerHouse data only; HMRC schema or sandbox acceptance is still required.",
    ]
    return validator(payload), warnings


@transaction.atomic
def run_hmrc_filing_preflight(case):
    locked_case = HmrcFilingCase.objects.select_for_update().get(pk=case.pk)
    errors, warnings = validate_hmrc_filing_case(locked_case)
    locked_case.validation_errors = errors
    locked_case.validation_warnings = warnings
    locked_case.status = (
        HmrcFilingCase.STATUS_VALIDATION_FAILED if errors else HmrcFilingCase.STATUS_READY_FOR_APPROVAL
    )
    locked_case.save(update_fields=["validation_errors", "validation_warnings", "status", "updated_at"])
    return locked_case


def submission_blockers(case, approval, environment):
    blockers = list(case.validation_errors)
    if case.status != HmrcFilingCase.STATUS_APPROVED_TO_FILE:
        blockers.append("The filing case has not completed client and practice approval.")
    if not case.approvals_complete:
        blockers.append("Both client and practice approval are required.")
    if environment == "production" and not approval.live_ready:
        blockers.append("HMRC production approval, verified credentials and an explicit live enablement are required.")
    if environment not in {"sandbox", "production"}:
        blockers.append("The HMRC environment must be sandbox or production.")
    return blockers


def submit_hmrc_filing_case(case, approval, environment):
    blockers = submission_blockers(case, approval, environment)
    if blockers:
        raise HmrcSubmissionBlocked(" ".join(blockers))
    definition = HMRC_SERVICES[case.service]
    raise HmrcSubmissionBlocked(
        f"{definition.name} transport is locked until its official HMRC test pack or sandbox route has passed."
    )


@transaction.atomic
def record_hmrc_provider_result(case, result, *, verified_transport=False):
    """Record a parsed provider result without trusting caller-supplied success."""
    if not verified_transport:
        raise HmrcSubmissionBlocked("Only a verified HMRC transport response may change a filing status.")
    if not isinstance(result, dict):
        raise ValueError("The HMRC provider result must be a dictionary.")
    provider_status = result.get("status")
    if provider_status not in {"pending", "accepted", "rejected"}:
        raise ValueError("The HMRC provider result does not contain a recognised status.")

    locked_case = HmrcFilingCase.objects.select_for_update().get(pk=case.pk)
    if locked_case.status in {HmrcFilingCase.STATUS_ACCEPTED, HmrcFilingCase.STATUS_REJECTED}:
        existing = json.loads(locked_case.provider_response or "{}")
        if existing == result:
            return locked_case
        raise HmrcSubmissionBlocked("A final HMRC filing decision cannot be overwritten.")

    correlation_id = str(result.get("correlation_id") or "")
    if provider_status == "pending" and not correlation_id:
        raise ValueError("A pending HMRC response must include a correlation ID.")
    if provider_status == "accepted" and result.get("errors"):
        raise ValueError("An accepted HMRC response cannot contain provider errors.")
    if provider_status == "rejected" and not result.get("errors"):
        raise ValueError("A rejected HMRC response must include provider errors.")

    now = timezone.now()
    locked_case.provider_response = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if correlation_id:
        locked_case.provider_correlation_id = correlation_id
    if provider_status == "pending":
        locked_case.status = HmrcFilingCase.STATUS_SUBMITTED
        locked_case.submitted_at = locked_case.submitted_at or now
    elif provider_status == "accepted":
        locked_case.status = HmrcFilingCase.STATUS_ACCEPTED
        locked_case.submitted_at = locked_case.submitted_at or now
        locked_case.decided_at = now
        receipt_source = str(result.get("receipt_id") or correlation_id or locked_case.idempotency_key)
        locked_case.provider_receipt_id = hashlib.sha256(receipt_source.encode("utf-8")).hexdigest()
    else:
        locked_case.status = HmrcFilingCase.STATUS_REJECTED
        locked_case.submitted_at = locked_case.submitted_at or now
        locked_case.decided_at = now
    locked_case.save(update_fields=[
        "provider_response", "provider_correlation_id", "provider_receipt_id",
        "status", "submitted_at", "decided_at", "updated_at",
    ])
    return locked_case


def build_hmrc_application_evidence(output_path):
    """Write a redacted service-level evidence register without taxpayer data."""
    approvals = {item.service: item for item in ensure_hmrc_service_approvals()}
    lines = [
        "# LedgerHouse HMRC Application Evidence Register",
        "",
        "This report excludes credentials, tokens, taxpayer references, filing payloads and provider responses.",
        "Local preflight is not HMRC approval or provider acceptance.",
        "",
    ]
    for definition in HMRC_SERVICES.values():
        approval = approvals[definition.code]
        cases = HmrcFilingCase.objects.filter(service=definition.code)
        passed = cases.filter(status__in=[
            HmrcFilingCase.STATUS_READY_FOR_APPROVAL,
            HmrcFilingCase.STATUS_APPROVED_TO_FILE,
        ]).count()
        failed = cases.filter(status=HmrcFilingCase.STATUS_VALIDATION_FAILED).count()
        submitted = cases.filter(status__in=[
            HmrcFilingCase.STATUS_SUBMITTED,
            HmrcFilingCase.STATUS_ACCEPTED,
            HmrcFilingCase.STATUS_REJECTED,
        ]).count()
        lines.extend(
            [
                f"## {definition.name}",
                "",
                f"- Transport: {approval.get_transport_display()}",
                f"- Filing types: {', '.join(definition.filing_types)}",
                f"- Approval status: {approval.get_status_display()}",
                f"- Credentials requested: {approval.credentials_requested_at.isoformat() if approval.credentials_requested_at else 'Not recorded'}",
                f"- Credentials verified: {'Yes' if approval.credentials_verified_at else 'No'}",
                f"- Live submission enabled: {'Yes' if approval.live_submission_enabled else 'No'}",
                f"- Local cases passing preflight: {passed}",
                f"- Local cases with blockers: {failed}",
                f"- Provider-result cases: {submitted}",
                f"- Official documentation: {definition.documentation_url}",
                "",
            ]
        )
        if definition.code == HmrcServiceApproval.SERVICE_INCOME_TAX_MTD:
            lines.extend(["### API subscription coverage", ""])
            for item in income_tax_subscription_status():
                state = "Subscribed" if item["subscribed"] else ("Required" if item["required"] else "Optional")
                lines.append(f"- {item['name']} {item['version']} ({item['stage']}): {state}")
            lines.append("")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
