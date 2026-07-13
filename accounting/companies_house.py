import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.conf import settings


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


def companies_house_status():
    key = companies_house_api_key()
    key_path = _local_key_path()
    key_source = "environment" if getattr(settings, "COMPANIES_HOUSE_API_KEY", "") else "local file"
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
