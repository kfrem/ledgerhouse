from django.test import TestCase

from accounting.exceptions import exception_register
from accounting.models import BankTransaction, ClientApprovalRecord, EvidenceDocument, ImportedFile, Journal, Tenant


class ExceptionRegisterTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Exceptions Ltd")
        self.other = Tenant.objects.create(name="Other Ltd")
        EvidenceDocument.objects.create(tenant=self.tenant, filename="receipt.pdf", file_content=b"x", content_type="application/pdf")
        Journal.objects.create(tenant=self.tenant, date="2026-07-01", description="Review me", source_type="SalesInvoice", source_id="j-1", created_by="practice")
        ClientApprovalRecord.objects.create(tenant=self.tenant, approval_type="Other", reference="A-1", title="Approve pack")
        EvidenceDocument.objects.create(tenant=self.other, filename="private.pdf", file_content=b"x", content_type="application/pdf")

    def test_register_combines_actionable_exceptions_without_cross_tenant_records(self):
        self.assertTrue(Journal.objects.filter(tenant=self.tenant, status="RequiresReview").exists())
        items = exception_register(self.tenant)
        titles = [item.title for item in items]

        self.assertEqual([item.severity for item in items], ["High", "High", "Normal"])
        self.assertIn("Review document: receipt.pdf", titles)
        self.assertIn("Review journal: Review me", titles)
        self.assertIn("Client decision needed: Approve pack", titles)
        self.assertNotIn("Review document: private.pdf", titles)

    def test_missing_bank_feed_match_has_an_explicit_practice_exception(self):
        imported_file = ImportedFile.objects.create(
            tenant=self.tenant,
            filename="bank-feed.json",
            file_hash="a" * 64,
            raw_content="local test",
        )
        BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-01",
            amount="25.00",
            reference="Expected invoice missing",
            fitid="needs-info-1",
            review_status="NeedsInfo",
        )

        items = exception_register(self.tenant)
        item = next(exception for exception in items if exception.kind == "Bank")
        self.assertEqual(item.title, "Investigate bank-feed match: Expected invoice missing")
        self.assertIn("could not find one", item.detail)
