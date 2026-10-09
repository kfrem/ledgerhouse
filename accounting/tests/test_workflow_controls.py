from datetime import date
from decimal import Decimal

from django.db import DatabaseError, transaction
from django.test import TestCase

from accounting.models import (
    AccountingTask,
    AuditEvent,
    ClientApprovalRecord,
    PurchaseBill,
    SalesInvoice,
    SalesReceipt,
    SupplierPaymentRun,
    SupplierPaymentRunBill,
    Tenant,
)
from accounting.workflow_controls import (
    mark_supplier_payment_run_paid,
    record_sales_receipt,
    release_approved_pack,
    transition_task,
)


class WorkflowControlTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Workflow Ltd")

    def test_release_requires_approval_and_is_idempotently_audited(self):
        approval = ClientApprovalRecord.objects.create(tenant=self.tenant, approval_type="Other", reference="P-1", title="Pack")
        with self.assertRaisesMessage(ValueError, "only be released"):
            release_approved_pack(approval, "practice")
        approval.status = ClientApprovalRecord.STATUS_APPROVED
        approval.save(update_fields=["status"])
        _, created = release_approved_pack(approval, "practice")
        _, repeated = release_approved_pack(approval, "practice")
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(AuditEvent.objects.filter(event_type="ApprovalPackReleased").count(), 1)

    def test_task_transitions_are_controlled_and_audited(self):
        task = AccountingTask.objects.create(tenant=self.tenant, phase="Close", title="Review close")
        transition_task(task, AccountingTask.STATUS_IN_PROGRESS, "practice")
        transition_task(task, AccountingTask.STATUS_DONE, "practice")
        with self.assertRaisesMessage(ValueError, "cannot move"):
            transition_task(task, AccountingTask.STATUS_OPEN, "practice")
        self.assertEqual(AuditEvent.objects.filter(event_type="AccountingTaskTransition").count(), 2)

    def test_payment_run_updates_only_linked_bills_and_records_reference(self):
        linked = self._bill("LINKED", PurchaseBill.STATUS_APPROVED, Decimal("120.00"))
        unrelated = self._bill("OTHER", PurchaseBill.STATUS_APPROVED, Decimal("75.00"))
        payment_run = SupplierPaymentRun.objects.create(
            tenant=self.tenant,
            run_reference="RUN-1",
            scheduled_date=date.today(),
            total_amount=Decimal("120.00"),
            status=SupplierPaymentRun.STATUS_APPROVED,
        )
        SupplierPaymentRunBill.objects.create(
            tenant=self.tenant,
            payment_run=payment_run,
            bill=linked,
        )

        mark_supplier_payment_run_paid(payment_run, "practice", "BANK-123")

        payment_run.refresh_from_db()
        linked.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual(payment_run.status, SupplierPaymentRun.STATUS_PAID)
        self.assertEqual(payment_run.payment_reference, "BANK-123")
        self.assertEqual(linked.status, PurchaseBill.STATUS_PAID)
        self.assertEqual(unrelated.status, PurchaseBill.STATUS_APPROVED)
        self.assertEqual(
            AuditEvent.objects.filter(event_type="SupplierPaymentRunConfirmed").count(),
            1,
        )

    def test_payment_run_rejects_missing_reference_empty_run_and_total_mismatch(self):
        payment_run = SupplierPaymentRun.objects.create(
            tenant=self.tenant,
            run_reference="RUN-2",
            scheduled_date=date.today(),
            total_amount=Decimal("120.00"),
            status=SupplierPaymentRun.STATUS_APPROVED,
        )
        with self.assertRaisesRegex(ValueError, "payment reference"):
            mark_supplier_payment_run_paid(payment_run, "practice", "")
        with self.assertRaisesRegex(ValueError, "no supplier bills"):
            mark_supplier_payment_run_paid(payment_run, "practice", "BANK-EMPTY")

        SupplierPaymentRunBill.objects.create(
            tenant=self.tenant,
            payment_run=payment_run,
            bill=self._bill("MISMATCH", PurchaseBill.STATUS_APPROVED, Decimal("100.00")),
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            mark_supplier_payment_run_paid(payment_run, "practice", "BANK-MISMATCH")

        payment_run.refresh_from_db()
        self.assertEqual(payment_run.status, SupplierPaymentRun.STATUS_APPROVED)

    def test_database_rejects_bill_from_another_tenant(self):
        other_tenant = Tenant.objects.create(name="Other Workflow Ltd")
        other_bill = PurchaseBill.objects.create(
            tenant=other_tenant,
            bill_number="OTHER-TENANT",
            supplier_name="Other Supplier Ltd",
            bill_date=date.today(),
            due_date=date.today(),
            net_amount=Decimal("50.00"),
            vat_amount=Decimal("0.00"),
            gross_amount=Decimal("50.00"),
            status=PurchaseBill.STATUS_APPROVED,
        )
        payment_run = SupplierPaymentRun.objects.create(
            tenant=self.tenant,
            run_reference="RUN-CROSS-TENANT",
            scheduled_date=date.today(),
            total_amount=Decimal("50.00"),
            status=SupplierPaymentRun.STATUS_APPROVED,
        )

        with self.assertRaises(DatabaseError), transaction.atomic():
            SupplierPaymentRunBill.objects.create(
                tenant=self.tenant,
                payment_run=payment_run,
                bill=other_bill,
            )

    def test_sales_receipts_support_partial_then_full_payment(self):
        invoice = self._invoice("INV-1", Decimal("120.00"))

        first, invoice = record_sales_receipt(
            invoice,
            "50.00",
            "BANK-RECEIPT-1",
            "practice",
        )
        self.assertEqual(first.amount, Decimal("50.00"))
        self.assertEqual(invoice.status, SalesInvoice.STATUS_PART_PAID)
        self.assertEqual(invoice.balance_due, Decimal("70.00"))

        _, invoice = record_sales_receipt(
            invoice,
            "70.00",
            "BANK-RECEIPT-2",
            "practice",
        )
        self.assertEqual(invoice.status, SalesInvoice.STATUS_PAID)
        self.assertEqual(invoice.balance_due, Decimal("0.00"))
        self.assertEqual(SalesReceipt.objects.filter(invoice=invoice).count(), 2)
        self.assertEqual(AuditEvent.objects.filter(event_type="SalesReceiptRecorded").count(), 2)

    def test_sales_receipt_rejects_overpayment_and_duplicate_reference(self):
        invoice = self._invoice("INV-2", Decimal("100.00"))
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            record_sales_receipt(invoice, "100.01", "BANK-OVER", "practice")

        _, invoice = record_sales_receipt(invoice, "25.00", "BANK-DUP", "practice")
        with self.assertRaisesRegex(ValueError, "already been recorded"):
            record_sales_receipt(invoice, "25.00", "BANK-DUP", "practice")

        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("25.00"))

    def _bill(self, number, status, gross_amount):
        return PurchaseBill.objects.create(
            tenant=self.tenant,
            bill_number=number,
            supplier_name="Supplier Ltd",
            bill_date=date.today(),
            due_date=date.today(),
            net_amount=gross_amount,
            vat_amount=Decimal("0.00"),
            gross_amount=gross_amount,
            status=status,
        )

    def _invoice(self, number, gross_amount):
        return SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=number,
            customer_name="Customer Ltd",
            issue_date=date.today(),
            due_date=date.today(),
            net_amount=gross_amount,
            vat_amount=Decimal("0.00"),
            gross_amount=gross_amount,
            status=SalesInvoice.STATUS_ISSUED,
        )
