import uuid
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from accounting.models import VatReturn, JournalLine

class MockHMRCClient:
    """Mock client simulating HMRC's MTD for VAT submission endpoint."""
    @staticmethod
    def submit_vat_return(payload):
        # In a real system, this would make an authenticated OAuth2 POST request to:
        # https://api.service.hmrc.gov.uk/organisations/vat/{vrn}/returns
        # Returns mock response indicating successful submission.
        receipt_id = f"HMRC-REC-{uuid.uuid4().hex[:12].upper()}"
        return {
            "status": "success",
            "receipt_id": receipt_id,
            "processingDate": timezone.now().isoformat(),
            "paymentIndicator": "BANK" if payload["netVatDue"] > 0 else "DD",
            "chargeRefNumber": f"CHARGEREF{uuid.uuid4().hex[:8].upper()}"
        }


def serialize_vat_return_9_box(tenant, start_date, end_date):
    """
    Serializes the UK 9-Box VAT return values from the ledger:
    - Box 1: VAT due on sales (Output VAT)
    - Box 2: VAT due on acquisitions from EU (0.00 for Phase 1)
    - Box 3: Total VAT due (Box 1 + Box 2)
    - Box 4: VAT reclaimed on purchases (Input VAT)
    - Box 5: Net VAT to pay or reclaim (Box 3 - Box 4)
    - Box 6: Total value of sales (net sales total)
    - Box 7: Total value of purchases (net purchases total)
    - Box 8: Total value of EU sales (0.00)
    - Box 9: Total value of EU purchases (0.00)
    """
    # Box 1: Output VAT
    sales_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SalesInvoice", "SalesCreditNote"]
    )
    box1 = Decimal("0.00")
    for line in sales_lines:
        if line.account.code == "2200":
            box1 += (line.credit - line.debit)

    # Box 2: EU acquisitions
    box2 = Decimal("0.00")

    # Box 3: Total VAT due
    box3 = box1 + box2

    # Box 4: Input VAT
    purchase_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SupplierInvoice", "EmployeeExpense"]
    )
    box4 = Decimal("0.00")
    for line in purchase_lines:
        if line.account.code == "2200":
            box4 += (line.debit - line.credit)

    # Box 5: Net VAT due/reclaimable
    box5 = abs(box3 - box4)

    # Box 6: Net Sales (Credits starting with 4 - Debits starting with 4)
    revenue_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="4",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    )
    box6 = sum(line.credit - line.debit for line in revenue_lines)

    # Box 7: Net Purchases (Debits starting with 5 or 6 - Credits starting with 5 or 6)
    expense_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="5",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    ) | JournalLine.objects.filter(
        tenant=tenant,
        account__code__startswith="6",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    )
    box7 = sum(line.debit - line.credit for line in expense_lines)

    box8 = Decimal("0.00")
    box9 = Decimal("0.00")

    return {
        "periodKey": "26A1",  # Mock period key
        "vatDueOnOutputs": float(round(box1, 2)),
        "vatDueAcquisitions": float(round(box2, 2)),
        "totalVatDue": float(round(box3, 2)),
        "vatReclaimedCurrPeriod": float(round(box4, 2)),
        "netVatDue": float(round(box5, 2)),
        "totalValueSalesExVAT": float(round(box6, 2)),
        "totalValuePurchasesExVAT": float(round(box7, 2)),
        "totalValueGoodsSuppliedExVAT": float(round(box8, 2)),
        "totalValueGoodsAcquisitionsExVAT": float(round(box9, 2)),
        "finalised": True
    }


def submit_vat_return_to_hmrc(tenant, vat_return, period_key="26A1"):
    """
    Submits a finalized/locked VAT Return to the mock HMRC gateway.
    Updates the VatReturn record with receipt details.
    """
    if vat_return.status == "Submitted":
        raise ValueError("VAT Return has already been submitted to HMRC.")

    payload = serialize_vat_return_9_box(tenant, vat_return.start_date, vat_return.end_date)
    payload["periodKey"] = period_key

    client = MockHMRCClient()
    response = client.submit_vat_return(payload)

    with transaction.atomic():
        vat_return.status = "Submitted"
        vat_return.hmrc_receipt_id = response["receipt_id"]
        vat_return.submitted_at = datetime.fromisoformat(response["processingDate"])
        vat_return.period_key = period_key
        vat_return.save()

    return response
