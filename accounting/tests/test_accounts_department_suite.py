from decimal import Decimal
from io import BytesIO
from pathlib import Path
from io import StringIO
import zipfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounting.models import (
    AccountingTask,
    AccountingPeriodLock,
    AuditEvent,
    BankRule,
    ClientApprovalRecord,
    CorporationTaxEstimate,
    CreditControlAction,
    DocumentIntelligenceRule,
    FixedAsset,
    ManagementPackSection,
    MonthEndClose,
    NotificationEvent,
    PayrollSummary,
    PurchaseBill,
    PurchaseOrder,
    SalesInvoice,
    SalesQuote,
    StatutoryAccountsDraft,
    SupplierPaymentRun,
    Tenant,
    TenantUserAccess,
)
from accounting.operations import (
    accounts_department_snapshot,
    build_local_accounts_department_suite,
)
from accounting.local_completion import (
    LOCAL_NO_HMRC_BUILD_ITEMS,
    build_no_hmrc_completion_pack,
    build_no_hmrc_completion_zip,
)
from accounting.reports import client_data_export_zip


class AccountsDepartmentSuiteTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Suite Client Ltd")
        self.staff = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )
        self.client_user = get_user_model().objects.create_user(
            username="suite-client",
            password="client-pass",
            is_staff=False,
        )
        TenantUserAccess.objects.create(
            tenant=self.tenant,
            user=self.client_user,
            role=TenantUserAccess.ROLE_CLIENT,
        )

    def test_build_local_suite_creates_phase_1_to_8_records(self):
        snapshot = build_local_accounts_department_suite(self.tenant, "admin")

        self.assertEqual(snapshot["passed_count"], 8)
        self.assertEqual(snapshot["total_count"], 8)
        self.assertEqual(SalesQuote.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(SalesInvoice.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(PurchaseOrder.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(PurchaseBill.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(CreditControlAction.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(SupplierPaymentRun.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(BankRule.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(MonthEndClose.objects.filter(tenant=self.tenant, status=MonthEndClose.STATUS_CLOSED).count(), 1)
        self.assertEqual(AccountingPeriodLock.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(FixedAsset.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(PayrollSummary.objects.filter(tenant=self.tenant, journal_posted=True).count(), 1)
        self.assertEqual(CorporationTaxEstimate.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(StatutoryAccountsDraft.objects.filter(tenant=self.tenant, client_approved=True).count(), 1)
        self.assertEqual(ManagementPackSection.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(DocumentIntelligenceRule.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(ClientApprovalRecord.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(AccountingTask.objects.filter(tenant=self.tenant).count(), 8)
        self.assertEqual(NotificationEvent.objects.filter(tenant=self.tenant).count(), 1)

        overdue_invoice = SalesInvoice.objects.get(tenant=self.tenant, invoice_number="LH-SI-0001")
        self.assertEqual(overdue_invoice.balance_due, Decimal("1800.00"))
        draft = StatutoryAccountsDraft.objects.get(tenant=self.tenant)
        self.assertTrue(draft.locally_complete)
        self.assertFalse(draft.ixbrl_ready)

    def test_snapshot_reports_phase_status_without_live_filing(self):
        build_local_accounts_department_suite(self.tenant, "admin")

        snapshot = accounts_department_snapshot(self.tenant)

        phase_labels = {phase["phase"]: phase for phase in snapshot["phases"]}
        self.assertEqual(snapshot["sales_count"], 2)
        self.assertEqual(snapshot["quote_count"], 1)
        self.assertEqual(snapshot["purchase_count"], 2)
        self.assertEqual(snapshot["purchase_order_count"], 1)
        self.assertEqual(snapshot["bank_rule_count"], 1)
        self.assertEqual(snapshot["period_lock_count"], 1)
        self.assertEqual(snapshot["pack_section_count"], 1)
        self.assertEqual(snapshot["document_rule_count"], 1)
        self.assertEqual(snapshot["approval_count"], 2)
        self.assertEqual(snapshot["pending_approval_count"], 2)
        self.assertEqual(snapshot["open_sales_count"], 1)
        self.assertEqual(snapshot["open_purchase_count"], 2)
        self.assertEqual(snapshot["sales_balance"], Decimal("1800.00"))
        self.assertEqual(snapshot["purchase_balance"], Decimal("1440.00"))
        self.assertTrue(phase_labels["Phase 1"]["passed"])
        self.assertTrue(phase_labels["Phase 8"]["passed"])
        self.assertIn("live Companies House/HMRC filing remains externally gated", phase_labels["Phase 8"]["detail"])

    def test_practice_can_build_suite_from_screen(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "build_local_suite",
                "company": str(self.tenant.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.tenant.id), response["Location"])
        page = self.client.get(reverse("practice_accounts_department"), {"company": str(self.tenant.id)})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Accounts department suite")
        self.assertContains(page, "Core operating ledgers")
        self.assertContains(page, "Month-end accounts department")
        self.assertContains(page, "Payroll, CIS and tax workflows")
        self.assertContains(page, "Statutory accounts preparation")
        self.assertContains(page, "Client/practice collaboration")
        self.assertContains(page, "Permissions and SaaS controls")
        self.assertContains(page, "Reports and packs")
        self.assertContains(page, "Local filing readiness")
        self.assertContains(page, "8 / 8 phases")
        self.assertContains(page, "LH-Q-0001")
        self.assertContains(page, "LH-PO-0001")
        self.assertContains(page, "Software subscriptions")
        self.assertContains(page, "Period lock")
        self.assertContains(page, "Director commentary")
        self.assertContains(page, "Supplier invoice detector")

    def test_practice_can_operate_suite_records_from_screen(self):
        build_local_accounts_department_suite(self.tenant, "admin")
        self.client.force_login(self.staff)

        invoice = SalesInvoice.objects.get(tenant=self.tenant, invoice_number="LH-SI-0001")
        linked_bill = PurchaseBill.objects.get(tenant=self.tenant, bill_number="LH-PB-0001")
        unrelated_bill = PurchaseBill.objects.get(tenant=self.tenant, bill_number="LH-PB-0002")
        payment_run = SupplierPaymentRun.objects.get(tenant=self.tenant, run_reference="LH-PAYRUN-0001")
        task = AccountingTask.objects.filter(tenant=self.tenant).exclude(status=AccountingTask.STATUS_DONE).first()
        notification = NotificationEvent.objects.get(tenant=self.tenant)

        invoice_response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "record_invoice_receipt",
                "company": str(self.tenant.id),
                "invoice_id": str(invoice.id),
                "receipt_amount": str(invoice.balance_due),
                "receipt_reference": "BANK-RECEIPT-0001",
            },
        )
        bill_response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "approve_purchase_bill",
                "company": str(self.tenant.id),
                "bill_id": str(unrelated_bill.id),
            },
        )
        payment_response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "mark_payment_run_paid",
                "company": str(self.tenant.id),
                "payment_run_id": str(payment_run.id),
                "payment_reference": "BANK-TEST-0001",
            },
        )
        task_response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "complete_task",
                "company": str(self.tenant.id),
                "task_id": str(task.id),
            },
        )
        notification_response = self.client.post(
            reverse("practice_accounts_department"),
            {
                "action": "review_notification_preview",
                "company": str(self.tenant.id),
                "notification_id": str(notification.id),
            },
        )

        self.assertEqual(invoice_response.status_code, 302)
        self.assertEqual(bill_response.status_code, 302)
        self.assertEqual(payment_response.status_code, 302)
        self.assertEqual(task_response.status_code, 302)
        self.assertEqual(notification_response.status_code, 302)

        invoice.refresh_from_db()
        linked_bill.refresh_from_db()
        unrelated_bill.refresh_from_db()
        payment_run.refresh_from_db()
        task.refresh_from_db()
        notification.refresh_from_db()

        self.assertEqual(invoice.status, SalesInvoice.STATUS_PAID)
        self.assertEqual(invoice.balance_due, Decimal("0.00"))
        self.assertEqual(linked_bill.status, PurchaseBill.STATUS_PAID)
        self.assertEqual(unrelated_bill.status, PurchaseBill.STATUS_APPROVED)
        self.assertEqual(payment_run.status, SupplierPaymentRun.STATUS_PAID)
        self.assertEqual(payment_run.payment_reference, "BANK-TEST-0001")
        self.assertEqual(task.status, AccountingTask.STATUS_DONE)
        self.assertEqual(notification.status, "Queued")
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                event_type="NotificationPreviewReviewed",
                details__notification_id=notification.id,
            ).exists()
        )

    def test_accounts_department_pack_downloads_as_pdf(self):
        build_local_accounts_department_suite(self.tenant, "admin")
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse(
                "download_management_report",
                args=[self.tenant.id, "accounts-department-pack"],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("accounts-department-pack.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 2500)

    def test_client_data_export_includes_accounts_department_records(self):
        build_local_accounts_department_suite(self.tenant, "admin")

        export_zip = client_data_export_zip(self.tenant)

        with zipfile.ZipFile(BytesIO(export_zip)) as exported:
            names = set(exported.namelist())
            expected_files = {
                "sales_quotes.csv",
                "sales_invoices.csv",
                "purchase_orders.csv",
                "purchase_bills.csv",
                "supplier_payment_runs.csv",
                "bank_rules.csv",
                "month_end_closes.csv",
                "accounting_period_locks.csv",
                "fixed_assets.csv",
                "payroll_summaries.csv",
                "corporation_tax_estimates.csv",
                "statutory_accounts_drafts.csv",
                "management_pack_sections.csv",
                "document_intelligence_rules.csv",
                "client_approval_records.csv",
                "accounting_tasks.csv",
                "notification_events.csv",
            }
            self.assertTrue(expected_files.issubset(names))
            self.assertIn("LH-Q-0001", exported.read("sales_quotes.csv").decode())
            self.assertIn("LH-SI-0001", exported.read("sales_invoices.csv").decode())
            self.assertIn("LH-PO-0001", exported.read("purchase_orders.csv").decode())
            self.assertIn("LH-PB-0002", exported.read("purchase_bills.csv").decode())
            self.assertIn("LH-PAYRUN-0001", exported.read("supplier_payment_runs.csv").decode())
            self.assertIn("Software subscriptions", exported.read("bank_rules.csv").decode())
            self.assertIn("MicroEntity", exported.read("statutory_accounts_drafts.csv").decode())
            self.assertIn("Director commentary", exported.read("management_pack_sections.csv").decode())
            self.assertIn("Supplier invoice detector", exported.read("document_intelligence_rules.csv").decode())
            self.assertIn("Management pack to", exported.read("client_approval_records.csv").decode())
            self.assertIn("Release management pack", exported.read("accounting_tasks.csv").decode())

    def test_no_hmrc_completion_pack_builds_takeover_artifacts(self):
        output_dir = "/tmp/ledgerhouse-no-hmrc-completion-test"

        results = build_no_hmrc_completion_pack(output_dir, username="admin")

        self.assertEqual(len(LOCAL_NO_HMRC_BUILD_ITEMS), 12)
        self.assertTrue(all(result.passed for result in results))
        tenant_dir = f"{output_dir}/suite-client-ltd"
        expected_files = [
            f"{output_dir}/README.md",
            f"{output_dir}/tenant_readiness.csv",
            f"{output_dir}/local_no_hmrc_build_items.json",
            f"{tenant_dir}/management_report.csv",
            f"{tenant_dir}/management_report.pdf",
            f"{tenant_dir}/management_pack.pdf",
            f"{tenant_dir}/accounts_department_pack.pdf",
            f"{tenant_dir}/client_data_export.zip",
        ]
        for path in expected_files:
            with self.subTest(path=path):
                self.assertTrue(Path(path).exists(), path)
        self.assertIn("LedgerHouse Local No-HMRC Completion", Path(f"{output_dir}/README.md").read_text())
        self.assertIn("Phase 8", Path(f"{output_dir}/tenant_readiness.csv").read_text())

    def test_no_hmrc_completion_pack_command_reports_success(self):
        output = StringIO()

        call_command(
            "build_no_hmrc_completion_pack",
            "--output-dir",
            "/tmp/ledgerhouse-no-hmrc-completion-command-test",
            "--strict",
            stdout=output,
        )

        self.assertIn("No-HMRC completion pack written", output.getvalue())

    def test_local_acceptance_suite_command_reports_success(self):
        output = StringIO()
        report_path = "/tmp/ledgerhouse-local-acceptance-test.md"

        call_command(
            "local_acceptance_suite",
            "--output",
            report_path,
            "--strict",
            stdout=output,
        )

        self.assertIn("All local acceptance checks passed.", output.getvalue())
        self.assertTrue(Path(report_path).exists())
        self.assertIn("LedgerHouse Local Acceptance Suite", Path(report_path).read_text())
        self.assertIn("Management report", Path(report_path).read_text())

    def test_no_hmrc_completion_zip_contains_takeover_readme(self):
        pack_bytes, results = build_no_hmrc_completion_zip(
            "/tmp/ledgerhouse-no-hmrc-completion-zip-test",
            username="admin",
        )

        self.assertTrue(all(result.passed for result in results))
        with zipfile.ZipFile(BytesIO(pack_bytes)) as exported:
            names = set(exported.namelist())
            self.assertIn("README.md", names)
            self.assertIn("tenant_readiness.csv", names)
            self.assertIn("local_no_hmrc_build_items.json", names)
            self.assertTrue(any(name.endswith("accounts_department_pack.pdf") for name in names))
            self.assertIn("LedgerHouse Local No-HMRC Completion", exported.read("README.md").decode())

    def test_practice_can_download_no_hmrc_completion_pack_from_app(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("download_no_hmrc_completion_pack"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("ledgerhouse-no-hmrc-local-completion-pack.zip", response["Content-Disposition"])
        with zipfile.ZipFile(BytesIO(response.content)) as exported:
            self.assertIn("README.md", set(exported.namelist()))

    def test_client_user_cannot_download_no_hmrc_completion_pack(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("download_no_hmrc_completion_pack"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    def test_client_user_cannot_access_practice_suite(self):
        self.client.force_login(self.client_user)

        response = self.client.get(reverse("practice_accounts_department"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))
