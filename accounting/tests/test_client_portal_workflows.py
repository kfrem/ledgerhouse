from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TransactionTestCase
from openpyxl import Workbook

from accounting.intake import process_uploaded_file
from accounting.models import BankTransaction, EvidenceDocument, Journal, JournalLine, NominalAccount, Tenant
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

    def test_management_reports_generate_csv_and_pdf(self):
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
