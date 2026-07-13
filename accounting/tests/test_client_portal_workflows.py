from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TransactionTestCase
from openpyxl import Workbook

from accounting.intake import process_uploaded_file
from accounting.models import (
    BankReconciliation,
    BankTransaction,
    ClientRequest,
    EvidenceDocument,
    ImportedFile,
    Journal,
    JournalLine,
    NominalAccount,
    Tenant,
    VatReturn,
)
from accounting.reports import management_report_csv, management_report_pdf


@pytest.mark.django_db(transaction=True)
class ClientPortalWorkflowTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
            is_superuser=True,
        )
        self.user = user
        self.tenant = Tenant.objects.create(name="Demo Client Ltd")
        self.cash = NominalAccount.objects.create(
            tenant=self.tenant,
            code="1200",
            name="Bank",
            category="Asset",
            canonical_taxonomy="Cash",
        )
        self.sales = NominalAccount.objects.create(
            tenant=self.tenant,
            code="4000",
            name="Sales",
            category="Revenue",
            canonical_taxonomy="Revenue",
        )
        self.expense = NominalAccount.objects.create(
            tenant=self.tenant,
            code="6000",
            name="Office costs",
            category="Expense",
            canonical_taxonomy="Expense",
        )
        with transaction.atomic():
            journal = Journal.objects.create(
                tenant=self.tenant,
                date="2026-07-01",
                description="Client sale",
                source_type="SalesInvoice",
                source_id="INV-001",
                created_by="Test",
            )
            JournalLine.objects.create(
                tenant=self.tenant,
                journal=journal,
                account=self.cash,
                debit=Decimal("1200.00"),
                credit=Decimal("0.00"),
            )
            JournalLine.objects.create(
                tenant=self.tenant,
                journal=journal,
                account=self.sales,
                debit=Decimal("0.00"),
                credit=Decimal("1200.00"),
                vat_code="SR",
                vat_amount=Decimal("200.00"),
            )

    def test_login_flow_and_client_portal_render(self):
        response = self.client.get("/")
        assert response.status_code == 302
        assert response["Location"].startswith("/login/")

        assert self.client.login(username="admin", password="admin2") is True
        response = self.client.get("/")
        body = response.content.decode()
        assert response.status_code == 200
        assert "Your accounts department" in body
        assert "Upload anything finance-related" in body
        assert "/admin/accounting" not in body

    def test_practice_workspace_is_separate_from_client_portal(self):
        self.client.force_login(self.user)
        response = self.client.get("/practice/")
        body = response.content.decode()
        assert response.status_code == 200
        assert "Portfolio command centre" in body
        assert "Practice" in body

    def test_csv_upload_imports_bank_transactions(self):
        self.client.force_login(self.user)
        csv_file = SimpleUploadedFile(
            "statement.csv",
            b"Date,Amount,Reference,FITID\n2026-07-02,-24.50,Parking,FITID-PORTAL-1\n",
            content_type="text/csv",
        )
        response = self.client.post(
            "/",
            {"company": str(self.tenant.id), "documents": [csv_file]},
            format="multipart",
        )
        assert response.status_code == 302
        assert BankTransaction.objects.filter(tenant=self.tenant, fitid="FITID-PORTAL-1").exists()

    def test_xlsx_upload_imports_bank_transactions(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Date", "Amount", "Reference", "FITID"])
        sheet.append(["2026-07-03", "-95.00", "Fuel", "FITID-XLSX-1"])
        buffer = BytesIO()
        workbook.save(buffer)
        xlsx_file = SimpleUploadedFile(
            "statement.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        result = process_uploaded_file(self.tenant, xlsx_file, "client")
        assert result.imported_count == 1
        assert BankTransaction.objects.filter(tenant=self.tenant, fitid="FITID-XLSX-1").exists()

    def test_pdf_upload_stores_evidence_document(self):
        pdf_file = SimpleUploadedFile(
            "receipt.pdf",
            b"%PDF-1.4\n% demo receipt\n",
            content_type="application/pdf",
        )
        result = process_uploaded_file(self.tenant, pdf_file, "client")
        assert result.kind == "evidence"
        assert EvidenceDocument.objects.filter(
            tenant=self.tenant,
            filename="receipt.pdf",
            content_type="application/pdf",
        ).exists()

    def test_client_portal_shows_recent_uploads(self):
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="receipt-visible.pdf",
            file_content=b"%PDF-1.4\n% demo receipt\n",
            content_type="application/pdf",
            uploaded_by="client",
        )

        self.client.force_login(self.user)
        response = self.client.get(f"/?company={self.tenant.id}")
        body = response.content.decode()
        assert response.status_code == 200
        assert "Recently uploaded" in body
        assert "receipt-visible.pdf" in body
        assert "Stored" in body

    def test_practice_dashboard_surfaces_client_work_queues(self):
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="supplier-invoice.pdf",
            file_content=b"%PDF-1.4\n% supplier invoice\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        imported_file = ImportedFile.objects.create(
            tenant=self.tenant,
            filename="bank-statement.csv",
            raw_content="Date,Amount,Reference,FITID\n2026-07-04,-42.00,Parking,FITID-QUEUE-1\n",
            file_hash="practice-queue-bank",
        )
        BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-04",
            amount=Decimal("-42.00"),
            reference="Parking",
            fitid="FITID-QUEUE-1",
        )
        Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-04",
            description="Director card purchase",
            source_type="SupplierInvoice",
            source_id="BILL-001",
            created_by="Test",
            status="RequiresReview",
        )
        ClientRequest.objects.create(
            tenant=self.tenant,
            subject="Open dashboard question",
            category="Tax",
            priority="Normal",
            message="Please review this tax question.",
            submitted_by="client",
        )

        self.client.force_login(self.user)
        response = self.client.get("/practice/")
        body = response.content.decode()
        assert response.status_code == 200
        assert "Client upload inbox" in body
        assert "supplier-invoice.pdf" in body
        assert "Unmatched bank lines" in body
        assert "Parking" in body
        assert "Review before release" in body
        assert "Director card purchase" in body
        assert f"/practice/clients/{self.tenant.id}/" in body
        assert "Live controls" in body
        assert "Client questions: 1 open" in body
        assert "Next build" not in body

    def test_client_can_send_question_to_practice_workbench(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/",
            {
                "company": str(self.tenant.id),
                "action": "submit_client_request",
                "subject": "Can we review cash flow?",
                "category": "Cash flow",
                "priority": "High",
                "message": "Please check whether we can afford a new hire next month.",
            },
        )

        assert response.status_code == 302
        request_item = ClientRequest.objects.get(tenant=self.tenant)
        assert request_item.subject == "Can we review cash flow?"
        assert request_item.category == "Cash flow"
        assert request_item.priority == "High"
        assert request_item.status == "Open"

        portal_response = self.client.get(f"/?company={self.tenant.id}#support")
        portal_body = portal_response.content.decode()
        assert portal_response.status_code == 200
        assert "Can we review cash flow?" in portal_body
        assert "Cash flow | Open" in portal_body

        practice_response = self.client.get("/practice/")
        practice_body = practice_response.content.decode()
        assert practice_response.status_code == 200
        assert "Client questions" in practice_body
        assert "Can we review cash flow?" in practice_body
        assert "High" in practice_body

    def test_practice_can_open_in_app_client_file(self):
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="client-file-receipt.pdf",
            file_content=b"%PDF-1.4\n% client file receipt\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        ClientRequest.objects.create(
            tenant=self.tenant,
            subject="Need pricing advice",
            category="Pricing",
            priority="Normal",
            message="Please review our pricing before the next quote.",
            submitted_by="client",
        )
        imported_file = ImportedFile.objects.create(
            tenant=self.tenant,
            filename="client-file-bank.csv",
            raw_content="Date,Amount,Reference,FITID\n2026-07-05,-31.00,Stationery,FITID-CLIENT-FILE\n",
            file_hash="client-file-bank",
        )
        BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-05",
            amount=Decimal("-31.00"),
            reference="Stationery",
            fitid="FITID-CLIENT-FILE",
        )
        Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-05",
            description="Quote review accrual",
            source_type="ManualJournal",
            source_id="MJ-CLIENT-FILE",
            created_by="Test",
            status="RequiresReview",
        )
        self.client.force_login(self.user)

        response = self.client.get(f"/practice/clients/{self.tenant.id}/")
        body = response.content.decode()

        assert response.status_code == 200
        assert "LedgerHouse | Client file" in body
        assert "Demo Client Ltd" in body
        assert "Need pricing advice" in body
        assert "client-file-receipt.pdf" in body
        assert "Stationery" in body
        assert "Quote review accrual" in body
        assert f"/reports/{self.tenant.id}/" in body
        assert f"/integrations/hmrc/vat/?company={self.tenant.id}" in body

    def test_practice_can_update_client_question_status_in_app(self):
        request_item = ClientRequest.objects.create(
            tenant=self.tenant,
            subject="Resolve payroll question",
            category="Payroll",
            priority="Normal",
            message="Can this payroll item be closed?",
            submitted_by="client",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            f"/practice/clients/{self.tenant.id}/",
            {
                "action": "update_client_request",
                "request_id": str(request_item.id),
                "status": "Resolved",
            },
        )

        assert response.status_code == 302
        request_item.refresh_from_db()
        assert request_item.status == "Resolved"
        assert request_item.resolved_by == "admin"
        assert request_item.resolved_at is not None

        detail_response = self.client.get(f"/practice/clients/{self.tenant.id}/")
        detail_body = detail_response.content.decode()
        assert detail_response.status_code == 200
        assert "Resolve payroll question" in detail_body
        assert "Resolved" in detail_body

    def test_practice_can_review_unmatched_bank_lines_in_app(self):
        imported_file = ImportedFile.objects.create(
            tenant=self.tenant,
            filename="bank-review.csv",
            raw_content=(
                "Date,Amount,Reference,FITID\n"
                "2026-07-08,-58.20,Unmatched software,FITID-BANK-OPEN\n"
                "2026-07-08,1200.00,Matched receipt,FITID-BANK-MATCHED\n"
            ),
            file_hash="bank-review",
        )
        open_transaction = BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-08",
            amount=Decimal("-58.20"),
            reference="Unmatched software",
            fitid="FITID-BANK-OPEN",
        )
        matched_transaction = BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-08",
            amount=Decimal("1200.00"),
            reference="Matched receipt",
            fitid="FITID-BANK-MATCHED",
        )
        matched_journal = Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-08",
            description="Matched bank receipt",
            source_type="BankReceipt",
            source_id="BR-001",
            created_by="Test",
        )
        BankReconciliation.objects.create(
            tenant=self.tenant,
            bank_transaction=matched_transaction,
            matched_journal=matched_journal,
            reconciled_by="Test",
        )
        self.client.force_login(self.user)

        response = self.client.get(f"/practice/banking/?company={self.tenant.id}")
        body = response.content.decode()

        assert response.status_code == 200
        assert "Unmatched bank review" in body
        assert "Unmatched software" in body
        assert "GBP -58.20" in body
        assert "Matched receipt" not in body
        assert f"/practice/clients/{open_transaction.tenant.id}/" in body
        assert "/admin/accounting/banktransaction/" in body

    def test_client_question_requires_subject_and_message(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/",
            {
                "company": str(self.tenant.id),
                "action": "submit_client_request",
                "subject": "",
                "category": "Tax",
                "priority": "Normal",
                "message": "",
            },
        )

        assert response.status_code == 302
        assert ClientRequest.objects.filter(tenant=self.tenant).count() == 0

    def test_management_reports_generate_csv_and_pdf(self):
        VatReturn.objects.create(
            tenant=self.tenant,
            start_date="2026-04-01",
            end_date="2026-06-30",
            locked_by="Test",
            total_output_vat=Decimal("200.00"),
            total_input_vat=Decimal("40.00"),
            net_vat_payable=Decimal("160.00"),
            status="Submitted",
            hmrc_receipt_id="FORM-REPORT",
            period_key="26A1",
        )
        csv_report = management_report_csv(self.tenant)
        pdf_report = management_report_pdf(self.tenant)

        assert "Demo Client Ltd" in csv_report
        assert "Revenue" in csv_report
        assert pdf_report.startswith(b"%PDF")

        self.client.force_login(self.user)
        csv_response = self.client.get(f"/reports/{self.tenant.id}/csv/")
        pdf_response = self.client.get(f"/reports/{self.tenant.id}/pdf/")
        assert csv_response.status_code == 200
        assert csv_response["Content-Type"] == "text/csv"
        assert pdf_response.status_code == 200
        assert pdf_response["Content-Type"] == "application/pdf"

    def test_client_can_view_management_report_in_app(self):
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="board-pack-receipt.pdf",
            file_content=b"%PDF-1.4\n% demo receipt\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        VatReturn.objects.create(
            tenant=self.tenant,
            start_date="2026-04-01",
            end_date="2026-06-30",
            locked_by="Test",
            total_output_vat=Decimal("200.00"),
            total_input_vat=Decimal("40.00"),
            net_vat_payable=Decimal("160.00"),
            status="Submitted",
            hmrc_receipt_id="FORM-REPORT",
            period_key="26A1",
        )
        self.client.force_login(self.user)

        portal_response = self.client.get(f"/?company={self.tenant.id}")
        portal_body = portal_response.content.decode()
        assert portal_response.status_code == 200
        assert "Management report" in portal_body
        assert f"/reports/{self.tenant.id}/" in portal_body
        assert "Coming" not in portal_body

        report_response = self.client.get(f"/reports/{self.tenant.id}/")
        report_body = report_response.content.decode()
        assert report_response.status_code == 200
        assert "LedgerHouse | Management report" in report_body
        assert "Demo Client Ltd" in report_body
        assert "GBP 1,200.00" in report_body
        assert "FORM-REPORT" in report_body
        assert "board-pack-receipt.pdf" in report_body
