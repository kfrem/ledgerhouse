import json
import hashlib
import socket
import urllib.parse
import urllib.request
import urllib.error
from decimal import Decimal
from django.conf import settings
from django.core import signing
from django.utils import timezone
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
    application_isolation = (
        settings.HMRC_APPLICATION_NAME == "LedgerHouse"
        and settings.HMRC_APPLICATION_OWNER == "LedgerHouse"
    )
    required = {
        "ledgerhouse_application": application_isolation,
        "client_id": bool(settings.HMRC_CLIENT_ID),
        "client_secret": bool(settings.HMRC_CLIENT_SECRET),
        "redirect_uri": bool(settings.HMRC_REDIRECT_URI),
        "vat_scopes": "read:vat" in settings.HMRC_SCOPES and "write:vat" in settings.HMRC_SCOPES,
        "vat_subscription": "VAT (MTD) 1.0" in settings.HMRC_SUBSCRIBED_APIS,
    }
    return {
        "application_name": settings.HMRC_APPLICATION_NAME,
        "environment": settings.HMRC_ENVIRONMENT,
        "api_base_url": settings.HMRC_API_BASE_URL,
        "redirect_uri": settings.HMRC_REDIRECT_URI,
        "configured": all(required.values()),
        "required": required,
        "subscribed_apis": settings.HMRC_SUBSCRIBED_APIS,
    }


def build_hmrc_authorisation_url(next_url="/practice/"):
    """Build the OAuth URL for HMRC VAT MTD user authorisation."""
    if not hmrc_sandbox_status()["configured"]:
        raise ValueError(
            "LedgerHouse's own HMRC sandbox VAT configuration is incomplete. "
            "Shared application credentials are not accepted."
        )
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


def _decode_hmrc_json(raw_body, *, status_code=502):
    try:
        return json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HmrcApiError(
            status_code,
            "HMRC returned a response that LedgerHouse could not read.",
        ) from exc


def _exchange_hmrc_token(body):
    request = urllib.request.Request(
        settings.HMRC_TOKEN_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = _decode_hmrc_json(response.read())
    except urllib.error.HTTPError as exc:
        payload = _decode_hmrc_json(exc.read(), status_code=exc.code)
        raise HmrcApiError(
            exc.code,
            "HMRC rejected the token request.",
            payload,
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise HmrcApiError(
            503,
            "HMRC could not be reached. No authorisation was saved.",
        ) from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise HmrcApiError(
            502,
            "HMRC did not return a usable access token.",
        )
    try:
        expires_in = int(payload.get("expires_in"))
    except (TypeError, ValueError) as exc:
        raise HmrcApiError(
            502,
            "HMRC did not return a valid token expiry.",
        ) from exc
    if expires_in <= 0:
        raise HmrcApiError(
            502,
            "HMRC did not return a valid token expiry.",
        )
    payload["expires_in"] = expires_in
    return payload


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
    return _exchange_hmrc_token(body)


def exchange_hmrc_client_credentials_token():
    if not settings.HMRC_CLIENT_ID:
        raise ValueError("HMRC_CLIENT_ID is not configured.")
    if not settings.HMRC_CLIENT_SECRET:
        raise ValueError("HMRC_CLIENT_SECRET is not configured.")

    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.HMRC_CLIENT_ID,
            "client_secret": settings.HMRC_CLIENT_SECRET,
        }
    ).encode("utf-8")
    return _exchange_hmrc_token(body)


def call_hmrc_sandbox_keepalive():
    """Call the LedgerHouse-owned Hello World application endpoint.

    This is deliberately limited to the harmless application-restricted
    sandbox endpoint. It neither reads client data nor records a filing,
    receipt or accounting side effect.
    """
    if settings.HMRC_ENVIRONMENT != "sandbox":
        raise ValueError("HMRC keep-alive calls are permitted only in the sandbox.")

    token = exchange_hmrc_client_credentials_token().get("access_token")
    if not token:
        raise HmrcApiError(502, "HMRC token response did not contain an access token.")

    response = _hmrc_json_request(
        f"{settings.HMRC_API_BASE_URL}/hello/application",
        token,
    )
    if response["status"] != 200 or response["payload"].get("message") != "Hello Application":
        raise HmrcApiError(
            response["status"],
            "HMRC Hello World application response was not recognised.",
            response["payload"],
        )
    return {
        "application": "LedgerHouse",
        "endpoint": "GET /hello/application",
        "http_status": response["status"],
        "timestamp": timezone.now().isoformat(),
    }


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


def _percent_encode_header_value(value):
    return urllib.parse.quote(str(value), safe="")


