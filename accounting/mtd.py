import uuid
import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.db import transaction
from accounting.models import VatReturn, JournalLine


VAT_MTD_SCOPE = "read:vat write:vat"


class HmrcApiError(RuntimeError):
    """Raised when HMRC returns a non-success response."""

    def __init__(self, status_code, message, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def hmrc_sandbox_status():
    """Return non-secret HMRC sandbox readiness details for the practice UI."""
    required = {
        "client_id": bool(settings.HMRC_CLIENT_ID),
        "client_secret": bool(settings.HMRC_CLIENT_SECRET),
        "redirect_uri": bool(settings.HMRC_REDIRECT_URI),
        "vat_scopes": "read:vat" in settings.HMRC_SCOPES and "write:vat" in settings.HMRC_SCOPES,
    }
    return {
        "environment": settings.HMRC_ENVIRONMENT,
        "api_base_url": settings.HMRC_API_BASE_URL,
        "redirect_uri": settings.HMRC_REDIRECT_URI,
        "configured": all(required.values()),
        "required": required,
        "subscribed_apis": ["VAT (MTD) 1.0", "Test Fraud Prevention Headers 1.0"],
    }


def build_hmrc_authorisation_url(next_url="/practice/"):
    """Build the OAuth URL for HMRC VAT MTD user authorisation."""
    if not settings.HMRC_CLIENT_ID:
        raise ValueError("HMRC_CLIENT_ID is not configured.")
    state = signing.dumps({"next": next_url, "ts": timezone.now().isoformat()}, salt="hmrc-oauth")
    params = {
        "response_type": "code",
        "client_id": settings.HMRC_CLIENT_ID,
        "scope": settings.HMRC_SCOPES or VAT_MTD_SCOPE,
        "redirect_uri": settings.HMRC_REDIRECT_URI,
        "state": state,
    }
    return f"{settings.HMRC_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def unpack_hmrc_state(state):
    return signing.loads(state, salt="hmrc-oauth", max_age=3600)


def exchange_hmrc_authorisation_code(code):
    """Exchange an HMRC OAuth authorisation code for tokens."""
    if not settings.HMRC_CLIENT_ID:
        raise ValueError("HMRC_CLIENT_ID is not configured.")
    if not settings.HMRC_CLIENT_SECRET:
        raise ValueError("HMRC_CLIENT_SECRET is not configured.")

    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": settings.HMRC_CLIENT_ID,
            "client_secret": settings.HMRC_CLIENT_SECRET,
            "redirect_uri": settings.HMRC_REDIRECT_URI,
            "code": code,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        settings.HMRC_TOKEN_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def build_desktop_fraud_prevention_headers(device_id, public_ip="127.0.0.1"):
    """
    Build baseline fraud prevention headers for local sandbox requests.

    These values are only suitable for development diagnostics; production
    header collection must reflect the real customer device and connection.
    """
    return {
        "Gov-Client-Connection-Method": "DESKTOP_APP_DIRECT",
        "Gov-Client-Device-ID": device_id,
        "Gov-Client-Public-IP": public_ip,
        "Gov-Client-Timezone": "+00:00",
        "Gov-Client-User-Agent": "LedgerHouse/local-sandbox",
        "Gov-Vendor-Version": "LedgerHouse=local",
    }


def _hmrc_json_request(url, access_token, method="GET", payload=None, headers=None):
    request_headers = {
        "Accept": "application/vnd.hmrc.1.0+json",
        "Authorization": f"Bearer {access_token}",
        **(headers or {}),
    }
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
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
        message = error_payload.get("message") or error_payload.get("code") or str(exc)
        raise HmrcApiError(exc.code, message, error_payload) from exc


def retrieve_vat_obligations(access_token, vrn, from_date, to_date, device_id, public_ip="127.0.0.1"):
    params = urllib.parse.urlencode({"from": from_date, "to": to_date})
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/obligations?{params}"
    response = _hmrc_json_request(
        url,
        access_token,
        headers=build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"].get("obligations", [])


def retrieve_vat_return(access_token, vrn, period_key, device_id, public_ip="127.0.0.1"):
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/returns/{period_key}"
    response = _hmrc_json_request(
        url,
        access_token,
        headers=build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"]


def submit_vat_return_payload(access_token, vrn, payload, device_id, public_ip="127.0.0.1"):
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/returns"
    response = _hmrc_json_request(
        url,
        access_token,
        method="POST",
        payload=payload,
        headers=build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"]

class MockHMRCClient:
    """Mock client simulating HMRC's MTD for VAT submission endpoint."""
    @staticmethod
    def submit_vat_return(payload):
        # In a real system, this would make an authenticated OAuth2 POST request to:
        # https://api.service.hmrc.gov.uk/organisations/vat/{vrn}/returns
        # Returns mock response indicating successful submission.
        receipt_id = f"HMRC-REC-{uuid.uuid4().hex[:12].upper()}"
        return {
            "status": "success",
            "receipt_id": receipt_id,
            "processingDate": timezone.now().isoformat(),
            "paymentIndicator": "BANK" if payload["netVatDue"] > 0 else "DD",
            "chargeRefNumber": f"CHARGEREF{uuid.uuid4().hex[:8].upper()}"
        }


def serialize_vat_return_9_box(tenant, start_date, end_date):
    """
    Serializes the UK 9-Box VAT return values from the ledger:
    - Box 1: VAT due on sales (Output VAT)
    - Box 2: VAT due on acquisitions from EU (0.00 for Phase 1)
    - Box 3: Total VAT due (Box 1 + Box 2)
    - Box 4: VAT reclaimed on purchases (Input VAT)
    - Box 5: Net VAT to pay or reclaim (Box 3 - Box 4)
    - Box 6: Total value of sales (net sales total)
    - Box 7: Total value of purchases (net purchases total)
    - Box 8: Total value of EU sales (0.00)
    - Box 9: Total value of EU purchases (0.00)
    """
    # Box 1: Output VAT
    sales_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SalesInvoice", "SalesCreditNote"]
    )
    box1 = Decimal("0.00")
    for line in sales_lines:
        if line.account.code == "2200":
            box1 += (line.credit - line.debit)

    # Box 2: EU acquisitions
    box2 = Decimal("0.00")

    # Box 3: Total VAT due
    box3 = box1 + box2

    # Box 4: Input VAT
    purchase_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SupplierInvoice", "EmployeeExpense"]
    )
    box4 = Decimal("0.00")
    for line in purchase_lines:
        if line.account.code == "2200":
            box4 += (line.debit - line.credit)

    # Box 5: Net VAT due/reclaimable
    box5 = abs(box3 - box4)

    # Box 6: Net Sales (Credits starting with 4 - Debits starting with 4)
    revenue_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="4",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    )
    box6 = sum(line.credit - line.debit for line in revenue_lines)

    # Box 7: Net Purchases (Debits starting with 5 or 6 - Credits starting with 5 or 6)
    expense_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="5",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    ) | JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="6",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    )
    box7 = sum(line.debit - line.credit for line in expense_lines)

    box8 = Decimal("0.00")
    box9 = Decimal("0.00")

    return {
        "periodKey": "26A1",  # Mock period key
        "vatDueOnOutputs": float(round(box1, 2)),
        "vatDueAcquisitions": float(round(box2, 2)),
        "totalVatDue": float(round(box3, 2)),
        "vatReclaimedCurrPeriod": float(round(box4, 2)),
        "netVatDue": float(round(box5, 2)),
        "totalValueSalesExVAT": float(round(box6, 2)),
        "totalValuePurchasesExVAT": float(round(box7, 2)),
        "totalValueGoodsSuppliedExVAT": float(round(box8, 2)),
        "totalValueGoodsAcquisitionsExVAT": float(round(box9, 2)),
        "finalised": True
    }


def submit_vat_return_to_hmrc(tenant, vat_return, period_key="26A1"):
    """
    Submits a finalized/locked VAT Return to the mock HMRC gateway.
    Updates the VatReturn record with receipt details.
    """
    if vat_return.status == "Submitted":
        raise ValueError("VAT Return has already been submitted to HMRC.")

    payload = serialize_vat_return_9_box(tenant, vat_return.start_date, vat_return.end_date)
    payload["periodKey"] = period_key

    client = MockHMRCClient()
    response = client.submit_vat_return(payload)

    with transaction.atomic():
        vat_return.status = "Submitted"
        vat_return.hmrc_receipt_id = response["receipt_id"]
        vat_return.submitted_at = datetime.fromisoformat(response["processingDate"])
        vat_return.period_key = period_key
        vat_return.save()

    return response
