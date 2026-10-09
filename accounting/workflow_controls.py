"""Local controls for approval-pack release and practice task transitions."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    AccountingTask,
    AuditEvent,
    ClientApprovalRecord,
    PurchaseBill,
    SalesInvoice,
    SalesReceipt,
    SupplierPaymentRun,
)
from .reports import management_report_context


def approval_pack_preview(approval):
    report = management_report_context(approval.tenant)
    return {
        "reference": approval.reference,
        "title": approval.title,
        "status": approval.status,
        "summary": approval.summary,
        "period": approval.requested_at.date().isoformat(),
        "revenue": str(report["revenue"]),
        "expenses": str(report["expenses"]),
        "profit": str(report["profit"]),
    }


@transaction.atomic
def release_approved_pack(approval, username):
    if approval.status != ClientApprovalRecord.STATUS_APPROVED:
        raise ValueError("A pack can only be released after client approval.")
    prior = AuditEvent.objects.filter(
        tenant=approval.tenant, event_type="ApprovalPackReleased", details__approval_id=approval.id
    ).first()
    if prior:
        return prior, False
    event = AuditEvent.objects.create(
        tenant=approval.tenant, event_type="ApprovalPackReleased", username=username,
        description=f"Approved pack '{approval.title}' released to the client.",
        details={"approval_id": approval.id, "reference": approval.reference, "preview": approval_pack_preview(approval)},
    )
    return event, True


@transaction.atomic
def transition_task(task, target_status, username):
    allowed = {
        AccountingTask.STATUS_OPEN: {AccountingTask.STATUS_IN_PROGRESS},
        AccountingTask.STATUS_IN_PROGRESS: {AccountingTask.STATUS_DONE},
        AccountingTask.STATUS_DONE: set(),
    }
    if target_status not in allowed.get(task.status, set()):
        raise ValueError(f"Task cannot move from {task.status} to {target_status}.")
    previous_status = task.status
    task.status = target_status
    task.completed_at = timezone.now() if target_status == AccountingTask.STATUS_DONE else None
    task.save(update_fields=["status", "completed_at"])
    AuditEvent.objects.create(
        tenant=task.tenant, event_type="AccountingTaskTransition", username=username,
        description=f"Task '{task.title}' moved to {target_status}.",
        details={"task_id": task.id, "from": previous_status, "to": target_status},
    )
    return task


@transaction.atomic
def mark_supplier_payment_run_paid(payment_run, username, payment_reference):
    """Confirm a payment run without touching bills outside that run."""
    payment_reference = (payment_reference or "").strip()
    if not payment_reference:
        raise ValueError("Enter the bank or payment reference before confirming this run.")

    locked_run = SupplierPaymentRun.objects.select_for_update().get(pk=payment_run.pk)
    if locked_run.status == SupplierPaymentRun.STATUS_PAID:
        raise ValueError("This payment run has already been confirmed as paid.")
    if locked_run.status != SupplierPaymentRun.STATUS_APPROVED:
        raise ValueError("Only an approved payment run can be confirmed as paid.")

    bills = list(locked_run.bills.select_for_update().order_by("id"))
    if not bills:
        raise ValueError("This payment run has no supplier bills assigned to it.")
    if any(bill.tenant_id != locked_run.tenant_id for bill in bills):
        raise ValueError("A payment run cannot contain bills from another client.")
    invalid = [
        bill.bill_number
        for bill in bills
        if bill.status not in {PurchaseBill.STATUS_APPROVED, PurchaseBill.STATUS_SCHEDULED}
        or bill.balance_due <= 0
    ]
    if invalid:
        raise ValueError("Review bills that are not approved or have no balance: " + ", ".join(invalid))

    balance_total = sum((bill.balance_due for bill in bills), Decimal("0.00"))
    if balance_total != locked_run.total_amount:
        raise ValueError(
            f"Payment run total {locked_run.total_amount:.2f} does not match linked bill balances {balance_total:.2f}."
        )

    for bill in bills:
        bill.paid_amount = bill.gross_amount
        bill.status = PurchaseBill.STATUS_PAID
        bill.save(update_fields=["paid_amount", "status", "updated_at"])

    locked_run.status = SupplierPaymentRun.STATUS_PAID
    locked_run.paid_by = username
    locked_run.payment_reference = payment_reference
    locked_run.paid_at = timezone.now()
    locked_run.save(update_fields=["status", "paid_by", "payment_reference", "paid_at"])
    AuditEvent.objects.create(
        tenant=locked_run.tenant,
        event_type="SupplierPaymentRunConfirmed",
        username=username,
        description=f"Payment run {locked_run.run_reference} confirmed against linked bills.",
        details={
            "payment_run_id": locked_run.id,
            "run_reference": locked_run.run_reference,
            "payment_reference": payment_reference,
            "bill_ids": [bill.id for bill in bills],
            "total_amount": str(locked_run.total_amount),
        },
    )
    return locked_run


@transaction.atomic
def record_sales_receipt(invoice, amount, receipt_reference, username, receipt_date=None):
    """Record a customer receipt and update only its invoice balance."""
    receipt_reference = (receipt_reference or "").strip()
    if not receipt_reference:
        raise ValueError("Enter the bank or receipt reference.")
    try:
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValueError("Enter a valid receipt amount.") from exc
    if amount <= 0:
        raise ValueError("Receipt amount must be greater than zero.")

    locked_invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    if amount > locked_invoice.balance_due:
        raise ValueError("Receipt amount cannot exceed the invoice balance.")
    if SalesReceipt.objects.filter(
        tenant=locked_invoice.tenant,
        receipt_reference=receipt_reference,
    ).exists():
        raise ValueError("This receipt reference has already been recorded for the client.")

    receipt = SalesReceipt.objects.create(
        tenant=locked_invoice.tenant,
        invoice=locked_invoice,
        receipt_reference=receipt_reference,
        receipt_date=receipt_date or timezone.localdate(),
        amount=amount,
        received_by=username,
    )
    locked_invoice.paid_amount += amount
    locked_invoice.status = (
        SalesInvoice.STATUS_PAID
        if locked_invoice.balance_due == 0
        else SalesInvoice.STATUS_PART_PAID
    )
    locked_invoice.save(update_fields=["paid_amount", "status", "updated_at"])
    AuditEvent.objects.create(
        tenant=locked_invoice.tenant,
        event_type="SalesReceiptRecorded",
        username=username,
        description=f"Receipt {receipt_reference} recorded for invoice {locked_invoice.invoice_number}.",
        details={
            "receipt_id": receipt.id,
            "invoice_id": locked_invoice.id,
            "receipt_reference": receipt_reference,
            "amount": str(amount),
            "invoice_status": locked_invoice.status,
        },
    )
    return receipt, locked_invoice
