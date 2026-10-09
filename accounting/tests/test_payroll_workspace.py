from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounting.models import AuditEvent, Journal, JournalLine, PayrollSummary, Tenant
from accounting.payroll_cis import post_payroll_period


PAYROLL_CSV = """Department,GrossPay,EmployerNI,EmployeeNI,PAYETax,NetWages
Operations,2500.00,300.00,200.00,500.00,1800.00
"""


class PayrollWorkspaceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Payroll workspace client")
        self.staff = get_user_model().objects.create_user(
            username="payroll-practice", password="test-password", is_staff=True
        )

    def test_post_payroll_period_creates_balanced_journal_and_register_entry(self):
        summary, journal = post_payroll_period(
            self.tenant, PAYROLL_CSV, date(2026, 7, 1), date(2026, 7, 31), "practice"
        )

        self.assertTrue(summary.journal_posted)
        self.assertEqual(summary.status, "Posted")
        self.assertEqual(summary.gross_pay, Decimal("2500.00"))
        self.assertEqual(sum(line.debit for line in JournalLine.objects.filter(journal=journal)), Decimal("2800.00"))
        self.assertEqual(sum(line.credit for line in JournalLine.objects.filter(journal=journal)), Decimal("2800.00"))

    def test_rejects_duplicate_posting_for_same_period(self):
        post_payroll_period(self.tenant, PAYROLL_CSV, date(2026, 7, 1), date(2026, 7, 31))

        with self.assertRaisesMessage(ValueError, "already been posted"):
            post_payroll_period(self.tenant, PAYROLL_CSV, date(2026, 7, 1), date(2026, 7, 31))

        self.assertEqual(Journal.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(PayrollSummary.objects.filter(tenant=self.tenant).count(), 1)

    def test_practice_workspace_posts_csv_and_records_audit_event(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            "/practice/payroll/",
            {
                "company": str(self.tenant.id),
                "period_start": "2026-07-01",
                "period_end": "2026-07-31",
                "payroll_file": self._uploaded_csv(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PayrollSummary.objects.filter(tenant=self.tenant, journal_posted=True).exists())
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, event_type="PayrollPosted").exists())

        response = self.client.get(f"/practice/payroll/?company={self.tenant.id}")
        self.assertContains(response, "Payroll journal control")
        self.assertContains(response, "Posted payroll periods")

    @staticmethod
    def _uploaded_csv():
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile("july-payroll.csv", PAYROLL_CSV.encode("utf-8"), content_type="text/csv")
