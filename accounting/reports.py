import csv
import io
from decimal import Decimal

from django.db.models import Q, Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import BankReconciliation, BankTransaction, EvidenceDocument, Journal, JournalLine, VatReturn


def _sum_lines(tenant, categories, side):
    aggregate = JournalLine.objects.filter(
        tenant=tenant,
        account__category__in=categories,
    ).aggregate(total=Sum(side))
    return aggregate["total"] or Decimal("0")


def management_report_context(tenant):
    revenue = _sum_lines(tenant, ["Revenue"], "credit")
    expenses = _sum_lines(tenant, ["Expense", "Cost of Sales"], "debit")
    reconciled_ids = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    bank_count = BankTransaction.objects.filter(tenant=tenant).count()
    unreconciled_count = (
        BankTransaction.objects.filter(tenant=tenant)
        .exclude(id__in=reconciled_ids)
        .count()
    )
    vat_due = VatReturn.objects.filter(tenant=tenant).aggregate(
        total=Sum("net_vat_payable")
    )["total"] or Decimal("0")

    return {
        "tenant": tenant,
        "revenue": revenue,
        "expenses": expenses,
        "profit": revenue - expenses,
        "vat_due": vat_due,
        "bank_count": bank_count,
        "unreconciled_count": unreconciled_count,
        "journal_count": Journal.objects.filter(tenant=tenant).count(),
        "evidence_count": EvidenceDocument.objects.filter(tenant=tenant).count(),
    }


def management_report_csv(tenant):
    report = management_report_context(tenant)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Company", tenant.name])
    writer.writerow(["Revenue", report["revenue"]])
    writer.writerow(["Expenses", report["expenses"]])
    writer.writerow(["Profit", report["profit"]])
    writer.writerow(["VAT due", report["vat_due"]])
    writer.writerow(["Bank lines", report["bank_count"]])
    writer.writerow(["Unmatched bank lines", report["unreconciled_count"]])
    writer.writerow(["Bookkeeping entries", report["journal_count"]])
    writer.writerow(["Evidence documents", report["evidence_count"]])
    return output.getvalue()


def management_report_pdf(tenant):
    report = management_report_context(tenant)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"{tenant.name} management report")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("LedgerHouse Management Report", styles["Title"]),
        Paragraph(tenant.name, styles["Heading2"]),
        Spacer(1, 16),
    ]
    rows = [
        ["Metric", "Value"],
        ["Revenue", f"GBP {report['revenue']:,.2f}"],
        ["Expenses", f"GBP {report['expenses']:,.2f}"],
        ["Profit", f"GBP {report['profit']:,.2f}"],
        ["VAT due", f"GBP {report['vat_due']:,.2f}"],
        ["Bank lines", str(report["bank_count"])],
        ["Unmatched bank lines", str(report["unreconciled_count"])],
        ["Bookkeeping entries", str(report["journal_count"])],
        ["Evidence documents", str(report["evidence_count"])],
    ]
    table = Table(rows, hAlign="LEFT", colWidths=[180, 260])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b7a65")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dce6e4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
