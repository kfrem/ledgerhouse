from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.mtd import (
    build_desktop_fraud_prevention_headers,
    build_hmrc_authorisation_url,
    hmrc_sandbox_status,
)


class HmrcSandboxIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )

    @override_settings(HMRC_CLIENT_ID="", HMRC_CLIENT_SECRET="")
    def test_status_reports_missing_secret_without_exposing_values(self):
        status = hmrc_sandbox_status()

        self.assertFalse(status["configured"])
        self.assertFalse(status["required"]["client_id"])
        self.assertFalse(status["required"]["client_secret"])
        self.assertIn("VAT (MTD) 1.0", status["subscribed_apis"])
        self.assertIn("Test Fraud Prevention Headers 1.0", status["subscribed_apis"])

    @override_settings(
        HMRC_CLIENT_ID="sandbox-client-id",
        HMRC_CLIENT_SECRET="sandbox-secret",
        HMRC_SCOPES="read:vat write:vat",
        HMRC_REDIRECT_URI="http://localhost:8000/api/integrations/hmrc/callback",
        HMRC_AUTHORIZE_URL="https://test-api.service.hmrc.gov.uk/oauth/authorize",
    )
    def test_authorisation_url_targets_hmrc_sandbox_vat_scopes(self):
        url = build_hmrc_authorisation_url("/practice/")

        self.assertTrue(url.startswith("https://test-api.service.hmrc.gov.uk/oauth/authorize?"))
        self.assertIn("client_id=sandbox-client-id", url)
        self.assertIn("scope=read%3Avat+write%3Avat", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fintegrations%2Fhmrc%2Fcallback", url)
        self.assertIn("state=", url)

    @override_settings(HMRC_CLIENT_ID="", HMRC_CLIENT_SECRET="")
    def test_authorise_view_blocks_when_client_id_missing(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("hmrc_authorise"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("hmrc_sandbox_status"))

    @override_settings(
        HMRC_CLIENT_ID="sandbox-client-id",
        HMRC_CLIENT_SECRET="sandbox-secret",
        HMRC_SCOPES="read:vat write:vat",
        HMRC_REDIRECT_URI="http://localhost:8000/api/integrations/hmrc/callback",
        HMRC_AUTHORIZE_URL="https://test-api.service.hmrc.gov.uk/oauth/authorize",
    )
    def test_authorise_view_redirects_to_hmrc(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("hmrc_authorise"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://test-api.service.hmrc.gov.uk/oauth/authorize?"))

    @override_settings(
        HMRC_CLIENT_ID="sandbox-client-id",
        HMRC_CLIENT_SECRET="sandbox-secret",
        HMRC_SCOPES="read:vat write:vat",
        HMRC_REDIRECT_URI="http://localhost:8000/api/integrations/hmrc/callback",
    )
    def test_callback_stores_token_payload_from_hmrc_exchange(self):
        self.client.force_login(self.user)
        authorisation_url = build_hmrc_authorisation_url("/integrations/hmrc/")
        state = parse_qs(urlparse(authorisation_url).query)["state"][0]

        with patch(
            "accounting.views.exchange_hmrc_authorisation_code",
            return_value={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "scope": "read:vat write:vat",
                "expires_in": 14400,
            },
        ) as exchange:
            response = self.client.get(
                reverse("hmrc_callback"),
                {"code": "auth-code", "state": state},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/integrations/hmrc/")
        exchange.assert_called_once_with("auth-code")
        self.assertEqual(self.client.session["hmrc_sandbox_token"]["scope"], "read:vat write:vat")

    def test_desktop_fraud_prevention_headers_have_required_basics(self):
        headers = build_desktop_fraud_prevention_headers(
            "device-123",
            public_ip="203.0.113.10",
        )

        self.assertEqual(headers["Gov-Client-Connection-Method"], "DESKTOP_APP_DIRECT")
        self.assertEqual(headers["Gov-Client-Device-ID"], "device-123")
        self.assertEqual(headers["Gov-Client-Public-IP"], "203.0.113.10")
        self.assertIn("Gov-Vendor-Version", headers)
