import pytest
from datetime import date
from decimal import Decimal
from django.db import connection, transaction, utils
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, Journal, JournalLine, AccountingPeriod, EvidenceDocument, JournalEvidenceLink
from ..middleware import tenant_context
from ..reversals import reverse_journal, get_review_metrics


@pytest.mark.django_db(transaction=True)
class EvidenceAndReversalTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Setup standard nominal accounts for Tenant A
        self.acc_bank = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1200", name="Bank", category="Asset", canonical_taxonomy="Cash"
        )
        self.acc_expense = NominalAccount.objects.create(
            tenant=self.tenant_a, code="6000", name="Rent", category="Expense", canonical_taxonomy="Operating Expense"
        )

    def test_default_status_requires_review(self):
        """Verify that invoices/expenses default to RequiresReview, while other types default to Posted."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific trigger test.")

        with tenant_context(self.tenant_a.id):
            # 1. SupplierInvoice must require review
            j_invoice = Journal.objects.create(
                tenant=self.tenant_a, date="2026-06-01", description="Purchase Rent", source_type="SupplierInvoice", created_by="Godfred"
            )
            j_invoice.refresh_from_db()
            assert j_invoice.status == "RequiresReview"

            # 2. ManualJournal does not require review
            j_manual = Journal.objects.create(
                tenant=self.tenant_a, date="2026-06-01", description="Adjusting journal", source_type="ManualJournal", created_by="Godfred"
            )
            j_manual.refresh_from_db()
            assert j_manual.status == "Posted"

    def test_evidence_link_lifecycle(self):
        """Verify linking evidence sets status to Posted, and unlinking reverts to RequiresReview."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific trigger test.")

        with tenant_context(self.tenant_a.id):
            j = Journal.objects.create(
                tenant=self.tenant_a, date="2026-06-01", description="Rent invoice", source_type="SupplierInvoice", created_by="Godfred"
            )
            j.refresh_from_db()
            assert j.status == "RequiresReview"

            # Create document
            doc = EvidenceDocument.objects.create(
                tenant=self.tenant_a, filename="invoice.pdf", file_content=b"pdf content", content_type="application/pdf", uploaded_by="Godfred"
            )

            # Link document
            link = JournalEvidenceLink.objects.create(
                tenant=self.tenant_a, journal=j, document=doc, linked_by="Godfred"
            )

            # Re-fetch journal and verify status is now Posted
            j.refresh_from_db()
            assert j.status == "Posted"

            # Check metrics
            metrics = get_review_metrics(self.tenant_a)
            assert metrics["requires_review_count"] == 0
            assert metrics["evidenced_count"] == 1

            # Delete link
            link.delete()

            # Verify status reverted to RequiresReview
            j.refresh_from_db()
            assert j.status == "RequiresReview"

            # Check metrics again
            metrics = get_review_metrics(self.tenant_a)
            assert metrics["requires_review_count"] == 1
            assert metrics["evidenced_count"] == 0

    def test_journal_reversal_success(self):
        """Verify successful journal reversal swaps debits/credits and blocks duplicates."""
        with tenant_context(self.tenant_a.id):
            # Create a balanced manual journal
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Correctable journal", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_expense, debit=Decimal("150.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank, debit=Decimal("0.00"), credit=Decimal("150.00"))

            # Reverse it
            rev = reverse_journal(self.tenant_a, j, "Godfred")
            assert rev.description.startswith(f"Reversal of Journal {j.id}")
            assert rev.date == j.date

            # Verify lines are swapped
            lines = list(rev.lines.order_by('id'))
            assert len(lines) == 2
            
            assert lines[0].account == self.acc_expense
            assert lines[0].debit == Decimal("0.00")
            assert lines[0].credit == Decimal("150.00")

            assert lines[1].account == self.acc_bank
            assert lines[1].debit == Decimal("150.00")
            assert lines[1].credit == Decimal("0.00")

            # Try reversing again (should fail)
            with self.assertRaisesMessage(ValueError, "Journal already reversed"):
                reverse_journal(self.tenant_a, j, "Godfred")

            # Try reversing the reversal itself (should fail)
            with self.assertRaisesMessage(ValueError, "Cannot reverse a journal that is itself a reversal"):
                reverse_journal(self.tenant_a, rev, "Godfred")

    def test_journal_reversal_closed_period(self):
        """Verify that reversing a journal in a closed period dates the reversal on date.today()."""
        # 1. Create open period
        p = AccountingPeriod.objects.create(
            tenant=self.tenant_a, start_date="2026-06-01", end_date="2026-06-30", is_closed=False
        )
        
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-15", description="Rent", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_expense, debit=Decimal("10.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank, debit=Decimal("0.00"), credit=Decimal("10.00"))
            
        # 2. Lock the period
        p.is_closed = True
        p.save()
        
        # 3. Create open period for today
        AccountingPeriod.objects.create(
            tenant=self.tenant_a, start_date=str(date.today().replace(day=1)), end_date=str(date.today().replace(day=28)), is_closed=False
        )

        with tenant_context(self.tenant_a.id):
            # Reversing should shift the date to today to avoid violating the closed period database lock
            rev = reverse_journal(self.tenant_a, j, "Godfred")
            assert rev.date == date.today()
            assert rev.lines.count() == 2

    def test_evidence_rls_isolation(self):
        """Verify RLS isolates Evidence and Links across tenants."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific RLS test.")

        with tenant_context(self.tenant_a.id):
            # Tenant A creates doc
            doc_a = EvidenceDocument.objects.create(
                tenant=self.tenant_a, filename="doc_a.pdf", file_content=b"content", content_type="application/pdf", uploaded_by="Godfred"
            )

        with tenant_context(self.tenant_b.id):
            # Tenant B should see 0 docs
            assert EvidenceDocument.objects.count() == 0
            
            # Tenant B creates doc
            doc_b = EvidenceDocument.objects.create(
                tenant=self.tenant_b, filename="doc_b.pdf", file_content=b"content", content_type="application/pdf", uploaded_by="User B"
            )

        with tenant_context(self.tenant_a.id):
            # Tenant A should see only their doc
            docs = list(EvidenceDocument.objects.all())
            assert len(docs) == 1
            assert docs[0].filename == "doc_a.pdf"
