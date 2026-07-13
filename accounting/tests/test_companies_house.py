import base64
import io
import json
import urllib.error
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.companies_house import (
    CompaniesHouseApiError,
    companies_house_status,
    normalise_company_number,
    retrieve_company_profile,
)
from accounting.models import AuditEvent, NominalAccount, Tenant


class FakeCompaniesHouseResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def company_profile_payload(company_number="00000006", company_name="LEDGERHOUSE TEST LIMITED"):
    return {
        "company_number": company_number,
        "company_name": company_name,
        "company_status": "active",
        "type": "ltd",
        "date_of_creation": "2024-04-06",
        "accounts": {"next_due": "2026-12-31", "overdue": False},
        "confirmation_statement": {"next_due": "2026-05-01", "overdue": False},
        "sic_codes": ["69201"],
        "registered_office_address": {
            "address_line_1": "1 Practice Street",
            "locality": "London",
            "postal_code": "EC1A 1AA",
            "country": "England",
        },
    }


@override_settings(
    COMPANIES_HOUSE_API_KEY="test-api-key",
    COMPANIES_HOUSE_API_BASE_URL="https://api.company-information.service.gov.uk",
)
class CompaniesHouseIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )

    def test_status_reports_configured_without_exposing_key(self):
        status = companies_house_status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["api_key_present"])
        self.assertEqual(status["key_source"], "environment")
        self.assertNotIn("test-api-key", str(status))

    def test_company_number_is_normalised_for_numeric_input(self):
        self.assertEqual(normalise_company_number("6"), "00000006")
        self.assertEqual(normalise_company_number(" 00000006 "), "00000006")
        self.assertEqual(normalise_company_number("SC123456"), "SC123456")

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_retrieve_company_profile_uses_basic_auth_api_key(self, urlopen):
        urlopen.return_value = FakeCompaniesHouseResponse(company_profile_payload())

        profile = retrieve_company_profile("6")

        self.assertEqual(profile["company_name"], "LEDGERHOUSE TEST LIMITED")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.company-information.service.gov.uk/company/00000006",
        )
        expected_token = base64.b64encode(b"test-api-key:").decode("ascii")
        self.assertEqual(request.headers["Authorization"], f"Basic {expected_token}")

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_retrieve_company_profile_preserves_api_errors(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.company-information.service.gov.uk/company/00000006",
            404,
            "Not Found",
            {},
            io.BytesIO(b'{"error":"company-profile-not-found"}'),
        )

        with self.assertRaises(CompaniesHouseApiError) as exc:
            retrieve_company_profile("6")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(str(exc.exception), "company-profile-not-found")

    @patch("accounting.views.retrieve_company_profile")
    def test_companies_house_workspace_displays_company_profile(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.get(reverse("companies_house_workspace"), {"company_number": "6"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LEDGERHOUSE TEST LIMITED")
        self.assertContains(response, "00000006")
        self.assertContains(response, "2026-12-31")
        retrieve_profile.assert_called_once_with("6")

    @patch("accounting.views.retrieve_company_profile")
    def test_companies_house_workspace_creates_client_from_profile(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace"),
            {"company_number": "6", "action": "create_client"},
        )

        tenant = Tenant.objects.get(name="LEDGERHOUSE TEST LIMITED")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("practice_client_detail", args=[tenant.id]))
        self.assertEqual(NominalAccount.objects.filter(tenant=tenant).count(), 6)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=tenant,
                event_type="CompaniesHouseSync",
                details__company_number="00000006",
            ).exists()
        )
