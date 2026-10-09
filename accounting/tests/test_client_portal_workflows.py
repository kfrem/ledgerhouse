from decimal import Decimal
from io import BytesIO
from io import StringIO
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TransactionTestCase
from openpyxl import Workbook

from accounting.intake import process_uploaded_file
from accounting.models import (
    AuditEvent,
    BankReconciliation,
    BankTransaction,
    BankRule,
    ClientApprovalRecord,
    ClientInvitation,
    ClientRequest,
    EvidenceDocument,
    DocumentIntelligenceRule,
    ImportedFile,
    Journal,
    JournalEvidenceLink,
    JournalLine,
    NominalAccount,
    SubscriptionPlan,
    Tenant,
    TenantUserAccess,
    VatReturn,
    VatReview,
)
from accounting.reports import (
    client_data_export_zip,
    management_report_context,
    management_report_csv,
    management_report_pack_pdf,
    management_report_pdf,
)
from accounting.operations import build_local_accounts_department_suite


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

    def test_public_privacy_and_terms_pages_render_without_login(self):
        privacy_response = self.client.get("/privacy/")
        terms_response = self.client.get("/terms/")

        assert privacy_response.status_code == 200
        assert terms_response.status_code == 200
        privacy_body = privacy_response.content.decode()
        terms_body = terms_response.content.decode()
        assert "How LedgerHouse handles customer data" in privacy_body
        assert "Retention and deletion" in privacy_body
        assert "Security contact" in privacy_body
        assert "LedgerHouse service terms" in terms_body
        assert "Payments and subscriptions" in terms_body
        assert "Launch status" in terms_body

    def test_practice_workspace_is_separate_from_client_portal(self):
        self.client.force_login(self.user)
        response = self.client.get("/practice/")
        body = response.content.decode()
        assert response.status_code == 200
        assert "Practice overview" in body
        assert "Practice" in body
        assert "Accounts production" in body

    def test_practice_can_view_launch_readiness_centre(self):
        self.client.force_login(self.user)
        response = self.client.get("/practice/launch/")
        body = response.content.decode()

        assert response.status_code == 200
        assert "Launch readiness centre" in body
        assert "Customer and Legal Pack" in body
        assert "Government Integrations" in body
        assert "Deployment" in body
        assert "Final legal review" in body
        assert "HMRC production approval" in body
        assert "Companies House filing access" in body
        assert "Public privacy notice" in body
        assert "Public service terms" in body

    def test_non_staff_client_cannot_access_practice_workspace(self):
        client_user = get_user_model().objects.create_user(
            username="client-user",
            password="client-pass",
            is_staff=False,
        )
        TenantUserAccess.objects.create(
            tenant=self.tenant,
            user=client_user,
            role=TenantUserAccess.ROLE_CLIENT,
        )
        self.client.force_login(client_user)

        response = self.client.get("/practice/")

        assert response.status_code == 302
        assert response["Location"].startswith("/login/")

    def test_client_portal_limits_company_switching_to_assigned_tenants(self):
        client_user = get_user_model().objects.create_user(
            username="assigned-client",
            password="client-pass",
            is_staff=False,
        )
        other_tenant = Tenant.objects.create(name="Other Client Ltd")
        TenantUserAccess.objects.create(
            tenant=self.tenant,
            user=client_user,
            role=TenantUserAccess.ROLE_CLIENT,
        )
        self.client.force_login(client_user)

        response = self.client.get(f"/?company={other_tenant.id}")
        body = response.content.decode()

        assert response.status_code == 200
        assert "Demo Client Ltd" in body
        assert "Other Client Ltd" not in body

    def test_client_cannot_download_unassigned_company_report(self):
        client_user = get_user_model().objects.create_user(
            username="report-client",
            password="client-pass",
            is_staff=False,
        )
        other_tenant = Tenant.objects.create(name="Unassigned Client Ltd")
        TenantUserAccess.objects.create(
            tenant=self.tenant,
            user=client_user,
            role=TenantUserAccess.ROLE_CLIENT,
        )
        self.client.force_login(client_user)

        response = self.client.get(f"/reports/{other_tenant.id}/csv/")

        assert response.status_code == 404

    def test_client_can_review_local_approval_queue(self):
        build_local_accounts_department_suite(self.tenant, "practice")
        client_user = get_user_model().objects.create_user(
            username="approval-client",
            password="client-pass",
            is_staff=False,
        )
        TenantUserAccess.objects.create(
            tenant=self.tenant,
            user=client_user,
            role=TenantUserAccess.ROLE_CLIENT,
        )
        self.client.force_login(client_user)

        page = self.client.get(f"/?company={self.tenant.id}#approvals")
        body = page.content.decode()

        assert page.status_code == 200
        assert "Your approval queue" in body
        assert "Management pack to" in body
        assert "Statutory accounts draft to" in body

        approval = ClientApprovalRecord.objects.filter(
            tenant=self.tenant,
            approval_type=ClientApprovalRecord.TYPE_MANAGEMENT_PACK,
            status=ClientApprovalRecord.STATUS_PENDING,
        ).first()
        response = self.client.post(
            "/",
            {
                "company": str(self.tenant.id),
                "action": "approve_client_item",
                "approval_id": str(approval.id),
                "decision_note": "Approved for local review.",
            },
        )

        approval.refresh_from_db()
        assert response.status_code == 302
        assert response["Location"].endswith("#approvals")
        assert approval.status == ClientApprovalRecord.STATUS_APPROVED
        assert approval.decided_by == "approval-client"
        assert approval.decision_note == "Approved for local review."
        assert AuditEvent.objects.filter(tenant=self.tenant, event_type="ClientApproval").exists()

    def test_practice_can_create_client_in_app(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/practice/clients/",
            {
                "action": "create_client",
                "name": "Northstar Design Ltd",
            },
        )

        tenant = Tenant.objects.get(name="Northstar Design Ltd")
        assert response.status_code == 302
        assert response["Location"] == f"/practice/clients/{tenant.id}/"
        assert NominalAccount.objects.filter(tenant=tenant).count() == 6

        list_response = self.client.get("/practice/clients/")
        list_body = list_response.content.decode()
        assert list_response.status_code == 200
        assert "Client management" in list_body
        assert "Northstar Design Ltd" in list_body
        assert f"/practice/clients/{tenant.id}/" in list_body

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
            "supplier-invoice-125.pdf",
            b"%PDF-1.4\nSupplier invoice total GBP 125.40\n",
            content_type="application/pdf",
        )
        result = process_uploaded_file(self.tenant, pdf_file, "client")
        assert result.kind == "evidence"
        document = EvidenceDocument.objects.get(
            tenant=self.tenant,
            filename="supplier-invoice-125.pdf",
            content_type="application/pdf",
        )
        assert result.category == "PurchaseInvoice"
        assert document.document_category == "PurchaseInvoice"
        assert document.gross_amount == Decimal("125.40")
        assert document.suggested_account_code == "6000"
        assert "Practice review is still required" in document.review_note

    def test_empty_upload_is_rejected_before_intake(self):
        empty_file = SimpleUploadedFile(
            "empty-receipt.pdf",
            b"",
            content_type="application/pdf",
        )

        with pytest.raises(ValueError, match="Uploaded file is empty."):
            process_uploaded_file(self.tenant, empty_file, "client")

        assert not EvidenceDocument.objects.filter(
            tenant=self.tenant,
            filename="empty-receipt.pdf",
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
        assert "Unreviewed" in body

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
        assert "Practice priorities" in body
        assert "Work needing attention" in body
        assert "Ledger review" in body
        assert "Client questions: 1 open" in body
        assert "Next build" not in body
        assert "/admin/accounting/clientrequest/" not in body

    def test_client_portal_surfaces_plain_english_action_cards(self):
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="awaiting-review.pdf",
            file_content=b"%PDF-1.4\n% awaiting review\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        imported_file = ImportedFile.objects.create(
            tenant=self.tenant,
            filename="client-action-bank.csv",
            raw_content="date,amount,reference\n2026-07-15,-42.00,Unknown card payment\n",
            file_hash="client-action-bank",
        )
        BankTransaction.objects.create(
            tenant=self.tenant,
            imported_file=imported_file,
            date="2026-07-15",
            amount=Decimal("-42.00"),
            reference="Unknown card payment",
            fitid="CLIENT-ACTION-BANK",
        )
        VatReview.objects.create(
            tenant=self.tenant,
            period_key="26A2",
            start_date="2026-07-01",
            end_date="2026-09-30",
            status="Ready",
            evidence_complete=True,
            bank_reconciled=True,
            vat_codes_reviewed=True,
            exceptions_resolved=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(f"/?company={self.tenant.id}")
        body = response.content.decode()

        assert response.status_code == 200
        assert "What needs attention" in body
        assert "Upload outstanding paperwork" in body
        assert "Explain unmatched bank lines" in body
        assert "Review statutory approvals" in body
        assert "What your accounts team is working on" in body
        assert "1 approval item(s) are waiting for review." in body
        assert "Your approval queue" in body
        assert "VAT and tax approvals" in body
        assert "Accounts department workflow" in body
        assert "Source documents" in body
        assert "Bank matching" in body
        assert "Bookkeeping" in body
        assert "Management reporting" in body
        assert "Statutory compliance" in body
        assert "Company summary" in body
        assert "Your position at a glance" in body
        assert "Gross profit" in body
        assert "Net margin" in body
        assert "Cash runway" in body
        assert "Government services" in body
        assert "Accounts health plan" in body
        assert "What needs to happen next" in body
        assert "Records received" in body
        assert "Source records active" in body
        assert "Bank matching" in body
        assert "Needs explanation" in body
        assert "Bookkeeping position" in body
        assert "1 bookkeeping entry is recorded." in body
        assert "Approvals" in body
        assert "Review needed" in body
        assert "Management pack" in body
        assert "Next best action: Upload missing receipts, invoices, payroll files or spreadsheets." in body
        assert "Next best action: Send the accountant a note for any unknown card payments or receipts." in body

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
        assert "Accounts department workflow" in body
        assert "Client service pipeline" in body
        assert "Source documents" in body
        assert "Bank matching" in body
        assert "Management reporting" in body
        assert "Invitations and access" in body
        assert "Billing status" in body
        assert "Recent control events" in body
        assert "Account control" in body
        assert "Service, billing and integration readiness" in body
        assert "Local SaaS controls" in body
        assert "Government services" in body
        assert "Gross profit" in body
        assert "Net margin" in body
        assert "/admin/accounting/banktransaction/" not in body

    def test_practice_can_prepare_invitation_and_subscription_status(self):
        self.client.force_login(self.user)

        invite_response = self.client.post(
            f"/practice/clients/{self.tenant.id}/",
            {
                "action": "create_invitation",
                "email": "OWNER@example.com",
                "role": "Client",
            },
        )
        subscription_response = self.client.post(
            f"/practice/clients/{self.tenant.id}/",
            {
                "action": "update_subscription",
                "plan_name": "Practice pilot",
                "status": "Trial",
                "monthly_price": "49.00",
                "currency": "GBP",
                "billing_provider": "Stripe",
                "collection_method": "DirectDebit",
                "provider_customer_id": "cus_test_local",
                "provider_subscription_id": "sub_test_local",
                "next_invoice_date": "2026-08-01",
                "billing_note": "No payment provider connected yet.",
            },
        )

        assert invite_response.status_code == 302
        assert subscription_response.status_code == 302
        invitation = ClientInvitation.objects.get(tenant=self.tenant)
        assert invitation.email == "owner@example.com"
        subscription = SubscriptionPlan.objects.get(tenant=self.tenant)
        assert subscription.plan_name == "Practice pilot"
        assert subscription.monthly_price == Decimal("49.00")
        assert subscription.billing_provider == "Stripe"
        assert subscription.collection_method == "DirectDebit"
        assert subscription.provider_customer_id == "cus_test_local"
        assert AuditEvent.objects.filter(tenant=self.tenant, event_type="ClientInvitation").exists()
        assert AuditEvent.objects.filter(tenant=self.tenant, event_type="SubscriptionUpdate").exists()

        detail_response = self.client.get(f"/practice/clients/{self.tenant.id}/")
        detail_body = detail_response.content.decode()
        assert "owner@example.com" in detail_body
        assert f"/invite/{invitation.id}/" in detail_body
        assert "Practice pilot" in detail_body

        invoice_response = self.client.post(
            f"/practice/clients/{self.tenant.id}/",
            {"action": "mark_invoice_sent"},
        )
        payment_response = self.client.post(
            f"/practice/clients/{self.tenant.id}/",
            {"action": "record_manual_payment"},
        )
        subscription.refresh_from_db()
        assert invoice_response.status_code == 302
        assert payment_response.status_code == 302
        assert subscription.latest_invoice_status == "Paid"
        assert subscription.status == "Active"
        assert subscription.last_payment_at is not None
        assert AuditEvent.objects.filter(tenant=self.tenant, event_type="BillingAction").count() == 2

    def test_client_can_accept_invitation_and_get_tenant_access(self):
        invitation = ClientInvitation.objects.create(
            tenant=self.tenant,
            email="new.client@example.com",
            role=TenantUserAccess.ROLE_CLIENT,
            invited_by="admin",
        )

        response = self.client.post(
            f"/invite/{invitation.id}/",
            {
                "full_name": "New Client",
                "password": "clientpass123",
            },
        )

        assert response.status_code == 302
        invitation.refresh_from_db()
        user = get_user_model().objects.get(username="new.client@example.com")
        assert invitation.status == ClientInvitation.STATUS_ACCEPTED
        assert invitation.accepted_by == user.username
        assert TenantUserAccess.objects.filter(
            tenant=self.tenant,
            user=user,
            role=TenantUserAccess.ROLE_CLIENT,
            is_active=True,
        ).exists()
        assert AuditEvent.objects.filter(
            tenant=self.tenant,
            event_type="ClientInvitationAccepted",
        ).exists()

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
        BankRule.objects.create(
            tenant=self.tenant,
            name="Software bank rule",
            match_text="software",
            account_code="6200",
            confidence=Decimal("94.00"),
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
        assert "Suggested by Software bank rule" in body
        assert "account 6200" in body
        assert "GBP -58.20" in body
        assert "Matched receipt" not in body
        assert f"/practice/clients/{open_transaction.tenant.id}/" in body
        assert "/admin/accounting/banktransaction/" in body

        update_response = self.client.post(
            f"/practice/banking/?company={self.tenant.id}",
            {
                "action": "update_bank_review",
                "transaction_id": str(open_transaction.id),
                "review_status": "ReadyToPost",
                "company": str(self.tenant.id),
            },
        )
        open_transaction.refresh_from_db()
        assert update_response.status_code == 302
        assert open_transaction.review_status == "Reviewed"
        assert open_transaction.reviewed_by == "admin"
        assert open_transaction.reviewed_at is not None
        posted_journal = Journal.objects.get(tenant=self.tenant, source_id="FITID-BANK-OPEN")
        assert posted_journal.source_type == "BankPayment"
        assert posted_journal.lines.count() == 2
        assert posted_journal.lines.filter(account__code="6200", debit=Decimal("58.20")).exists()
        assert BankReconciliation.objects.filter(
            tenant=self.tenant,
            bank_transaction=open_transaction,
            matched_journal=posted_journal,
        ).exists()
        assert AuditEvent.objects.filter(
            tenant=self.tenant,
            event_type="BankReview",
            details__bank_transaction_id=open_transaction.id,
        ).exists()

    def test_practice_can_review_filtered_ledger_in_app(self):
        review_journal = Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-09",
            description="Accrual awaiting sign-off",
            source_type="SupplierInvoice",
            source_id="MJ-REVIEW",
            created_by="Test",
            status="RequiresReview",
        )
        Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-09",
            description="Posted receipt",
            source_type="BankReceipt",
            source_id="BR-POSTED",
            created_by="Test",
            status="Posted",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            f"/practice/ledger/?company={self.tenant.id}&status=RequiresReview"
        )
        body = response.content.decode()

        assert response.status_code == 200
        assert "Ledger review" in body
        assert "Accrual awaiting sign-off" in body
        assert "Posted receipt" not in body
        assert f"/practice/clients/{review_journal.tenant.id}/" in body
        assert "/admin/accounting/journal/" in body

        approve_response = self.client.post(
            f"/practice/ledger/?company={self.tenant.id}&status=RequiresReview",
            {
                "action": "approve_journal",
                "journal_id": str(review_journal.id),
                "company": str(self.tenant.id),
                "status": "RequiresReview",
            },
        )
        review_journal.refresh_from_db()
        assert approve_response.status_code == 302
        assert review_journal.status == "Posted"
        assert AuditEvent.objects.filter(
            tenant=self.tenant,
            event_type="LedgerApproval",
            details__journal_id=review_journal.id,
        ).exists()

    def test_document_intelligence_rule_populates_review_suggestions(self):
        DocumentIntelligenceRule.objects.create(
            tenant=self.tenant,
            name="Fuel receipt detector",
            keyword="fuel",
            document_category="Receipt",
            suggested_account_code="6100",
            confidence=Decimal("92.00"),
        )
        document = EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="fuel-receipt-2026-07-10.txt",
            file_content=b"Fuel receipt 2026-07-10 GBP 72.00 VAT",
            content_type="text/plain",
            uploaded_by="client",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            f"/practice/evidence/?company={self.tenant.id}",
            {
                "action": "analyse_evidence",
                "document_id": str(document.id),
                "company": str(self.tenant.id),
            },
        )

        document.refresh_from_db()
        assert response.status_code == 302
        assert document.document_category == "Receipt"
        assert document.suggested_account_code == "6100"
        assert document.gross_amount == Decimal("72.00")
        assert document.vat_amount == Decimal("12.00")
        assert "Local document intelligence populated suggested fields." in document.review_note
        assert AuditEvent.objects.filter(
            tenant=self.tenant,
            event_type="EvidenceAnalysis",
            details__document_id=document.id,
        ).exists()

    def test_practice_can_review_evidence_uploads_in_app(self):
        unlinked_document = EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="unlinked-receipt.pdf",
            file_content=b"%PDF-1.4\n% unlinked receipt\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        linked_document = EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="linked-invoice.pdf",
            file_content=b"%PDF-1.4\n% linked invoice\n",
            content_type="application/pdf",
            uploaded_by="client",
        )
        journal = Journal.objects.create(
            tenant=self.tenant,
            date="2026-07-10",
            description="Invoice with evidence",
            source_type="SupplierInvoice",
            source_id="SI-EVIDENCE",
            created_by="Test",
        )
        JournalEvidenceLink.objects.create(
            tenant=self.tenant,
            journal=journal,
            document=linked_document,
            linked_by="Test",
        )
        self.client.force_login(self.user)

        response = self.client.get(f"/practice/evidence/?company={self.tenant.id}")
        body = response.content.decode()

        assert response.status_code == 200
        assert "Evidence review" in body
        assert "unlinked-receipt.pdf" in body
        assert "linked-invoice.pdf" in body
        assert "Documents shown" in body
        assert "Linked" in body
        assert "Unlinked" in body
        assert f"/practice/clients/{unlinked_document.tenant.id}/" in body
        assert "/admin/accounting/evidencedocument/" in body

        update_response = self.client.post(
            f"/practice/evidence/?company={self.tenant.id}",
            {
                "action": "update_evidence_review",
                "document_id": str(unlinked_document.id),
                "review_status": "ReadyForPosting",
                "document_category": "PurchaseInvoice",
                "supplier_or_customer": "Stationery Supplier Ltd",
                "document_date": "2026-07-10",
                "gross_amount": "120.00",
                "vat_amount": "20.00",
                "suggested_account_code": "6000",
                "review_note": "Post as office costs after client confirmation.",
                "company": str(self.tenant.id),
            },
        )
        unlinked_document.refresh_from_db()
        assert update_response.status_code == 302
        assert unlinked_document.review_status == "ReadyForPosting"
        assert unlinked_document.document_category == "PurchaseInvoice"
        assert unlinked_document.supplier_or_customer == "Stationery Supplier Ltd"
        assert unlinked_document.gross_amount == Decimal("120.00")
        assert unlinked_document.vat_amount == Decimal("20.00")
        assert unlinked_document.suggested_account_code == "6000"
        assert unlinked_document.reviewed_by == "admin"
        assert unlinked_document.reviewed_at is not None
        evidence_journal = Journal.objects.get(
            tenant=self.tenant,
            source_type="EvidenceReview",
            source_id=f"EVIDENCE-{unlinked_document.id}",
        )
        assert evidence_journal.status == "RequiresReview"
        assert evidence_journal.lines.count() == 3
        assert sum((line.debit for line in evidence_journal.lines.all()), Decimal("0.00")) == Decimal("120.00")
        assert sum((line.credit for line in evidence_journal.lines.all()), Decimal("0.00")) == Decimal("120.00")
        assert JournalEvidenceLink.objects.filter(
            tenant=self.tenant,
            journal=evidence_journal,
            document=unlinked_document,
        ).exists()
        assert AuditEvent.objects.filter(
            tenant=self.tenant,
            event_type="EvidenceReview",
            details__document_id=unlinked_document.id,
        ).exists()

        detail_response = self.client.get(f"/practice/evidence/{unlinked_document.id}/")
        detail_body = detail_response.content.decode()
        assert detail_response.status_code == 200
        assert "Evidence detail" in detail_body
        assert "Stationery Supplier Ltd" in detail_body
        assert "Post as office costs" in detail_body

        file_response = self.client.get(f"/practice/evidence/{unlinked_document.id}/file/")
        assert file_response.status_code == 200
        assert file_response["Content-Type"] == "application/pdf"

    def test_practice_can_analyse_and_post_evidence_from_detail_page(self):
        document = EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="2026-07-12-stationery-invoice-240.00.txt",
            file_content=b"Supplier: Stationery Partner\nInvoice total GBP 240.00 including VAT\n",
            content_type="text/plain",
            uploaded_by="client",
        )
        self.client.force_login(self.user)

        analyse_response = self.client.post(
            f"/practice/evidence/{document.id}/",
            {"action": "analyse_evidence"},
        )
        document.refresh_from_db()
        assert analyse_response.status_code == 302
        assert document.document_category == "PurchaseInvoice"
        assert document.gross_amount == Decimal("240.00")
        assert document.vat_amount == Decimal("40.00")
        assert document.suggested_account_code == "6000"

        post_response = self.client.post(
            f"/practice/evidence/{document.id}/",
            {"action": "post_evidence_journal"},
        )
        document.refresh_from_db()
        journal = Journal.objects.get(
            tenant=self.tenant,
            source_type="EvidenceReview",
            source_id=f"EVIDENCE-{document.id}",
        )
        assert post_response.status_code == 302
        assert document.review_status == "ReadyForPosting"
        assert journal.lines.count() == 3
        assert JournalEvidenceLink.objects.filter(tenant=self.tenant, journal=journal, document=document).exists()

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
        EvidenceDocument.objects.create(
            tenant=self.tenant,
            filename="switching-evidence.pdf",
            file_content=b"%PDF-1.4\n% export receipt\n",
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
        csv_report = management_report_csv(self.tenant)
        report_context = management_report_context(self.tenant)
        pdf_report = management_report_pdf(self.tenant)
        pack_report = management_report_pack_pdf(self.tenant)
        export_zip = client_data_export_zip(self.tenant)

        assert "Demo Client Ltd" in csv_report
        assert "Revenue" in csv_report
        assert "Cash balance" in csv_report
        assert "Net assets" in csv_report
        assert "Gross profit" in csv_report
        assert "Gross margin %" in csv_report
        assert "Net margin %" in csv_report
        assert "Cash runway months" in csv_report
        assert "Aged debtors" in csv_report
        assert "Aged creditors" in csv_report
        assert "Open client questions" in csv_report
        assert "Plain-English summary" in csv_report
        assert "Workflow stage" in csv_report
        assert "Local accounting adjustment" in csv_report
        assert "Action point" in csv_report
        assert "Review 1 uploaded document(s) before finalising the bookkeeping." in csv_report
        assert report_context["action_points"]
        assert report_context["action_points"][0] == "Review 1 uploaded document(s) before finalising the bookkeeping."
        assert report_context["plain_english_summary"]
        assert report_context["workflow_board"]
        assert report_context["local_accounting_adjustments"]
        assert pdf_report.startswith(b"%PDF")
        assert pack_report.startswith(b"%PDF")
        with zipfile.ZipFile(BytesIO(export_zip)) as exported:
            names = set(exported.namelist())
            assert "README.txt" in names
            assert "journals.csv" in names
            assert "journal_lines.csv" in names
            assert "bank_transactions.csv" in names
            assert "vat_returns.csv" in names
            assert "evidence_documents.csv" in names
            assert "client_invitations.csv" in names
            assert "subscription.csv" in names
            assert "sales_quotes.csv" in names
            assert "sales_invoices.csv" in names
            assert "purchase_orders.csv" in names
            assert "purchase_bills.csv" in names
            assert "supplier_payment_runs.csv" in names
            assert "bank_rules.csv" in names
            assert "month_end_closes.csv" in names
            assert "accounting_period_locks.csv" in names
            assert "fixed_assets.csv" in names
            assert "payroll_summaries.csv" in names
            assert "corporation_tax_estimates.csv" in names
            assert "statutory_accounts_drafts.csv" in names
            assert "management_pack_sections.csv" in names
            assert "document_intelligence_rules.csv" in names
            assert "client_approval_records.csv" in names
            assert "accounting_tasks.csv" in names
            assert "notification_events.csv" in names
            assert any(name.endswith("-switching-evidence.pdf") for name in names)
            assert "FORM-REPORT" in exported.read("vat_returns.csv").decode()
            assert "accepted_by" in exported.read("client_invitations.csv").decode()
            assert "billing_provider" in exported.read("subscription.csv").decode()

        self.client.force_login(self.user)
        csv_response = self.client.get(f"/reports/{self.tenant.id}/csv/")
        pdf_response = self.client.get(f"/reports/{self.tenant.id}/pdf/")
        zip_response = self.client.get(f"/reports/{self.tenant.id}/zip/")
        pack_response = self.client.get(f"/reports/{self.tenant.id}/pack/")
        assert csv_response.status_code == 200
        assert csv_response["Content-Type"] == "text/csv"
        assert pdf_response.status_code == 200
        assert pdf_response["Content-Type"] == "application/pdf"
        assert zip_response.status_code == 200
        assert zip_response["Content-Type"] == "application/zip"
        assert pack_response.status_code == 200
        assert pack_response["Content-Type"] == "application/pdf"

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
        assert f"/reports/{self.tenant.id}/zip/" in portal_body
        assert f"/reports/{self.tenant.id}/pack/" in portal_body
        assert "Coming" not in portal_body

        report_response = self.client.get(f"/reports/{self.tenant.id}/")
        report_body = report_response.content.decode()
        assert report_response.status_code == 200
        assert "LedgerHouse | Management report" in report_body
        assert "Demo Client Ltd" in report_body
        assert "GBP 1,200.00" in report_body
        assert "Cash balance" in report_body
        assert "Net assets" in report_body
        assert "Gross profit" in report_body
        assert "Net margin" in report_body
        assert "Cash runway" in report_body
        assert "Operating readiness" in report_body
        assert "Aged debtors" in report_body
        assert "Aged creditors" in report_body
        assert "Open questions" in report_body
        assert "Action points" in report_body
        assert "What should happen next" in report_body
        assert "Review 1 uploaded document(s) before finalising the bookkeeping." in report_body
        assert "FORM-REPORT" in report_body
        assert "board-pack-receipt.pdf" in report_body

    def test_production_readiness_command_reports_local_blockers(self):
        output = StringIO()

        call_command("check_production_readiness", stdout=output)

        text = output.getvalue()
        assert "LedgerHouse production readiness" in text
        assert "DEBUG disabled" in text
        assert "FIELD_ENCRYPTION_KEY" in text
        assert "PostgreSQL backend" in text

    def test_local_production_rehearsal_command_passes_local_checks(self):
        output = StringIO()

        call_command("local_production_rehearsal", stdout=output)

        text = output.getvalue()
        assert "LedgerHouse local production rehearsal" in text
        assert "[PASS] Django system check" in text
        assert "[PASS] Migration state" in text
        assert "[PASS] Tenant data" in text
        assert "[PASS] Management report context" in text
        assert "[PASS] CSV report export" in text
        assert "[PASS] PDF report exports" in text
        assert "[PASS] Client data export" in text
        assert "All local production rehearsal checks passed." in text
        assert "[FAIL]" not in text
