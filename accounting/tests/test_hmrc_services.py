from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.db import connection
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.hmrc_services import (
    HMRC_SERVICES,
    HmrcSubmissionBlocked,
    ensure_hmrc_service_approvals,
    get_case_payload,
    run_hmrc_filing_preflight,
    record_hmrc_provider_result,
    set_case_payload,
    submit_hmrc_filing_case,
    validate_hmrc_filing_case,
)
from accounting.models import (
    CorporationTaxEstimate,
    HmrcFilingCase,
    HmrcServiceApproval,
    HmrcTaxProfile,
    PayrollSummary,
    StatutoryAccountsDraft,
    Tenant,
)


class HmrcServiceRegistryTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="HMRC Workflow Ltd")

    def _case(self, service, filing_type, payload):
        case = HmrcFilingCase(
            tenant=self.tenant,
            service=service,
            filing_type=filing_type,
            period_start=date(2025, 4, 6),
            period_end=date(2026, 4, 5),
        )
        set_case_payload(case, payload)
        case.save()
        return case

    def test_registry_creates_separate_approval_record_for_every_service(self):
        approvals = ensure_hmrc_service_approvals()

        self.assertEqual(len(approvals), len(HMRC_SERVICES))
        self.assertEqual(HmrcServiceApproval.objects.count(), len(HMRC_SERVICES))
        self.assertEqual(
            HmrcServiceApproval.objects.get(service=HmrcServiceApproval.SERVICE_VAT_MTD).status,
            HmrcServiceApproval.STATUS_CREDENTIALS_REQUESTED,
        )
        self.assertEqual(
            HmrcServiceApproval.objects.exclude(service=HmrcServiceApproval.SERVICE_VAT_MTD)
            .filter(status=HmrcServiceApproval.STATUS_DEVELOPMENT)
            .count(),
            len(HMRC_SERVICES) - 1,
        )

    def test_tax_references_and_case_payload_are_encrypted_at_rest(self):
        profile = HmrcTaxProfile.objects.create(
            tenant=self.tenant,
            corporation_tax_utr="1234567890",
            paye_reference="123/AB456",
        )
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT corporation_tax_utr, paye_reference FROM accounting_hmrctaxprofile WHERE id = %s",
                [profile.id],
            )
            stored_profile = cursor.fetchone()
            cursor.execute(
                "SELECT encrypted_payload FROM accounting_hmrcfilingcase WHERE id = %s",
                [case.id],
            )
            stored_payload = cursor.fetchone()[0]

        self.assertNotIn("1234567890", " ".join(stored_profile))
        self.assertNotIn("123/AB456", " ".join(stored_profile))
        self.assertNotIn("1234567890", stored_payload)
        self.assertEqual(get_case_payload(case)["utr"], "1234567890")

    def test_valid_local_profiles_pass_for_each_supported_tax_family(self):
        payloads = (
            (
                HmrcServiceApproval.SERVICE_CORPORATION_TAX,
                "CT600",
                {
                    "company_tax_reference": "1234567890",
                    "company_number": "12345678",
                    "accounting_period_start": "2025-04-06",
                    "accounting_period_end": "2026-04-05",
                    "taxable_profit": "25000.00",
                    "corporation_tax_due": "4750.00",
                    "accounts_ixbrl_ready": True,
                    "computations_ixbrl_ready": True,
                },
            ),
            (
                HmrcServiceApproval.SERVICE_PAYE_RTI,
                "FPS",
                {
                    "paye_reference": "123/AB456",
                    "accounts_office_reference": "123PA00012345",
                    "payment_date": "2026-03-31",
                    "employees": [{
                        "payroll_id": "E001", "taxable_pay": "2500.00", "paye_tax": "300.00",
                        "employee_ni": "150.00",
                    }],
                },
            ),
            (
                HmrcServiceApproval.SERVICE_PAYE_RTI,
                "EPS",
                {
                    "paye_reference": "123/AB456", "accounts_office_reference": "123PA00012345",
                    "tax_year": "2025-26", "tax_month": 12,
                },
            ),
            (
                HmrcServiceApproval.SERVICE_CIS,
                "CIS300",
                {
                    "paye_reference": "123/AB456", "tax_year": "2025-26", "tax_month": 12,
                    "subcontractors": [{"utr": "1234567890", "gross_payment": "1000.00", "deduction": "200.00"}],
                },
            ),
            (
                HmrcServiceApproval.SERVICE_INCOME_TAX_MTD,
                "QUARTERLY_UPDATE",
                {
                    "nino": "AB123456C", "business_id": "XAIS12345678901", "tax_year": "2025-26",
                    "period_start": "2025-04-06", "period_end": "2025-07-05",
                    "income": "12000.00", "expenses": "5000.00",
                },
            ),
            (
                HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
                "SA100",
                {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
            ),
        )

        for service, filing_type, payload in payloads:
            with self.subTest(service=service, filing_type=filing_type):
                case = self._case(service, filing_type, payload)
                errors, warnings = validate_hmrc_filing_case(case)
                self.assertEqual(errors, [])
                self.assertTrue(warnings)

    def test_invalid_and_wrong_service_payloads_fail_preflight(self):
        case = self._case(HmrcServiceApproval.SERVICE_CORPORATION_TAX, "FPS", {})

        checked = run_hmrc_filing_preflight(case)

        self.assertEqual(checked.status, HmrcFilingCase.STATUS_VALIDATION_FAILED)
        self.assertTrue(any("not a supported filing type" in item for item in checked.validation_errors))

    def test_preflight_moves_valid_case_to_approval_without_submitting(self):
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )

        checked = run_hmrc_filing_preflight(case)

        self.assertEqual(checked.status, HmrcFilingCase.STATUS_READY_FOR_APPROVAL)
        self.assertIsNone(checked.submitted_at)
        self.assertEqual(checked.provider_receipt_id, "")

    def test_submission_fails_closed_before_and_after_local_approval(self):
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )
        case = run_hmrc_filing_preflight(case)
        approval = HmrcServiceApproval.objects.create(
            service=HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            transport=HmrcServiceApproval.TRANSPORT_XML_GATEWAY,
            status=HmrcServiceApproval.STATUS_DEVELOPMENT,
        )

        with self.assertRaisesRegex(HmrcSubmissionBlocked, "not completed client and practice approval"):
            submit_hmrc_filing_case(case, approval, "sandbox")

        now = timezone.now()
        case.status = HmrcFilingCase.STATUS_APPROVED_TO_FILE
        case.client_approved_at = now
        case.practice_approved_at = now
        case.save()
        with self.assertRaisesRegex(HmrcSubmissionBlocked, "transport is locked"):
            submit_hmrc_filing_case(case, approval, "sandbox")

    def test_application_evidence_is_redacted_and_service_specific(self):
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )
        run_hmrc_filing_preflight(case)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "hmrc-evidence.md"
            call_command("build_hmrc_application_evidence", output=str(output))
            content = output.read_text(encoding="utf-8")

        self.assertIn("Self Assessment Online", content)
        self.assertIn("Local cases passing preflight: 1", content)
        self.assertIn("Corporation Tax Online", content)
        self.assertNotIn("1234567890", content)

    def test_provider_results_require_verified_transport_and_cannot_overwrite_final_decision(self):
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )
        result = {
            "status": "pending", "correlation_id": "correlation-1", "errors": [],
        }
        with self.assertRaisesRegex(HmrcSubmissionBlocked, "verified HMRC transport"):
            record_hmrc_provider_result(case, result)

        pending = record_hmrc_provider_result(case, result, verified_transport=True)
        self.assertEqual(pending.status, HmrcFilingCase.STATUS_SUBMITTED)
        self.assertTrue(pending.submitted_at)
        self.assertEqual(pending.provider_receipt_id, "")

        accepted_result = {
            "status": "accepted", "correlation_id": "correlation-1", "receipt_id": "receipt-1", "errors": [],
        }
        accepted = record_hmrc_provider_result(case, accepted_result, verified_transport=True)
        self.assertEqual(accepted.status, HmrcFilingCase.STATUS_ACCEPTED)
        self.assertTrue(accepted.decided_at)
        self.assertEqual(len(accepted.provider_receipt_id), 64)

        same = record_hmrc_provider_result(case, accepted_result, verified_transport=True)
        self.assertEqual(same.status, HmrcFilingCase.STATUS_ACCEPTED)
        with self.assertRaisesRegex(HmrcSubmissionBlocked, "cannot be overwritten"):
            record_hmrc_provider_result(
                case,
                {"status": "rejected", "correlation_id": "correlation-1", "errors": [{"text": "Late"}]},
                verified_transport=True,
            )

    def test_provider_result_rejects_inconsistent_or_incomplete_outcomes(self):
        case = self._case(
            HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            "SA100",
            {"utr": "1234567890", "tax_year": "2025-26", "declaration": True},
        )
        invalid_results = (
            ({"status": "pending", "correlation_id": "", "errors": []}, "correlation ID"),
            ({"status": "accepted", "errors": [{"text": "bad"}]}, "cannot contain"),
            ({"status": "rejected", "errors": []}, "must include"),
            ({"status": "unknown"}, "recognised status"),
        )
        for result, message in invalid_results:
            with self.subTest(result=result):
                with self.assertRaisesRegex(ValueError, message):
                    record_hmrc_provider_result(case, result, verified_transport=True)


class HmrcServicesWorkspaceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="HMRC Workspace Ltd")
        self.other_tenant = Tenant.objects.create(name="Other Tenant Ltd")
        self.staff = get_user_model().objects.create_user(
            username="hmrc-practice", password="pass", is_staff=True
        )
        self.client_user = get_user_model().objects.create_user(
            username="hmrc-client", password="pass"
        )
        self.profile = HmrcTaxProfile.objects.create(
            tenant=self.tenant,
            corporation_tax_utr="1234567890",
            company_number="12345678",
            paye_reference="123/AB456",
            accounts_office_reference="123PA00012345",
        )
        CorporationTaxEstimate.objects.create(
            tenant=self.tenant,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            accounting_profit="30000.00",
            taxable_profit="25000.00",
            estimated_tax="4750.00",
        )
        StatutoryAccountsDraft.objects.create(
            tenant=self.tenant,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            ixbrl_ready=True,
        )
        PayrollSummary.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            gross_pay="5000.00",
            paye="600.00",
            employee_ni="300.00",
            employer_ni="350.00",
        )

    def test_staff_can_view_all_services_without_other_tenant_cases(self):
        HmrcFilingCase.objects.create(
            tenant=self.other_tenant,
            service=HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
            filing_type="PRIVATE_ONLY",
            period_start=date(2025, 4, 6),
            period_end=date(2026, 4, 5),
        )
        self.client.force_login(self.staff)

        response = self.client.get(reverse("hmrc_services_workspace"), {"company": self.tenant.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Corporation Tax Online")
        self.assertContains(response, "PAYE Online / RTI")
        self.assertContains(response, "Income Tax (Making Tax Digital)")
        self.assertNotContains(response, "PRIVATE_ONLY")

    def test_client_user_cannot_open_practice_hmrc_workspace(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("hmrc_services_workspace"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_ct600_and_fps_preparation_create_honest_blocked_cases(self):
        self.client.force_login(self.staff)
        for action, service in (
            ("prepare_ct600", HmrcServiceApproval.SERVICE_CORPORATION_TAX),
            ("prepare_fps", HmrcServiceApproval.SERVICE_PAYE_RTI),
        ):
            with self.subTest(action=action):
                response = self.client.post(
                    reverse("hmrc_services_workspace"),
                    {"company": self.tenant.id, "action": action},
                )
                case = HmrcFilingCase.objects.filter(tenant=self.tenant, service=service).latest("created_at")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(case.status, HmrcFilingCase.STATUS_VALIDATION_FAILED)
                self.assertTrue(case.validation_errors)
                self.assertIsNone(case.submitted_at)
                self.assertEqual(case.provider_receipt_id, "")

    def test_other_tax_drafts_are_created_with_explicit_completion_blockers(self):
        self.client.force_login(self.staff)
        expected = {
            "prepare_eps": "EPS",
            "prepare_cis": "CIS300",
            "prepare_itsa": "QUARTERLY_UPDATE",
            "prepare_itsa_annual": "ANNUAL_SUMMARY",
            "prepare_sa100": "SA100",
            "prepare_sa800": "SA800",
            "prepare_sa900": "SA900",
        }

        for action, filing_type in expected.items():
            with self.subTest(action=action):
                response = self.client.post(
                    reverse("hmrc_services_workspace"),
                    {"company": self.tenant.id, "action": action},
                )
                case = HmrcFilingCase.objects.filter(
                    tenant=self.tenant, filing_type=filing_type
                ).latest("created_at")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(case.status, HmrcFilingCase.STATUS_VALIDATION_FAILED)
                self.assertTrue(case.validation_errors)
                self.assertIsNone(case.submitted_at)

    def test_tax_profile_update_is_atomic_and_validates_references(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("hmrc_services_workspace"),
            {
                "company": self.tenant.id,
                "action": "save_tax_profile",
                "corporation_tax_utr": "9876543210",
                "company_number": "SC123456",
                "self_assessment_utr": "not-valid",
            },
        )

        self.profile.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.profile.corporation_tax_utr, "1234567890")
        self.assertEqual(self.profile.company_number, "12345678")
        self.assertEqual(self.profile.self_assessment_utr, "")

        self.client.post(
            reverse("hmrc_services_workspace"),
            {
                "company": self.tenant.id,
                "action": "save_tax_profile",
                "corporation_tax_utr": "9876543210",
                "company_number": "SC123456",
            },
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.corporation_tax_utr, "9876543210")
        self.assertEqual(self.profile.company_number, "SC123456")
