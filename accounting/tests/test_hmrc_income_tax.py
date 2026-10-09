from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from accounting.hmrc_income_tax import (
    INCOME_TAX_API_REQUIREMENTS,
    call_income_tax_mtd_endpoint,
    income_tax_subscription_status,
    missing_income_tax_subscriptions,
)


class IncomeTaxMtdTests(SimpleTestCase):
    def test_registry_covers_full_in_year_and_end_of_year_minimum(self):
        keys = {item.key for item in INCOME_TAX_API_REQUIREMENTS}
        self.assertTrue({
            "business_details", "obligations", "self_employment", "bsas", "losses",
            "liability_adjustments", "calculations", "fraud_headers",
        }.issubset(keys))

    def test_subscription_status_is_case_insensitive_and_reports_required_gaps(self):
        subscribed = [
            "Business Details (MTD) 2.0",
            "OBLIGATIONS (MTD) 3.0",
            "Test Fraud Prevention Headers 1.0",
        ]
        rows = income_tax_subscription_status(subscribed)
        self.assertTrue(next(row for row in rows if row["key"] == "business_details")["subscribed"])
        missing = missing_income_tax_subscriptions(subscribed)
        self.assertTrue(any(row["key"] == "calculations" for row in missing))
        self.assertFalse(any(row["key"] == "property" for row in missing))

    @override_settings(HMRC_API_BASE_URL="https://test-api.service.hmrc.gov.uk", HMRC_ENVIRONMENT="sandbox")
    @patch("accounting.hmrc_income_tax._hmrc_json_request")
    def test_endpoint_call_forwards_version_fraud_headers_and_sandbox_scenario(self, request):
        request.return_value = {"status": 200, "payload": {"success": True}}
        result = call_income_tax_mtd_endpoint(
            access_token="token",
            path="/individuals/business/details/AA123456A/list",
            fraud_headers={"Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER"},
            api_version="2.0",
            test_scenario="STATEFUL",
        )
        self.assertEqual(result["status"], 200)
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(headers["Accept"], "application/vnd.hmrc.2.0+json")
        self.assertEqual(headers["Gov-Test-Scenario"], "STATEFUL")

    @override_settings(HMRC_ENVIRONMENT="production")
    def test_endpoint_call_rejects_missing_security_bad_paths_and_production_test_scenarios(self):
        base = {
            "access_token": "token",
            "path": "/valid",
            "fraud_headers": {"Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER"},
            "api_version": "2.0",
        }
        with self.assertRaisesRegex(ValueError, "absolute API path"):
            call_income_tax_mtd_endpoint(**{**base, "path": "relative"})
        with self.assertRaisesRegex(ValueError, "access token"):
            call_income_tax_mtd_endpoint(**{**base, "access_token": ""})
        with self.assertRaisesRegex(ValueError, "fraud prevention"):
            call_income_tax_mtd_endpoint(**{**base, "fraud_headers": {}})
        with self.assertRaisesRegex(ValueError, "permitted only"):
            call_income_tax_mtd_endpoint(**base, test_scenario="STATEFUL")
