from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import io
import urllib.error

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.mtd import (
    HmrcApiError,
    build_desktop_fraud_prevention_headers,
    build_hmrc_authorisation_url,
    hmrc_sandbox_status,
    retrieve_vat_obligations,
    retrieve_vat_return,
    submit_vat_return_payload,
    to_hmrc_vat_return_payload,
)
from accounting.models import HmrcVatConnection, Tenant, VatReturn, VatReview


class HmrcSandboxIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )

    def _prepared_payload(self, period_key="18A2"):
        return {
            "periodKey": period_key,
            "vatDueOnOutputs": 105.50,
            "vatDueAcquisitions": 0.00,
            "totalVatDue": 105.50,
            "vatReclaimedCurrPeriod": 25.25,
            "netVatDue": 80.25,
            "totalValueSalesExVAT": 1000,
            "totalValuePurchasesExVAT": 250,
            "totalValueGoodsSuppliedExVAT": 0,
            "totalValueGoodsAcquisitionsExVAT": 0,
            "finalised": True,
        }

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

    def test_vat_payload_mapper_uses_hmrc_field_names(self):
        payload = to_hmrc_vat_return_payload(
            {
                "periodKey": "18A2",
                "vatDueOnOutputs": 105.5,
                "vatDueAcquisitions": 0,
                "totalVatDue": 105.5,
                "vatReclaimedCurrPeriod": 25.25,
                "netVatDue": 80.25,
                "totalValueSalesExVAT": 1000,
                "totalValuePurchasesExVAT": 250,
                "totalValueGoodsSuppliedExVAT": 0,
                "totalValueGoodsAcquisitionsExVAT": 0,
                "finalised": True,
            }
        )

        self.assertEqual(payload["vatDueSales"], 105.5)
        self.assertEqual(payload["totalAcquisitionsExVAT"], 0)
        self.assertNotIn("vatDueOnOutputs", payload)

    @override_settings(HMRC_API_BASE_URL="https://test-api.service.hmrc.gov.uk")
    @patch("accounting.mtd.urllib.request.urlopen")
    def test_retrieve_vat_obligations_calls_hmrc_with_fraud_headers(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"obligations":[{"periodKey":"18A2","status":"O"}]}'
        )

        obligations = retrieve_vat_obligations(
            "access-token",
            "123456789",
            "2026-01-01",
            "2026-12-31",
            "device-123",
        )

        request = urlopen.call_args.args[0]
        self.assertIn("/organisations/vat/123456789/obligations?", request.full_url)
        self.assertEqual(request.headers["Authorization"], "Bearer access-token")
        self.assertEqual(request.headers["Gov-client-device-id"], "device-123")
        self.assertEqual(obligations[0]["periodKey"], "18A2")

    @override_settings(HMRC_API_BASE_URL="https://test-api.service.hmrc.gov.uk")
    @patch("accounting.mtd.urllib.request.urlopen")
    def test_submit_and_retrieve_vat_return_payloads(self, urlopen):
        submit_response = urlopen.return_value.__enter__.return_value
        submit_response.status = 201
        submit_response.read.return_value = b'{"formBundleNumber":"123"}'

        payload = {
            "periodKey": "18A2",
            "vatDueSales": 105.50,
            "vatDueAcquisitions": 0.00,
            "totalVatDue": 105.50,
            "vatReclaimedCurrPeriod": 25.25,
            "netVatDue": 80.25,
            "totalValueSalesExVAT": 1000,
            "totalValuePurchasesExVAT": 250,
            "totalValueGoodsSuppliedExVAT": 0,
            "totalAcquisitionsExVAT": 0,
            "finalised": True,
        }

        result = submit_vat_return_payload(
            "access-token",
            "123456789",
            payload,
            "device-123",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/organisations/vat/123456789/returns", request.full_url)
        self.assertEqual(result["formBundleNumber"], "123")

        retrieve_response = urlopen.return_value.__enter__.return_value
        retrieve_response.status = 200
        retrieve_response.read.return_value = b'{"periodKey":"18A2","netVatDue":80.25}'

        retrieved = retrieve_vat_return("access-token", "123456789", "18A2", "device-123")

        self.assertEqual(retrieved["periodKey"], "18A2")
        self.assertEqual(retrieved["netVatDue"], 80.25)

    @override_settings(HMRC_API_BASE_URL="https://test-api.service.hmrc.gov.uk")
    @patch("accounting.mtd.urllib.request.urlopen")
    def test_hmrc_error_preserves_status_and_payload(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://test-api.service.hmrc.gov.uk/test",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"code":"INVALID_DATE_RANGE","message":"Invalid date range"}'),
        )

        with self.assertRaises(HmrcApiError) as raised:
            retrieve_vat_obligations(
                "access-token",
                "123456789",
                "2026-01-01",
                "2027-12-31",
                "device-123",
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.payload["code"], "INVALID_DATE_RANGE")

    def test_vat_workspace_renders_selected_tenant_connection(self):
        tenant = Tenant.objects.create(name="Sandbox Client Ltd")
        HmrcVatConnection.objects.create(
            tenant=tenant,
            vrn="123456789",
            status="Connected",
            access_token="access-token",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("hmrc_vat_workspace"), {"company": tenant.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sandbox Client Ltd")
        self.assertContains(response, "Token stored")
        self.assertContains(response, "123456789")

    def test_vat_workspace_backfills_reviews_for_existing_synced_obligations(self):
        tenant = Tenant.objects.create(name="Backfill Client Ltd")
        HmrcVatConnection.objects.create(
            tenant=tenant,
            vrn="123456789",
            status="Connected",
            access_token="access-token",
            latest_obligations=[
                {
                    "periodKey": "18A2",
                    "start": "2017-04-01",
                    "end": "2017-06-30",
                    "due": "2017-08-07",
                    "status": "O",
                }
            ],
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("hmrc_vat_workspace"), {"company": tenant.id})

        self.assertEqual(response.status_code, 200)
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertEqual(review.status, "Draft")
        self.assertEqual(review.prepared_payload["periodKey"], "18A2")

    @override_settings(
        HMRC_CLIENT_ID="sandbox-client-id",
        HMRC_CLIENT_SECRET="sandbox-secret",
        HMRC_SCOPES="read:vat write:vat",
        HMRC_REDIRECT_URI="http://localhost:8000/api/integrations/hmrc/callback",
    )
    def test_callback_persists_token_to_selected_tenant_connection(self):
        tenant = Tenant.objects.create(name="OAuth Client Ltd")
        self.client.force_login(self.user)
        authorisation_url = build_hmrc_authorisation_url(
            f"/integrations/hmrc/vat/?company={tenant.id}"
        )
        state = parse_qs(urlparse(authorisation_url).query)["state"][0]

        with patch(
            "accounting.views.exchange_hmrc_authorisation_code",
            return_value={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "scope": "read:vat write:vat",
                "expires_in": 14400,
            },
        ):
            response = self.client.get(
                reverse("hmrc_callback"),
                {"code": "auth-code", "state": state},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/integrations/hmrc/vat/?company={tenant.id}")
        connection = HmrcVatConnection.objects.get(tenant=tenant)
        self.assertEqual(connection.status, "Connected")
        self.assertEqual(connection.scope, "read:vat write:vat")
        self.assertTrue(connection.access_token)

    @patch("accounting.views.retrieve_vat_obligations")
    def test_vat_workspace_syncs_obligations(self, retrieve_obligations):
        tenant = Tenant.objects.create(name="Obligation Client Ltd")
        HmrcVatConnection.objects.create(
            tenant=tenant,
            vrn="123456789",
            status="Connected",
            access_token="access-token",
        )
        retrieve_obligations.return_value = [
            {
                "periodKey": "18A2",
                "start": "2017-04-01",
                "end": "2017-06-30",
                "due": "2017-08-07",
                "status": "O",
            }
        ]
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("hmrc_vat_workspace"),
            {
                "company": tenant.id,
                "action": "sync_obligations",
                "from_date": "2026-01-01",
                "to_date": "2026-12-31",
            },
        )

        self.assertEqual(response.status_code, 302)
        connection = HmrcVatConnection.objects.get(tenant=tenant)
        self.assertEqual(connection.latest_obligations[0]["periodKey"], "18A2")
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertEqual(review.status, "Draft")
        self.assertEqual(review.prepared_payload["periodKey"], "18A2")

    def test_vat_workspace_updates_practice_review_checklist(self):
        tenant = Tenant.objects.create(name="Review Client Ltd")
        VatReview.objects.create(
            tenant=tenant,
            period_key="18A2",
            start_date="2017-04-01",
            end_date="2017-06-30",
            due_date="2017-08-07",
            prepared_payload=self._prepared_payload(),
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("hmrc_vat_workspace"),
            {
                "company": tenant.id,
                "action": "update_review",
                "period_key": "18A2",
                "evidence_complete": "on",
                "bank_reconciled": "on",
                "vat_codes_reviewed": "on",
                "exceptions_resolved": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertTrue(review.checklist_complete)
        self.assertEqual(review.status, "Ready")
        self.assertEqual(review.practice_approved_by, "admin")

    def test_client_vat_review_requires_completed_practice_checklist(self):
        tenant = Tenant.objects.create(name="Client Approval Ltd")
        VatReview.objects.create(
            tenant=tenant,
            period_key="18A2",
            start_date="2017-04-01",
            end_date="2017-06-30",
            prepared_payload=self._prepared_payload(),
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_vat_review"),
            {"company": tenant.id, "period_key": "18A2"},
        )

        self.assertEqual(response.status_code, 302)
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertFalse(review.client_approved)
        self.assertEqual(review.status, "Draft")

    def test_client_vat_review_approves_completed_review(self):
        tenant = Tenant.objects.create(name="Client Approved Ltd")
        VatReview.objects.create(
            tenant=tenant,
            period_key="18A2",
            start_date="2017-04-01",
            end_date="2017-06-30",
            prepared_payload=self._prepared_payload(),
            evidence_complete=True,
            bank_reconciled=True,
            vat_codes_reviewed=True,
            exceptions_resolved=True,
            status="Ready",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_vat_review"),
            {"company": tenant.id, "period_key": "18A2"},
        )

        self.assertEqual(response.status_code, 302)
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertTrue(review.client_approved)
        self.assertEqual(review.status, "ClientApproved")
        self.assertEqual(review.client_approved_by, "admin")

    @patch("accounting.views.submit_vat_return_payload")
    def test_vat_workspace_blocks_submission_until_review_is_approved(self, submit_payload):
        tenant = Tenant.objects.create(name="Blocked Submit Ltd")
        HmrcVatConnection.objects.create(
            tenant=tenant,
            vrn="123456789",
            status="Connected",
            access_token="access-token",
            latest_obligations=[
                {
                    "periodKey": "18A2",
                    "start": "2017-04-01",
                    "end": "2017-06-30",
                    "due": "2017-08-07",
                    "status": "O",
                }
            ],
        )
        VatReview.objects.create(
            tenant=tenant,
            period_key="18A2",
            start_date="2017-04-01",
            end_date="2017-06-30",
            prepared_payload=self._prepared_payload(),
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("hmrc_vat_workspace"),
            {
                "company": tenant.id,
                "action": "submit_return",
                "period_key": "18A2",
            },
        )

        self.assertEqual(response.status_code, 302)
        submit_payload.assert_not_called()
        self.assertFalse(VatReturn.objects.filter(tenant=tenant, period_key="18A2").exists())

    @patch("accounting.views.submit_vat_return_payload")
    def test_vat_workspace_submits_open_obligation_and_records_vat_return(self, submit_payload):
        tenant = Tenant.objects.create(name="Submit Client Ltd")
        HmrcVatConnection.objects.create(
            tenant=tenant,
            vrn="123456789",
            status="Connected",
            access_token="access-token",
            latest_obligations=[
                {
                    "periodKey": "18A2",
                    "start": "2017-04-01",
                    "end": "2017-06-30",
                    "due": "2017-08-07",
                    "status": "O",
                }
            ],
        )
        VatReview.objects.create(
            tenant=tenant,
            period_key="18A2",
            start_date="2017-04-01",
            end_date="2017-06-30",
            due_date="2017-08-07",
            prepared_payload=self._prepared_payload(),
            evidence_complete=True,
            bank_reconciled=True,
            vat_codes_reviewed=True,
            exceptions_resolved=True,
            client_approved=True,
            status="ClientApproved",
        )
        submit_payload.return_value = {"formBundleNumber": "FORM-123"}
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("hmrc_vat_workspace"),
            {
                "company": tenant.id,
                "action": "submit_return",
                "period_key": "18A2",
            },
        )

        self.assertEqual(response.status_code, 302)
        vat_return = VatReturn.objects.get(tenant=tenant, period_key="18A2")
        self.assertEqual(vat_return.status, "Submitted")
        self.assertEqual(vat_return.hmrc_receipt_id, "FORM-123")
        review = VatReview.objects.get(tenant=tenant, period_key="18A2")
        self.assertEqual(review.status, "Submitted")
        self.assertEqual(review.hmrc_receipt_id, "FORM-123")
