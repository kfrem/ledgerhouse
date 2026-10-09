from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounting.models import (
    AccountingTask,
    BankTransaction,
    EvidenceDocument,
    ImportedFile,
    Journal,
    JournalLine,
    ManagementPackSection,
    NominalAccount,
    StatutoryAccountsDraft,
    Tenant,
)


class CommercialReadinessRehearsalTests(TestCase):
    def setUp(self):
        for index, name in enumerate((
            "CareCo Limited", "ConsultCo Consulting", "TradeCo Retail",
            "TechCo Software Ltd", "LogisticsCo Transport Ltd", "CharityCo Foundation",
        )):
            tenant = Tenant.objects.create(name=name)
            cash = NominalAccount.objects.create(tenant=tenant, code="1200", name="Bank", category="Asset", canonical_taxonomy="Cash")
            income = NominalAccount.objects.create(tenant=tenant, code="4000", name="Sales", category="Revenue", canonical_taxonomy="Revenue")
            journal = Journal.objects.create(tenant=tenant, date=date(2026, 1, 31), description="Synthetic income", source_type="SalesInvoice", created_by="test")
            JournalLine.objects.create(tenant=tenant, journal=journal, account=cash, debit="120.00")
            JournalLine.objects.create(tenant=tenant, journal=journal, account=income, credit="120.00")
            EvidenceDocument.objects.create(tenant=tenant, filename=f"synthetic-{index}.pdf", content_type="application/pdf", file_content=b"%PDF", uploaded_by="test")
            imported = ImportedFile.objects.create(tenant=tenant, filename=f"bank-{index}.csv", raw_content="Date,Amount,Reference,FITID", file_hash=f"rehearsal-{index}")
            BankTransaction.objects.create(tenant=tenant, imported_file=imported, date=date(2026, 1, 31), amount="120.00", reference="Synthetic receipt", fitid=f"rehearsal-{index}")
            StatutoryAccountsDraft.objects.create(tenant=tenant, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31), accounts_type="MicroEntity")
            ManagementPackSection.objects.create(tenant=tenant, section_name="Commentary", period_end=date(2025, 12, 31), commentary="Synthetic review.")
            AccountingTask.objects.create(tenant=tenant, phase="Review", title="Review synthetic client", status=AccountingTask.STATUS_IN_PROGRESS)

    def test_rehearsal_passes_for_complete_synthetic_portfolio(self):
        output = StringIO()
        call_command("commercial_readiness_rehearsal", "--strict", stdout=output)
        text = output.getvalue()
        self.assertIn("Commercial readiness rehearsal passed.", text)
        self.assertNotIn("[FAIL]", text)
        self.assertIn("External filing safety", text)
