from dataclasses import dataclass

from django.conf import settings

from .mtd import _hmrc_json_request


INCOME_TAX_MTD_SCOPES = "read:self-assessment write:self-assessment"


@dataclass(frozen=True)
class IncomeTaxApiRequirement:
    key: str
    name: str
    version: str
    stage: str
    required: bool = True


INCOME_TAX_API_REQUIREMENTS = (
    IncomeTaxApiRequirement("business_details", "Business Details (MTD)", "2.0", "in-year and end-of-year"),
    IncomeTaxApiRequirement("obligations", "Obligations (MTD)", "3.0", "in-year and end-of-year"),
    IncomeTaxApiRequirement("self_employment", "Self Employment Business (MTD)", "5.0", "in-year and end-of-year"),
    IncomeTaxApiRequirement("property", "Property Business (MTD)", "6.0", "in-year and end-of-year", False),
    IncomeTaxApiRequirement("bsas", "Business Source Adjustable Summary (MTD)", "7.0", "end-of-year"),
    IncomeTaxApiRequirement("losses", "Individual Losses (MTD)", "5.0", "end-of-year"),
    IncomeTaxApiRequirement("liability_adjustments", "Individuals Tax Liability Adjustments (MTD)", "3.0", "end-of-year"),
    IncomeTaxApiRequirement("calculations", "Individual Calculations (MTD)", "8.0", "in-year and end-of-year"),
    IncomeTaxApiRequirement("test_support", "Self Assessment Test Support (MTD)", "2.0", "sandbox", False),
    IncomeTaxApiRequirement("fraud_headers", "Test Fraud Prevention Headers", "1.0", "sandbox"),
)


def income_tax_subscription_status(subscribed_apis=None):
    subscribed = tuple(subscribed_apis if subscribed_apis is not None else settings.HMRC_SUBSCRIBED_APIS)
    rows = []
    for requirement in INCOME_TAX_API_REQUIREMENTS:
        present = any(requirement.name.lower() in item.lower() for item in subscribed)
        rows.append({
            "key": requirement.key,
            "name": requirement.name,
            "version": requirement.version,
            "stage": requirement.stage,
            "required": requirement.required,
            "subscribed": present,
        })
    return rows


def missing_income_tax_subscriptions(subscribed_apis=None):
    return [row for row in income_tax_subscription_status(subscribed_apis) if row["required"] and not row["subscribed"]]


def call_income_tax_mtd_endpoint(
    *,
    access_token,
    path,
    method="GET",
    payload=None,
    fraud_headers,
    api_version,
    test_scenario="",
):
    if not str(path or "").startswith("/") or ".." in path:
        raise ValueError("The HMRC Income Tax endpoint path must be an absolute API path.")
    if method not in {"GET", "POST", "PUT", "DELETE"}:
        raise ValueError("Unsupported HMRC Income Tax HTTP method.")
    if not access_token:
        raise ValueError("An HMRC user access token is required.")
    if not fraud_headers:
        raise ValueError("HMRC fraud prevention headers are required.")
    if not api_version:
        raise ValueError("The HMRC API version is required.")
    headers = {
        **fraud_headers,
        "Accept": f"application/vnd.hmrc.{api_version}+json",
    }
    if test_scenario:
        if settings.HMRC_ENVIRONMENT != "sandbox":
            raise ValueError("Gov-Test-Scenario is permitted only in the HMRC sandbox.")
        headers["Gov-Test-Scenario"] = test_scenario
    return _hmrc_json_request(
        f"{settings.HMRC_API_BASE_URL}{path}",
        access_token,
        method=method,
        payload=payload,
        headers=headers,
    )