def _hash_header_value(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest().upper()


def build_web_app_via_server_fraud_prevention_headers(
    *,
    device_id,
    public_ip,
    public_port,
    browser_js_user_agent,
    screens,
    timezone,
    user_id,
    window_size,
    vendor_public_ip,
    vendor_version="LedgerHouse=local",
):
    now = timezone_now_millis()
    encoded_user_id = _percent_encode_header_value(user_id or "anonymous")
    return {
        "Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER",
        "Gov-Client-Browser-JS-User-Agent": browser_js_user_agent or "unavailable",
        "Gov-Client-Device-ID": device_id,
        "Gov-Client-Multi-Factor": (
            f"type=OTHER&timestamp={_percent_encode_header_value(now)}"
            f"&unique-reference={_hash_header_value(user_id or device_id)}"
        ),
        "Gov-Client-Public-IP": public_ip,
        "Gov-Client-Public-IP-Timestamp": now,
        "Gov-Client-Public-Port": str(public_port or "0"),
        "Gov-Client-Screens": screens or "width=1&height=1&scaling-factor=1&colour-depth=1",
        "Gov-Client-Timezone": timezone or "UTC+00:00",
        "Gov-Client-User-IDs": f"ledgerhouse={encoded_user_id}",
        "Gov-Client-Window-Size": window_size or "width=1&height=1",
        "Gov-Vendor-Forwarded": (
            f"by={_percent_encode_header_value(vendor_public_ip)}"
            f"&for={_percent_encode_header_value(public_ip)}"
        ),
        "Gov-Vendor-License-IDs": f"LedgerHouse={_hash_header_value('LedgerHouse SaaS')}",
        "Gov-Vendor-Product-Name": "LedgerHouse",
        "Gov-Vendor-Public-IP": vendor_public_ip,
        "Gov-Vendor-Version": vendor_version,
    }


def timezone_now_millis():
    return timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"


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
            response_body = response.read()
            return {
                "status": response.status,
                "payload": _decode_hmrc_json(response_body),
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        try:
            error_payload = json.loads(error_body)
        except json.JSONDecodeError:
            error_payload = {"message": error_body}
        message = error_payload.get("message") or error_payload.get("code") or str(exc)
        raise HmrcApiError(exc.code, message, error_payload) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise HmrcApiError(
            503,
            "HMRC could not be reached. No filing or accounting status was changed.",
        ) from exc


def retrieve_vat_obligations(access_token, vrn, from_date, to_date, device_id, public_ip="127.0.0.1", fraud_headers=None):
    params = urllib.parse.urlencode({"from": from_date, "to": to_date})
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/obligations?{params}"
    response = _hmrc_json_request(
        url,
        access_token,
        headers=fraud_headers or build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"].get("obligations", [])


def retrieve_vat_return(access_token, vrn, period_key, device_id, public_ip="127.0.0.1", fraud_headers=None):
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/returns/{period_key}"
    response = _hmrc_json_request(
        url,
        access_token,
        headers=fraud_headers or build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"]


def submit_vat_return_payload(access_token, vrn, payload, device_id, public_ip="127.0.0.1", fraud_headers=None):
    url = f"{settings.HMRC_API_BASE_URL}/organisations/vat/{vrn}/returns"
    response = _hmrc_json_request(
        url,
        access_token,
        method="POST",
        payload=payload,
        headers=fraud_headers or build_desktop_fraud_prevention_headers(device_id, public_ip),
    )
    return response["payload"]


def validate_fraud_prevention_headers(access_token, fraud_headers):
    url = f"{settings.HMRC_API_BASE_URL}/test/fraud-prevention-headers/validate"
    response = _hmrc_json_request(
        url,
        access_token,
        headers=fraud_headers,
    )
    return response["payload"]


def to_hmrc_vat_return_payload(serialized_return):
    """Map LedgerHouse 9-box names to HMRC VAT MTD API field names."""
    return {
        "periodKey": serialized_return["periodKey"],
        "vatDueSales": serialized_return["vatDueOnOutputs"],
        "vatDueAcquisitions": serialized_return["vatDueAcquisitions"],
        "totalVatDue": serialized_return["totalVatDue"],
        "vatReclaimedCurrPeriod": serialized_return["vatReclaimedCurrPeriod"],
        "netVatDue": serialized_return["netVatDue"],
        "totalValueSalesExVAT": serialized_return["totalValueSalesExVAT"],
        "totalValuePurchasesExVAT": serialized_return["totalValuePurchasesExVAT"],
        "totalValueGoodsSuppliedExVAT": serialized_return["totalValueGoodsSuppliedExVAT"],
        "totalAcquisitionsExVAT": serialized_return["totalValueGoodsAcquisitionsExVAT"],
        "finalised": serialized_return["finalised"],
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
    """Fail closed for the retired mock VAT submission path.

    Real VAT filing must use the authorised workspace transport, live HMRC
    obligations, fraud-prevention headers and an actual HMRC response.
    """
    raise HmrcApiError(
        503,
        "The legacy mock VAT submission path is disabled. Use the authorised HMRC workspace transport.",
        {"period_key": period_key, "tenant_id": str(tenant.id)},
    )
