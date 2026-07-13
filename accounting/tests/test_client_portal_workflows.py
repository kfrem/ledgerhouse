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
    BankTransaction,
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
