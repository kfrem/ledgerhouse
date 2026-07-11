"""Regression tests for the Stage 6 audit remediation:

1. VAT-lock trigger hardening (migration 0008): journal lines inside a filed
   VAT period can no longer be inserted, updated or deleted, journals can no
   longer be deleted, and journals cannot be moved out of a locked range.
2. Payroll CSV internal-consistency validation.
3. CIS deduction rate whitelist (20% / 30% / 0%).
4. Open Banking consent guard (expired / inactive connections refuse to sync).
"""
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.db import connection, transaction, utils
from accounting.models import (
    Tenant, NominalAccount, Journal, JournalLine, VatReturn, BankFeedConnection,
)
from accounting.middleware import tenant_context
from accounting.open_banking import sync_bank_feed
from accounting.payroll_cis import import_payroll_journal, post_subcontractor_invoice


class VatLockHardeningTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Lock Test Ltd")
        with tenant_context(self.tenant.id):
            self.acc_bank = NominalAccount.objects.create(
                tenant=self.tenant, code="1200", name="Bank", category="Asset",
                canonical_taxonomy="Cash and Cash Equivalents")
            self.acc_sales = NominalAccount.objects.create(
                tenant=self.tenant, code="4000", name="Sales", category="Revenue",
                canonical_taxonomy="Operating Revenue")

            # Post a balanced journal BEFORE the VAT period is locked
            with transaction.atomic():
                self.journal = Journal.objects.create(
                    tenant=self.tenant, date=date(2026, 6, 15),
                    description="Pre-lock sales journal",
                    source_type="SalesInvoice", created_by="Test")
                self.line_dr = JournalLine.objects.create(
                    tenant=self.tenant, journal=self.journal, account=self.acc_bank,
                    debit=Decimal("120.00"), credit=Decimal("0.00"))
                self.line_cr = JournalLine.objects.create(
                    tenant=self.tenant, journal=self.journal, account=self.acc_sales,
                    debit=Decimal("0.00"), credit=Decimal("120.00"))

            # File/lock June 2026
            VatReturn.objects.create(
                tenant=self.tenant, start_date=date(2026, 6, 1), end_date=date(2026, 6, 30),
                locked_by="Test", total_output_vat=Decimal("20.00"),
                total_input_vat=Decimal("0.00"), net_vat_payable=Decimal("20.00"))

        self.is_postgres = (connection.vendor == 'postgresql')

    def test_line_update_blocked_in_locked_vat_period(self):
        if not self.is_postgres:
            self.skipTest("Requires PostgreSQL triggers.")
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(utils.DatabaseError, "falls within a locked VAT return period"):
                with transaction.atomic():
                    JournalLine.objects.filter(pk=self.line_dr.pk).update(vat_code="SR")

    def test_line_delete_blocked_in_locked_vat_period(self):
        if not self.is_postgres:
            self.skipTest("Requires PostgreSQL triggers.")
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(utils.DatabaseError, "falls within a locked VAT return period"):
                with transaction.atomic():
                    self.line_cr.delete()

    def test_line_insert_blocked_in_locked_vat_period(self):
        if not self.is_postgres:
            self.skipTest("Requires PostgreSQL triggers.")
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(utils.DatabaseError, "falls within a locked VAT return period"):
                with transaction.atomic():
                    JournalLine.objects.create(
                        tenant=self.tenant, journal=self.journal, account=self.acc_bank,
                        debit=Decimal("1.00"), credit=Decimal("0.00"))

    def test_journal_delete_blocked_in_locked_vat_period(self):
        if not self.is_postgres:
            self.skipTest("Requires PostgreSQL triggers.")
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(utils.DatabaseError, "falls within a locked VAT return period"):
                with transaction.atomic():
                    self.journal.delete()

    def test_journal_cannot_be_moved_out_of_locked_vat_period(self):
        if not self.is_postgres:
            self.skipTest("Requires PostgreSQL triggers.")
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(utils.DatabaseError, "falls within a locked VAT return period"):
                with transaction.atomic():
                    self.journal.date = date(2026, 7, 15)
                    self.journal.save()

    def test_activity_outside_locked_range_still_allowed(self):
        with tenant_context(self.tenant.id):
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant, date=date(2026, 7, 10),
                    description="Post-lock journal in open period",
                    source_type="SalesInvoice", created_by="Test")
                JournalLine.objects.create(
                    tenant=self.tenant, journal=j, account=self.acc_bank,
                    debit=Decimal("60.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(
                    tenant=self.tenant, journal=j, account=self.acc_sales,
                    debit=Decimal("0.00"), credit=Decimal("60.00"))
            self.assertEqual(j.lines.count(), 2)


class PayrollValidationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Payroll Test Ltd")

    def test_inconsistent_row_rejected_with_clear_error(self):
        # Gross 5000 but PAYE + EmployeeNI + Net = 4900 -> would be unbalanced
        csv_content = """Department,GrossPay,EmployerNI,EmployeeNI,PAYETax,NetWages
Engineering,5000.00,600.00,500.00,1000.00,3400.00
"""
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(ValueError, "row 1 is inconsistent"):
                import_payroll_journal(self.tenant, csv_content, date(2026, 6, 30))

    def test_negative_amount_rejected(self):
        csv_content = """Department,GrossPay,EmployerNI,EmployeeNI,PAYETax,NetWages
Sales,3000.00,-360.00,300.00,600.00,2100.00
"""
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(ValueError, "row 1 contains a negative amount"):
                import_payroll_journal(self.tenant, csv_content, date(2026, 6, 30))

    def test_non_numeric_amount_rejected(self):
        csv_content = """Department,GrossPay,EmployerNI,EmployeeNI,PAYETax,NetWages
Sales,3000.00,abc,300.00,600.00,2100.00
"""
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(ValueError, "row 1 contains a non-numeric amount"):
                import_payroll_journal(self.tenant, csv_content, date(2026, 6, 30))


class CisRateValidationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="CIS Test Ltd")

    def test_non_hmrc_rate_rejected(self):
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(ValueError, "Invalid CIS rate"):
                post_subcontractor_invoice(
                    tenant=self.tenant, subcontractor_name="Brickwork Ltd",
                    gross_amount=Decimal("2000.00"), cis_rate=Decimal("0.25"),
                    date_val=date(2026, 6, 18))

    def test_unverified_30_percent_rate_accepted(self):
        with tenant_context(self.tenant.id):
            j = post_subcontractor_invoice(
                tenant=self.tenant, subcontractor_name="Groundworks Ltd",
                gross_amount=Decimal("1000.00"), cis_rate=Decimal("0.30"),
                date_val=date(2026, 6, 18))
            cis_credit = sum(l.credit for l in j.lines.all() if l.account.code == "2230")
            self.assertEqual(cis_credit, Decimal("300.00"))

    def test_non_positive_gross_rejected(self):
        with tenant_context(self.tenant.id):
            with self.assertRaisesMessage(ValueError, "gross amount must be positive"):
                post_subcontractor_invoice(
                    tenant=self.tenant, subcontractor_name="Brickwork Ltd",
                    gross_amount=Decimal("0.00"), cis_rate=Decimal("0.20"),
                    date_val=date(2026, 6, 18))


class OpenBankingConsentGuardTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Feed Test Ltd")

    def test_expired_consent_refuses_sync_and_marks_connection(self):
        with tenant_context(self.tenant.id):
            conn = BankFeedConnection.objects.create(
                tenant=self.tenant, bank_name="Barclays", account_identifier="123",
                status="Connected", expires_at=timezone.now() - timedelta(days=1),
                consent_token="tok")
            with self.assertRaisesMessage(ValueError, "expired"):
                sync_bank_feed(self.tenant, conn)
            conn.refresh_from_db()
            self.assertEqual(conn.status, "Expired")

    def test_inactive_connection_refuses_sync(self):
        with tenant_context(self.tenant.id):
            conn = BankFeedConnection.objects.create(
                tenant=self.tenant, bank_name="Barclays", account_identifier="456",
                status="Expired", expires_at=timezone.now() + timedelta(days=90),
                consent_token="tok")
            with self.assertRaisesMessage(ValueError, "not active"):
                sync_bank_feed(self.tenant, conn)
