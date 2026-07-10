import pytest
import uuid
from decimal import Decimal
from django.db import connection, transaction, utils
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, Journal, JournalLine, BankTransaction, ImportedFile, VatReturn
from ..middleware import tenant_context
from ..reconciliation import reconcile_transaction_to_invoice
from ..audit import generate_trial_balance, lock_vat_period, run_accountant_audit_check


@pytest.mark.django_db(transaction=True)
class AccountantAuditTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Nominal accounts
        self.acc_bank_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1200", name="Bank", category="Asset", canonical_taxonomy="Cash"
        )
        self.acc_debtors_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1100", name="Aged Debtors", category="Asset", canonical_taxonomy="Receivable"
        )
        self.acc_creditors_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="2100", name="Aged Creditors", category="Liability", canonical_taxonomy="Payable"
        )
        self.acc_expense_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="6000", name="Expense", category="Expense", canonical_taxonomy="Operating Expense"
        )

    def test_trial_balance_zero_sum(self):
        """Verify that the trial balance is generated and sums to exactly zero."""
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Journal 1", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_expense_a, debit=Decimal("150.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank_a, debit=Decimal("0.00"), credit=Decimal("150.00"))

            tb = generate_trial_balance(self.tenant_a)
            tb_sum = sum(acc["net"] for acc in tb)
            assert round(tb_sum, 2) == 0.0
            
            # Check individual accounts
            expense_entry = next(acc for acc in tb if acc["code"] == "6000")
            assert expense_entry["net"] == 150.00
            
            bank_entry = next(acc for acc in tb if acc["code"] == "1200")
            assert bank_entry["net"] == -150.00

    def test_vat_return_locking_blocks_writes(self):
        """Verify that a locked VAT return period blocks inserting or modifying journals in that range."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL trigger-specific test.")

        # Create a journal outside of the lock range first
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j_ok = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-07-05", description="July Journal", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_ok, account=self.acc_expense_a, debit=Decimal("50.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_ok, account=self.acc_bank_a, debit=Decimal("0.00"), credit=Decimal("50.00"))

            # Lock June period
            lock_vat_period(self.tenant_a, "2026-06-01", "2026-06-30", "Godfred")

            # 1. Attempt to insert a journal in June (should fail)
            try:
                with transaction.atomic():
                    j_bad = Journal.objects.create(
                        tenant=self.tenant_a, date="2026-06-15", description="June Journal", source_type="ManualJournal", created_by="Godfred"
                    )
                    JournalLine.objects.create(tenant=self.tenant_a, journal=j_bad, account=self.acc_expense_a, debit=Decimal("10.00"), credit=Decimal("0.00"))
                    JournalLine.objects.create(tenant=self.tenant_a, journal=j_bad, account=self.acc_bank_a, debit=Decimal("0.00"), credit=Decimal("10.00"))
                pytest.fail("Database allowed inserting journal inside locked VAT period.")
            except utils.DatabaseError as e:
                assert "falls within a locked VAT return period" in str(e)

            # 2. Attempt to update the July journal date to June (should fail)
            try:
                with transaction.atomic():
                    j_ok.date = "2026-06-20"
                    j_ok.save()
                pytest.fail("Database allowed updating journal date into locked VAT period.")
            except utils.DatabaseError as e:
                assert "falls within a locked VAT return period" in str(e)

    def test_vat_return_rls_isolation(self):
        """Verify that Tenant A locking a period does not affect Tenant B's ability to write in that period."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL trigger-specific test.")

        # Lock June period for Tenant A
        with tenant_context(self.tenant_a.id):
            lock_vat_period(self.tenant_a, "2026-06-01", "2026-06-30", "Godfred")

        # Tenant B provisions nominal accounts
        acc_expense_b = NominalAccount.objects.create(
            tenant=self.tenant_b, code="6000", name="Expense", category="Expense", canonical_taxonomy="Taxonomy"
        )
        acc_bank_b = NominalAccount.objects.create(
            tenant=self.tenant_b, code="1200", name="Bank", category="Asset", canonical_taxonomy="Taxonomy"
        )

        # Tenant B should be able to write to June because their June is not locked
        with tenant_context(self.tenant_b.id):
            with transaction.atomic():
                j_b = Journal.objects.create(
                    tenant=self.tenant_b, date="2026-06-10", description="Tenant B June Journal", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_b, journal=j_b, account=acc_expense_b, debit=Decimal("30.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_b, journal=j_b, account=acc_bank_b, debit=Decimal("0.00"), credit=Decimal("30.00"))

            assert Journal.objects.filter(id=j_b.id).exists()

    def test_run_accountant_audit_check(self):
        """Verify that audit checks succeed only when trial balance, review counts, and bank reconciliations are clean."""
        with tenant_context(self.tenant_a.id):
            # Initially, trial balance is balanced (all accounts at zero), bank statement is empty (diff = 0), and review count is 0.
            audit = run_accountant_audit_check(self.tenant_a)
            assert audit["is_clean"] is True
            assert audit["requires_review_count"] == 0
            assert audit["bank_reconciliation"]["reconciled"] is True

            # 1. Create an invoice (will default to status='RequiresReview')
            with transaction.atomic():
                j_invoice = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Supplies", source_type="SupplierInvoice", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_expense_a, debit=Decimal("100.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_creditors_a, debit=Decimal("0.00"), credit=Decimal("100.00"))

            if not self.is_postgres:
                j_invoice.status = 'RequiresReview'
                j_invoice.save()

            # Audit should fail now because invoice needs review (RequiresReview)
            audit = run_accountant_audit_check(self.tenant_a)
            assert audit["is_clean"] is False
            assert audit["requires_review_count"] == 1

            # 2. Add bank statement payment and reconcile
            imp_file = ImportedFile.objects.create(tenant=self.tenant_a, filename="bank.csv", raw_content="raw", file_hash="hash_audit")
            bank_tx = BankTransaction.objects.create(
                tenant=self.tenant_a, imported_file=imp_file, date="2026-06-02", amount=Decimal("-100.00"), reference="Pay invoice", fitid="FITID-AUDIT"
            )

            # Reconcile invoice to payment
            # This generates a BankPayment journal (clearing status) and creates link.
            # But wait, does it clear the invoice review status?
            # Yes! In Stage 4, we implemented the trigger that shifts Journal.status to 'Posted' when linked to evidence.
            # For bank transactions, reconciliation acts as the audit link. Let's make sure the invoice has status changed to Posted
            # once it is linked to a document.
            # In Stage 4, the trigger check_journal_status_default only checks for document links.
            # Let's link a dummy document to the invoice to mark it Posted, or manually mark it.
            # Let's manually set j_invoice.status = 'Posted' to simulate reviewer approval, or link evidence.
            j_invoice.status = 'Posted'
            j_invoice.save()

            reconcile_transaction_to_invoice(self.tenant_a, bank_tx, j_invoice, "Godfred")

            # Audit should succeed now because review count is 0 and bank is reconciled
            audit = run_accountant_audit_check(self.tenant_a)
            assert audit["is_clean"] is True
            assert audit["requires_review_count"] == 0
            assert audit["bank_reconciliation"]["reconciled"] is True
