import csv
import io
import zipfile
from decimal import Decimal

from django.db.models import Q, Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    AccountingTask,
    AccountingPeriodLock,
    BankReconciliation,
    BankTransaction,
    BankRule,
    ClientApprovalRecord,
    ClientRequest,
    ClientInvitation,
    CorporationTaxEstimate,
    DocumentIntelligenceRule,
    EvidenceDocument,
    FixedAsset,
    ImportedFile,
    Journal,
    JournalLine,
    ManagementPackSection,
    MonthEndClose,
    NominalAccount,
    NotificationEvent,
    PayrollSummary,
    PurchaseBill,
    PurchaseOrder,
    SalesInvoice,
    SalesQuote,
    SubscriptionPlan,
    StatutoryAccountsDraft,
    SupplierPaymentRun,
    VatReturn,
)


def _sum_lines(tenant, categories, side):
    aggregate = JournalLine.objects.filter(
        tenant=tenant,
        account__category__in=categories,
    ).aggregate(total=Sum(side))
    return aggregate["total"] or Decimal("0")


def management_report_context(tenant):
    revenue = _sum_lines(tenant, ["Revenue"], "credit")
    expenses = _sum_lines(tenant, ["Expense", "Cost of Sales"], "debit")
    cost_of_sales = _sum_lines(tenant, ["Cost of Sales"], "debit")
    overheads = _sum_lines(tenant, ["Expense"], "debit")
    assets = _sum_lines(tenant, ["Asset"], "debit") - _sum_lines(tenant, ["Asset"], "credit")
    liabilities = _sum_lines(tenant, ["Liability"], "credit") - _sum_lines(tenant, ["Liability"], "debit")
    equity = _sum_lines(tenant, ["Equity"], "credit") - _sum_lines(tenant, ["Equity"], "debit")
    cash = (
        JournalLine.objects.filter(
            tenant=tenant,
            account__category="Asset",
            account__canonical_taxonomy__icontains="Cash",
        ).aggregate(debits=Sum("debit"), credits=Sum("credit"))
    )
    cash_balance = (cash["debits"] or Decimal("0")) - (cash["credits"] or Decimal("0"))
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
    debtors = (
        JournalLine.objects.filter(tenant=tenant, account__code="1100")
        .aggregate(debits=Sum("debit"), credits=Sum("credit"))
    )
    creditors = (
        JournalLine.objects.filter(tenant=tenant, account__code="2100")
        .aggregate(debits=Sum("debit"), credits=Sum("credit"))
    )
    aged_debtors = (debtors["debits"] or Decimal("0")) - (debtors["credits"] or Decimal("0"))
    aged_creditors = (creditors["credits"] or Decimal("0")) - (creditors["debits"] or Decimal("0"))
    profit = revenue - expenses
    gross_profit = revenue - cost_of_sales
    gross_margin = Decimal("0")
    net_margin = Decimal("0")
    if revenue:
        gross_margin = (gross_profit / revenue * Decimal("100")).quantize(Decimal("0.01"))
        net_margin = (profit / revenue * Decimal("100")).quantize(Decimal("0.01"))
    monthly_overheads = overheads / Decimal("3") if overheads else Decimal("0")
    cash_runway_months = None
    if monthly_overheads > 0:
        cash_runway_months = (cash_balance / monthly_overheads).quantize(Decimal("0.1"))

    report = {
        "tenant": tenant,
        "revenue": revenue,
        "expenses": expenses,
        "cost_of_sales": cost_of_sales,
        "overheads": overheads,
        "gross_profit": gross_profit,
        "profit": profit,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "cash_runway_months": cash_runway_months,
        "gross_assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "net_assets": assets - liabilities,
        "cash_balance": cash_balance,
        "vat_due": vat_due,
        "aged_debtors": aged_debtors,
        "aged_creditors": aged_creditors,
        "bank_count": bank_count,
        "unreconciled_count": unreconciled_count,
        "journal_count": Journal.objects.filter(tenant=tenant).count(),
        "evidence_count": EvidenceDocument.objects.filter(tenant=tenant).count(),
        "open_client_requests": ClientRequest.objects.filter(tenant=tenant).exclude(status="Resolved").count(),
        "unreviewed_evidence": EvidenceDocument.objects.filter(tenant=tenant).exclude(review_status="ReadyForPosting").count(),
    }
    latest_close = MonthEndClose.objects.filter(tenant=tenant).order_by("-period_end").first()
    report["month_end"] = {
        "period_end": latest_close.period_end if latest_close else None,
        "status": latest_close.get_status_display() if latest_close else "Not started",
        "checklist_complete": bool(latest_close and latest_close.checklist_complete),
        "locked": bool(latest_close and AccountingPeriodLock.objects.filter(
            tenant=tenant, period_start=latest_close.period_start, period_end=latest_close.period_end,
            status=AccountingPeriodLock.STATUS_LOCKED,
        ).exists()),
    }
    report["action_points"] = management_action_points(report)
    report["plain_english_summary"] = management_plain_english_summary(report)
    report["workflow_board"] = management_workflow_board(tenant)
    report["local_accounting_adjustments"] = local_accounting_adjustments(tenant, report)
    return report


def management_plain_english_summary(report):
    summary = []
    if report["profit"] > Decimal("0"):
        summary.append(f"The business is showing a local accounting profit of {_money(report['profit'])}.")
    elif report["profit"] < Decimal("0"):
        summary.append(f"The business is showing a local accounting loss of {_money(abs(report['profit']))}.")
    else:
        summary.append("The local records currently show break-even trading.")
    if report["aged_debtors"] > Decimal("0"):
        summary.append(f"Customers still owe {_money(report['aged_debtors'])}, so debtor follow-up remains important.")
    if report["aged_creditors"] > Decimal("0"):
        summary.append(f"Supplier payments of {_money(report['aged_creditors'])} need planning.")
    if report["cash_runway_months"] is None:
        summary.append("Cash runway cannot be calculated until more spending history is available.")
    elif report["cash_runway_months"] < Decimal("3"):
        summary.append(f"Cash runway is short at about {report['cash_runway_months']} month(s).")
    else:
        summary.append(f"Cash runway is about {report['cash_runway_months']} month(s) based on local records.")
    return summary


def management_workflow_board(tenant):
    stages = [
        ("Inbox", EvidenceDocument.objects.filter(tenant=tenant, review_status="Unreviewed").count()),
        ("Evidence review", EvidenceDocument.objects.filter(tenant=tenant).exclude(review_status="ReadyForPosting").count()),
        ("Bank matching", BankTransaction.objects.filter(tenant=tenant).exclude(id__in=BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")).count()),
        ("Client questions", ClientRequest.objects.filter(tenant=tenant).exclude(status="Resolved").count()),
        ("Approvals", ClientApprovalRecord.objects.filter(tenant=tenant, status=ClientApprovalRecord.STATUS_PENDING).count()),
        ("Reports ready", ManagementPackSection.objects.filter(tenant=tenant, status=ManagementPackSection.STATUS_REVIEWED).count()),
    ]
    return [
        {
            "stage": stage,
            "count": count,
            "status": "Clear" if count == 0 else "Action needed",
        }
        for stage, count in stages
    ]


def local_accounting_adjustments(tenant, report):
    fixed_assets = FixedAsset.objects.filter(tenant=tenant)
    payroll = PayrollSummary.objects.filter(tenant=tenant).order_by("-period_end").first()
    tax_estimate = CorporationTaxEstimate.objects.filter(tenant=tenant).order_by("-period_end").first()
    depreciation_remaining = sum((asset.cost - asset.accumulated_depreciation for asset in fixed_assets), Decimal("0.00"))
    adjustments = [
        {
            "label": "Depreciation review",
            "value": depreciation_remaining,
            "detail": "Review remaining fixed asset net book value before finalising month-end.",
        },
        {
            "label": "Payroll liabilities",
            "value": (payroll.paye + payroll.employee_ni + payroll.employer_ni + payroll.pension) if payroll else Decimal("0.00"),
            "detail": "Check PAYE, NI and pension control balances against payroll summaries.",
        },
        {
            "label": "Corporation tax estimate",
            "value": tax_estimate.estimated_tax if tax_estimate else Decimal("0.00"),
            "detail": "Use local estimate for management planning; live filing remains externally blocked.",
        },
        {
            "label": "Working capital pressure",
            "value": report["aged_debtors"] - report["aged_creditors"],
            "detail": "Positive means more customer cash is due than supplier payments recorded locally.",
        },
    ]
    return adjustments


def management_action_points(report):
    points = []
    if report["unreviewed_evidence"]:
        points.append(
            f"Review {report['unreviewed_evidence']} uploaded document(s) before finalising the bookkeeping."
        )
    if report["unreconciled_count"]:
        points.append(
            f"Explain or match {report['unreconciled_count']} bank transaction(s) before relying on the figures."
        )
    if report["open_client_requests"]:
        points.append(
            f"Respond to {report['open_client_requests']} open client question(s) from the accounts team."
        )
    if report["aged_debtors"] > Decimal("0"):
        points.append(f"Chase or review debtors of {_money(report['aged_debtors'])}.")
    if report["aged_creditors"] > Decimal("0"):
        points.append(f"Plan supplier payments for creditors of {_money(report['aged_creditors'])}.")
    if report["cash_runway_months"] is not None and report["cash_runway_months"] < Decimal("3"):
        points.append(f"Review cash runway of {report['cash_runway_months']} month(s).")
    if not report["month_end"]["checklist_complete"]:
        points.append("Complete the latest month-end control checklist before treating the figures as closed.")
    elif not report["month_end"]["locked"]:
        points.append("The latest month-end checklist is complete but the accounting period has not yet been locked.")
    if not points:
        points.append("No immediate local action points were identified from the current records.")
    return points


def management_report_csv(tenant):
    report = management_report_context(tenant)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Company", tenant.name])
    writer.writerow(["Revenue", report["revenue"]])
    writer.writerow(["Expenses", report["expenses"]])
    writer.writerow(["Cost of sales", report["cost_of_sales"]])
    writer.writerow(["Overheads", report["overheads"]])
    writer.writerow(["Gross profit", report["gross_profit"]])
    writer.writerow(["Profit", report["profit"]])
    writer.writerow(["Gross margin %", report["gross_margin"]])
    writer.writerow(["Net margin %", report["net_margin"]])
    writer.writerow(["Cash runway months", report["cash_runway_months"] or "Not enough data"])
    writer.writerow(["Cash balance", report["cash_balance"]])
    writer.writerow(["Gross assets", report["gross_assets"]])
    writer.writerow(["Liabilities", report["liabilities"]])
    writer.writerow(["Net assets", report["net_assets"]])
    writer.writerow(["Equity", report["equity"]])
    writer.writerow(["VAT due", report["vat_due"]])
    writer.writerow(["Aged debtors", report["aged_debtors"]])
    writer.writerow(["Aged creditors", report["aged_creditors"]])
    writer.writerow(["Bank lines", report["bank_count"]])
    writer.writerow(["Unmatched bank lines", report["unreconciled_count"]])
    writer.writerow(["Bookkeeping entries", report["journal_count"]])
    writer.writerow(["Evidence documents", report["evidence_count"]])
    writer.writerow(["Unreviewed evidence", report["unreviewed_evidence"]])
    writer.writerow(["Open client questions", report["open_client_requests"]])
    writer.writerow([])
    writer.writerow(["Plain-English summary", "Detail"])
    for index, summary in enumerate(report["plain_english_summary"], start=1):
        writer.writerow([index, summary])
    writer.writerow([])
    writer.writerow(["Workflow stage", "Count", "Status"])
    for item in report["workflow_board"]:
        writer.writerow([item["stage"], item["count"], item["status"]])
    writer.writerow([])
    writer.writerow(["Local accounting adjustment", "Value", "Detail"])
    for item in report["local_accounting_adjustments"]:
        writer.writerow([item["label"], item["value"], item["detail"]])
    writer.writerow([])
    writer.writerow(["Action point", "Detail"])
    for index, point in enumerate(report["action_points"], start=1):
        writer.writerow([index, point])
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
        ["Gross profit", f"GBP {report['gross_profit']:,.2f}"],
        ["Profit", f"GBP {report['profit']:,.2f}"],
        ["Gross margin", f"{report['gross_margin']}%"],
        ["Net margin", f"{report['net_margin']}%"],
        ["Cash runway", f"{report['cash_runway_months']} months" if report["cash_runway_months"] is not None else "Not enough data"],
        ["Cash balance", f"GBP {report['cash_balance']:,.2f}"],
        ["Gross assets", f"GBP {report['gross_assets']:,.2f}"],
        ["Liabilities", f"GBP {report['liabilities']:,.2f}"],
        ["Net assets", f"GBP {report['net_assets']:,.2f}"],
        ["Equity", f"GBP {report['equity']:,.2f}"],
        ["VAT due", f"GBP {report['vat_due']:,.2f}"],
        ["Aged debtors", f"GBP {report['aged_debtors']:,.2f}"],
        ["Aged creditors", f"GBP {report['aged_creditors']:,.2f}"],
        ["Bank lines", str(report["bank_count"])],
        ["Unmatched bank lines", str(report["unreconciled_count"])],
        ["Bookkeeping entries", str(report["journal_count"])],
        ["Evidence documents", str(report["evidence_count"])],
        ["Unreviewed evidence", str(report["unreviewed_evidence"])],
        ["Open client questions", str(report["open_client_requests"])],
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
    story.append(Spacer(1, 16))
    story.append(Paragraph("Plain-English summary", styles["Heading1"]))
    for summary in report["plain_english_summary"]:
        story.append(Paragraph(summary, styles["BodyText"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Workflow board", styles["Heading1"]))
    story.append(
        _styled_table(
            [["Stage", "Count", "Status"]]
            + [[item["stage"], str(item["count"]), item["status"]] for item in report["workflow_board"]]
        )
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph("Local accounting adjustments", styles["Heading1"]))
    story.append(
        _styled_table(
            [["Adjustment", "Value", "Detail"]]
            + [
                [item["label"], f"GBP {item['value']:,.2f}", item["detail"]]
                for item in report["local_accounting_adjustments"]
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(Paragraph("Action points", styles["Heading1"]))
    story.append(_styled_table([["No.", "Action"]] + [[str(index), point] for index, point in enumerate(report["action_points"], start=1)]))
    doc.build(story)
    return buffer.getvalue()


def _money(value):
    return f"GBP {value:,.2f}"


def monthly_profit_rows(tenant):
    journals = Journal.objects.filter(tenant=tenant).order_by("date")
    months = {}
    for journal in journals:
        key = journal.date.strftime("%Y-%m")
        months.setdefault(key, {"revenue": Decimal("0"), "expenses": Decimal("0")})
        for line in journal.lines.select_related("account"):
            if line.account.category == "Revenue":
                months[key]["revenue"] += line.credit
            if line.account.category in {"Expense", "Cost of Sales"}:
                months[key]["expenses"] += line.debit
    rows = []
    for key, values in sorted(months.items()):
        rows.append([
            key,
            _money(values["revenue"]),
            _money(values["expenses"]),
            _money(values["revenue"] - values["expenses"]),
        ])
    return rows


def management_report_pack_pdf(tenant):
    report = management_report_context(tenant)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"{tenant.name} LedgerHouse management pack")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("LedgerHouse Management Accounts Pack", styles["Title"]),
        Paragraph(tenant.name, styles["Heading2"]),
        Paragraph("Prepared from current local ledger, banking, VAT and evidence records.", styles["BodyText"]),
        Spacer(1, 16),
    ]

    summary_rows = [
        ["Metric", "Value"],
        ["Revenue", _money(report["revenue"])],
        ["Expenses", _money(report["expenses"])],
        ["Gross profit", _money(report["gross_profit"])],
        ["Profit", _money(report["profit"])],
        ["Gross margin", f"{report['gross_margin']}%"],
        ["Net margin", f"{report['net_margin']}%"],
        ["Cash runway", f"{report['cash_runway_months']} months" if report["cash_runway_months"] is not None else "Not enough data"],
        ["Cash balance", _money(report["cash_balance"])],
        ["Net assets", _money(report["net_assets"])],
        ["VAT due", _money(report["vat_due"])],
        ["Aged debtors", _money(report["aged_debtors"])],
        ["Aged creditors", _money(report["aged_creditors"])],
        ["Open client questions", str(report["open_client_requests"])],
        ["Evidence still in review", str(report["unreviewed_evidence"])],
    ]
    story.append(Paragraph("Executive summary", styles["Heading1"]))
    story.append(_styled_table(summary_rows))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Action points", styles["Heading1"]))
    story.append(_styled_table([["No.", "Action"]] + [[str(index), point] for index, point in enumerate(report["action_points"], start=1)]))
    story.append(PageBreak())

    story.append(Paragraph("Balance sheet style summary", styles["Heading1"]))
    story.append(_styled_table([
        ["Area", "Value"],
        ["Gross assets", _money(report["gross_assets"])],
        ["Liabilities", _money(report["liabilities"])],
        ["Net assets", _money(report["net_assets"])],
        ["Equity", _money(report["equity"])],
        ["Cash balance", _money(report["cash_balance"])],
        ["Aged debtors", _money(report["aged_debtors"])],
        ["Aged creditors", _money(report["aged_creditors"])],
    ]))
    story.append(Spacer(1, 16))

    monthly_rows = [["Month", "Revenue", "Expenses", "Profit"]] + (monthly_profit_rows(tenant) or [["No data", "GBP 0.00", "GBP 0.00", "GBP 0.00"]])
    story.append(Paragraph("Profit and loss by month", styles["Heading1"]))
    story.append(_styled_table(monthly_rows))
    story.append(PageBreak())

    vat_rows = [["Period", "Status", "Net VAT", "Receipt"]]
    for vat_return in VatReturn.objects.filter(tenant=tenant).order_by("-end_date")[:12]:
        vat_rows.append([
            f"{vat_return.start_date} to {vat_return.end_date}",
            vat_return.status,
            _money(vat_return.net_vat_payable),
            vat_return.hmrc_receipt_id or "Not recorded",
        ])
    if len(vat_rows) == 1:
        vat_rows.append(["No VAT returns", "-", "GBP 0.00", "-"])
    story.append(Paragraph("VAT and filing summary", styles["Heading1"]))
    story.append(_styled_table(vat_rows))
    story.append(Spacer(1, 16))

    workflow_rows = [
        ["Workflow", "Count"],
        ["Bank lines", str(report["bank_count"])],
        ["Unmatched bank lines", str(report["unreconciled_count"])],
        ["Bookkeeping entries", str(report["journal_count"])],
        ["Evidence documents", str(report["evidence_count"])],
        ["Unreviewed evidence", str(report["unreviewed_evidence"])],
        ["Open client questions", str(report["open_client_requests"])],
    ]
    story.append(Paragraph("Workflow status", styles["Heading1"]))
    story.append(_styled_table(workflow_rows))
    doc.build(story)
    return buffer.getvalue()


def _styled_table(rows):
    table = Table(rows, hAlign="LEFT", colWidths=[180, 260] if len(rows[0]) == 2 else None)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b7a65")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dce6e4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def accounts_department_pack_pdf(tenant):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"{tenant.name} accounts department pack")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("LedgerHouse Accounts Department Pack", styles["Title"]),
        Paragraph(tenant.name, styles["Heading2"]),
        Paragraph(
            "Prepared from local sales, purchase, month-end, payroll, tax, statutory accounts, task and notification records.",
            styles["BodyText"],
        ),
        Spacer(1, 16),
    ]

    sales = SalesInvoice.objects.filter(tenant=tenant).order_by("due_date", "invoice_number")
    quotes = SalesQuote.objects.filter(tenant=tenant).order_by("-issue_date", "quote_number")
    purchases = PurchaseBill.objects.filter(tenant=tenant).order_by("due_date", "bill_number")
    purchase_orders = PurchaseOrder.objects.filter(tenant=tenant).order_by("-order_date", "order_number")
    payment_runs = SupplierPaymentRun.objects.filter(tenant=tenant).order_by("-scheduled_date")
    bank_rules = BankRule.objects.filter(tenant=tenant).order_by("name")
    month_ends = MonthEndClose.objects.filter(tenant=tenant).order_by("-period_end")
    period_locks = AccountingPeriodLock.objects.filter(tenant=tenant).order_by("-period_end")
    assets = FixedAsset.objects.filter(tenant=tenant).order_by("asset_name")
    payroll = PayrollSummary.objects.filter(tenant=tenant).order_by("-period_end")
    tax = CorporationTaxEstimate.objects.filter(tenant=tenant).order_by("-period_end")
    drafts = StatutoryAccountsDraft.objects.filter(tenant=tenant).order_by("-period_end")
    pack_sections = ManagementPackSection.objects.filter(tenant=tenant).order_by("-period_end", "section_name")
    document_rules = DocumentIntelligenceRule.objects.filter(tenant=tenant).order_by("name")
    approvals = ClientApprovalRecord.objects.filter(tenant=tenant).order_by("status", "-requested_at")
    tasks = AccountingTask.objects.filter(tenant=tenant).order_by("status", "-priority", "due_date")
    notifications = NotificationEvent.objects.filter(tenant=tenant).order_by("-created_at")

    story.append(Paragraph("Operating summary", styles["Heading1"]))
    story.append(_styled_table([
        ["Area", "Local records"],
        ["Sales quotes", str(quotes.count())],
        ["Sales invoices", str(sales.count())],
        ["Purchase orders", str(purchase_orders.count())],
        ["Purchase bills", str(purchases.count())],
        ["Supplier payment runs", str(payment_runs.count())],
        ["Bank rules", str(bank_rules.count())],
        ["Month-end close files", str(month_ends.count())],
        ["Period locks", str(period_locks.count())],
        ["Fixed assets", str(assets.count())],
        ["Payroll summaries", str(payroll.count())],
        ["Corporation tax estimates", str(tax.count())],
        ["Statutory accounts drafts", str(drafts.count())],
        ["Management pack sections", str(pack_sections.count())],
        ["Document intelligence rules", str(document_rules.count())],
        ["Client approval items", str(approvals.count())],
        ["Open tasks", str(tasks.exclude(status=AccountingTask.STATUS_DONE).count())],
        ["Notification events", str(notifications.count())],
    ]))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Sales ledger", styles["Heading1"]))
    quote_rows = [["Quote", "Customer", "Expiry", "Gross", "Status"]]
    for quote in quotes[:12]:
        quote_rows.append([
            quote.quote_number,
            quote.customer_name,
            str(quote.expiry_date),
            _money(quote.gross_amount),
            quote.get_status_display(),
        ])
    if len(quote_rows) == 1:
        quote_rows.append(["No records", "-", "-", "GBP 0.00", "-"])
    story.append(_styled_table(quote_rows))
    story.append(Spacer(1, 14))

    sales_rows = [["Invoice", "Customer", "Due", "Gross", "Paid", "Status"]]
    for invoice in sales[:20]:
        sales_rows.append([
            invoice.invoice_number,
            invoice.customer_name,
            str(invoice.due_date),
            _money(invoice.gross_amount),
            _money(invoice.paid_amount),
            invoice.get_status_display(),
        ])
    if len(sales_rows) == 1:
        sales_rows.append(["No records", "-", "-", "GBP 0.00", "GBP 0.00", "-"])
    story.append(_styled_table(sales_rows))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Purchase ledger and supplier payments", styles["Heading1"]))
    po_rows = [["Order", "Supplier", "Expected", "Gross", "Status"]]
    for order in purchase_orders[:12]:
        po_rows.append([
            order.order_number,
            order.supplier_name,
            str(order.expected_date or ""),
            _money(order.gross_amount),
            order.get_status_display(),
        ])
    if len(po_rows) == 1:
        po_rows.append(["No records", "-", "-", "GBP 0.00", "-"])
    story.append(_styled_table(po_rows))
    story.append(Spacer(1, 14))

    purchase_rows = [["Bill", "Supplier", "Due", "Gross", "Paid", "Status"]]
    for bill in purchases[:20]:
        purchase_rows.append([
            bill.bill_number,
            bill.supplier_name,
            str(bill.due_date),
            _money(bill.gross_amount),
            _money(bill.paid_amount),
            bill.get_status_display(),
        ])
    if len(purchase_rows) == 1:
        purchase_rows.append(["No records", "-", "-", "GBP 0.00", "GBP 0.00", "-"])
    story.append(_styled_table(purchase_rows))
    for run in payment_runs[:8]:
        story.append(Paragraph(f"{run.run_reference}: {run.get_status_display()} for {_money(run.total_amount)} on {run.scheduled_date}", styles["BodyText"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Bank rules and reconciliation intelligence", styles["Heading1"]))
    bank_rule_rows = [["Rule", "Match text", "Account", "Action", "Confidence"]]
    for rule in bank_rules[:12]:
        bank_rule_rows.append([rule.name, rule.match_text, rule.account_code, rule.get_action_display(), f"{rule.confidence}%"])
    if len(bank_rule_rows) == 1:
        bank_rule_rows.append(["No records", "-", "-", "-", "0%"])
    story.append(_styled_table(bank_rule_rows))
    story.append(PageBreak())

    story.append(Paragraph("Month-end and assets", styles["Heading1"]))
    close_rows = [["Period", "Status", "Bank", "Accruals", "Payroll", "Review"]]
    for close in month_ends[:12]:
        close_rows.append([
            f"{close.period_start} to {close.period_end}",
            close.get_status_display(),
            "Done" if close.bank_reconciled else "Open",
            "Done" if close.accruals_posted else "Open",
            "Done" if close.payroll_posted else "Open",
            "Signed" if close.review_signed_off else "Open",
        ])
    if len(close_rows) == 1:
        close_rows.append(["No records", "-", "-", "-", "-", "-"])
    story.append(_styled_table(close_rows))
    story.append(Spacer(1, 14))

    lock_rows = [["Period", "Status", "Locked by", "Reason"]]
    for lock in period_locks[:12]:
        lock_rows.append([f"{lock.period_start} to {lock.period_end}", lock.get_status_display(), lock.locked_by, lock.reason])
    if len(lock_rows) == 1:
        lock_rows.append(["No records", "-", "-", "-"])
    story.append(_styled_table(lock_rows))
    story.append(Spacer(1, 14))

    asset_rows = [["Asset", "Cost", "Depreciation", "NBV", "Status"]]
    for asset in assets[:20]:
        asset_rows.append([
            asset.asset_name,
            _money(asset.cost),
            _money(asset.accumulated_depreciation),
            _money(asset.net_book_value),
            asset.status,
        ])
    if len(asset_rows) == 1:
        asset_rows.append(["No records", "GBP 0.00", "GBP 0.00", "GBP 0.00", "-"])
    story.append(_styled_table(asset_rows))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Payroll, CIS and corporation tax", styles["Heading1"]))
    payroll_rows = [["Period", "Gross pay", "PAYE", "Employee NI", "Employer NI", "Status"]]
    for summary in payroll[:12]:
        payroll_rows.append([
            f"{summary.period_start} to {summary.period_end}",
            _money(summary.gross_pay),
            _money(summary.paye),
            _money(summary.employee_ni),
            _money(summary.employer_ni),
            summary.status,
        ])
    if len(payroll_rows) == 1:
        payroll_rows.append(["No records", "GBP 0.00", "GBP 0.00", "GBP 0.00", "GBP 0.00", "-"])
    story.append(_styled_table(payroll_rows))
    story.append(Spacer(1, 14))

    tax_rows = [["Period end", "Taxable profit", "Tax rate", "Estimated tax", "Status"]]
    for estimate in tax[:8]:
        tax_rows.append([
            str(estimate.period_end),
            _money(estimate.taxable_profit),
            f"{estimate.tax_rate}%",
            _money(estimate.estimated_tax),
            estimate.status,
        ])
    if len(tax_rows) == 1:
        tax_rows.append(["No records", "GBP 0.00", "0%", "GBP 0.00", "-"])
    story.append(_styled_table(tax_rows))
    story.append(PageBreak())

    story.append(Paragraph("Statutory accounts readiness", styles["Heading1"]))
    statutory_rows = [["Period", "Type", "Status", "Balance sheet", "Notes", "Client", "iXBRL"]]
    for draft in drafts[:8]:
        statutory_rows.append([
            str(draft.period_end),
            draft.accounts_type,
            draft.get_status_display(),
            "Ready" if draft.balance_sheet_ready else "Open",
            "Ready" if draft.notes_ready else "Open",
            "Approved" if draft.client_approved else "Open",
            "Ready" if draft.ixbrl_ready else "Not ready",
        ])
    if len(statutory_rows) == 1:
        statutory_rows.append(["No records", "-", "-", "-", "-", "-", "-"])
    story.append(_styled_table(statutory_rows))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Management commentary and document intelligence", styles["Heading1"]))
    commentary_rows = [["Section", "Period end", "Status", "Owner"]]
    for section in pack_sections[:12]:
        commentary_rows.append([section.section_name, str(section.period_end), section.get_status_display(), section.owner or "Unassigned"])
    if len(commentary_rows) == 1:
        commentary_rows.append(["No records", "-", "-", "-"])
    story.append(_styled_table(commentary_rows))
    story.append(Spacer(1, 14))

    intelligence_rows = [["Rule", "Keyword", "Category", "Account", "Confidence"]]
    for rule in document_rules[:12]:
        intelligence_rows.append([rule.name, rule.keyword, rule.get_document_category_display(), rule.suggested_account_code, f"{rule.confidence}%"])
    if len(intelligence_rows) == 1:
        intelligence_rows.append(["No records", "-", "-", "-", "0%"])
    story.append(_styled_table(intelligence_rows))
    story.append(Spacer(1, 16))

    approval_rows = [["Type", "Title", "Status", "Decided by"]]
    for approval in approvals[:12]:
        approval_rows.append([
            approval.get_approval_type_display(),
            approval.title,
            approval.get_status_display(),
            approval.decided_by or "Waiting",
        ])
    if len(approval_rows) == 1:
        approval_rows.append(["No records", "-", "-", "-"])
    story.append(Paragraph("Client approvals", styles["Heading1"]))
    story.append(_styled_table(approval_rows))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Practice work queue and notifications", styles["Heading1"]))
    task_rows = [["Phase", "Task", "Priority", "Status", "Owner"]]
    for task in tasks[:20]:
        task_rows.append([task.phase, task.title, task.priority, task.status, task.owner or "Unassigned"])
    if len(task_rows) == 1:
        task_rows.append(["No records", "-", "-", "-", "-"])
    story.append(_styled_table(task_rows))
    story.append(Spacer(1, 14))

    notification_rows = [["Channel", "Recipient", "Subject", "Status"]]
    for event in notifications[:10]:
        notification_rows.append([event.channel, event.recipient, event.subject, event.status])
    if len(notification_rows) == 1:
        notification_rows.append(["No records", "-", "-", "-"])
    story.append(_styled_table(notification_rows))

    doc.build(story)
    return buffer.getvalue()


def _csv_bytes(headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def client_data_export_zip(tenant):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as export:
        export.writestr(
            "README.txt",
            (
                "LedgerHouse client data export\n"
                f"Company: {tenant.name}\n"
                "This package contains accounting records, source file indexes, "
                "client questions, VAT records and uploaded evidence files for "
                "provider switching or client archive purposes.\n"
            ),
        )
        export.writestr(
            "nominal_accounts.csv",
            _csv_bytes(
                ["id", "code", "name", "category", "canonical_taxonomy"],
                NominalAccount.objects.filter(tenant=tenant)
                .order_by("code")
                .values_list("id", "code", "name", "category", "canonical_taxonomy"),
            ),
        )
        export.writestr(
            "journals.csv",
            _csv_bytes(
                ["id", "date", "source_type", "source_id", "status", "description", "created_by"],
                Journal.objects.filter(tenant=tenant)
                .order_by("date", "id")
                .values_list("id", "date", "source_type", "source_id", "status", "description", "created_by"),
            ),
        )
        export.writestr(
            "journal_lines.csv",
            _csv_bytes(
                [
                    "id",
                    "journal_id",
                    "account_code",
                    "account_name",
                    "debit",
                    "credit",
                    "vat_code",
                    "vat_rate",
                    "vat_amount",
                    "department",
                ],
                JournalLine.objects.filter(tenant=tenant)
                .select_related("account")
                .order_by("journal_id", "id")
                .values_list(
                    "id",
                    "journal_id",
                    "account__code",
                    "account__name",
                    "debit",
                    "credit",
                    "vat_code",
                    "vat_rate",
                    "vat_amount",
                    "department",
                ),
            ),
        )
        export.writestr(
            "imported_files.csv",
            _csv_bytes(
                ["id", "filename", "uploaded_at", "file_hash"],
                ImportedFile.objects.filter(tenant=tenant)
                .order_by("uploaded_at", "id")
                .values_list("id", "filename", "uploaded_at", "file_hash"),
            ),
        )
        export.writestr(
            "bank_transactions.csv",
            _csv_bytes(
                ["id", "imported_file_id", "date", "amount", "reference", "fitid", "review_status", "reviewed_by"],
                BankTransaction.objects.filter(tenant=tenant)
                .order_by("date", "id")
                .values_list("id", "imported_file_id", "date", "amount", "reference", "fitid", "review_status", "reviewed_by"),
            ),
        )
        export.writestr(
            "vat_returns.csv",
            _csv_bytes(
                [
                    "id",
                    "start_date",
                    "end_date",
                    "period_key",
                    "status",
                    "total_output_vat",
                    "total_input_vat",
                    "net_vat_payable",
                    "hmrc_receipt_id",
                ],
                VatReturn.objects.filter(tenant=tenant)
                .order_by("start_date", "id")
                .values_list(
                    "id",
                    "start_date",
                    "end_date",
                    "period_key",
                    "status",
                    "total_output_vat",
                    "total_input_vat",
                    "net_vat_payable",
                    "hmrc_receipt_id",
                ),
            ),
        )
        export.writestr(
            "client_requests.csv",
            _csv_bytes(
                ["id", "subject", "category", "priority", "status", "submitted_by", "submitted_at", "resolved_by"],
                ClientRequest.objects.filter(tenant=tenant)
                .order_by("submitted_at", "id")
                .values_list("id", "subject", "category", "priority", "status", "submitted_by", "submitted_at", "resolved_by"),
            ),
        )
        evidence_rows = []
        for document in EvidenceDocument.objects.filter(tenant=tenant).order_by("uploaded_at", "id"):
            evidence_path = f"evidence/{document.id}-{document.filename}"
            evidence_rows.append(
                [
                    document.id,
                    document.filename,
                    evidence_path,
                    document.content_type,
                    document.uploaded_at,
                    document.uploaded_by,
                    document.review_status,
                    document.reviewed_by,
                    document.document_category,
                    document.supplier_or_customer,
                    document.document_date,
                    document.gross_amount,
                    document.vat_amount,
                    document.suggested_account_code,
                    document.review_note,
                ]
            )
            export.writestr(evidence_path, bytes(document.file_content))
        export.writestr(
            "evidence_documents.csv",
            _csv_bytes(
                [
                    "id",
                    "filename",
                    "export_path",
                    "content_type",
                    "uploaded_at",
                    "uploaded_by",
                    "review_status",
                    "reviewed_by",
                    "document_category",
                    "supplier_or_customer",
                    "document_date",
                    "gross_amount",
                    "vat_amount",
                    "suggested_account_code",
                    "review_note",
                ],
                evidence_rows,
            ),
        )
        export.writestr(
            "client_invitations.csv",
            _csv_bytes(
                ["id", "email", "role", "status", "invited_by", "invited_at", "accepted_at", "accepted_by"],
                ClientInvitation.objects.filter(tenant=tenant)
                .order_by("invited_at", "email")
                .values_list("id", "email", "role", "status", "invited_by", "invited_at", "accepted_at", "accepted_by"),
            ),
        )
        export.writestr(
            "subscription.csv",
            _csv_bytes(
                [
                    "plan_name",
                    "status",
                    "monthly_price",
                    "currency",
                    "billing_provider",
                    "collection_method",
                    "provider_customer_id",
                    "provider_subscription_id",
                    "latest_invoice_status",
                    "next_invoice_date",
                    "last_payment_at",
                    "billing_note",
                ],
                SubscriptionPlan.objects.filter(tenant=tenant)
                .values_list(
                    "plan_name",
                    "status",
                    "monthly_price",
                    "currency",
                    "billing_provider",
                    "collection_method",
                    "provider_customer_id",
                    "provider_subscription_id",
                    "latest_invoice_status",
                    "next_invoice_date",
                    "last_payment_at",
                    "billing_note",
                ),
            ),
        )
        export.writestr(
            "sales_quotes.csv",
            _csv_bytes(
                [
                    "id",
                    "quote_number",
                    "customer_name",
                    "issue_date",
                    "expiry_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "status",
                    "converted_invoice_id",
                    "notes",
                ],
                SalesQuote.objects.filter(tenant=tenant)
                .order_by("issue_date", "quote_number")
                .values_list(
                    "id",
                    "quote_number",
                    "customer_name",
                    "issue_date",
                    "expiry_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "status",
                    "converted_invoice_id",
                    "notes",
                ),
            ),
        )
        export.writestr(
            "sales_invoices.csv",
            _csv_bytes(
                [
                    "id",
                    "invoice_number",
                    "customer_name",
                    "issue_date",
                    "due_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "paid_amount",
                    "status",
                    "notes",
                ],
                SalesInvoice.objects.filter(tenant=tenant)
                .order_by("issue_date", "invoice_number")
                .values_list(
                    "id",
                    "invoice_number",
                    "customer_name",
                    "issue_date",
                    "due_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "paid_amount",
                    "status",
                    "notes",
                ),
            ),
        )
        export.writestr(
            "purchase_orders.csv",
            _csv_bytes(
                [
                    "id",
                    "order_number",
                    "supplier_name",
                    "order_date",
                    "expected_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "status",
                    "approved_by",
                    "linked_bill_id",
                    "notes",
                ],
                PurchaseOrder.objects.filter(tenant=tenant)
                .order_by("order_date", "order_number")
                .values_list(
                    "id",
                    "order_number",
                    "supplier_name",
                    "order_date",
                    "expected_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "status",
                    "approved_by",
                    "linked_bill_id",
                    "notes",
                ),
            ),
        )
        export.writestr(
            "purchase_bills.csv",
            _csv_bytes(
                [
                    "id",
                    "bill_number",
                    "supplier_name",
                    "bill_date",
                    "due_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "paid_amount",
                    "status",
                    "approval_note",
                ],
                PurchaseBill.objects.filter(tenant=tenant)
                .order_by("bill_date", "bill_number")
                .values_list(
                    "id",
                    "bill_number",
                    "supplier_name",
                    "bill_date",
                    "due_date",
                    "net_amount",
                    "vat_amount",
                    "gross_amount",
                    "paid_amount",
                    "status",
                    "approval_note",
                ),
            ),
        )
        export.writestr(
            "supplier_payment_runs.csv",
            _csv_bytes(
                ["id", "run_reference", "scheduled_date", "total_amount", "status", "approved_by", "paid_at"],
                SupplierPaymentRun.objects.filter(tenant=tenant)
                .order_by("scheduled_date", "run_reference")
                .values_list("id", "run_reference", "scheduled_date", "total_amount", "status", "approved_by", "paid_at"),
            ),
        )
        export.writestr(
            "bank_rules.csv",
            _csv_bytes(
                ["id", "name", "match_text", "account_code", "action", "confidence", "is_active"],
                BankRule.objects.filter(tenant=tenant)
                .order_by("name")
                .values_list("id", "name", "match_text", "account_code", "action", "confidence", "is_active"),
            ),
        )
        export.writestr(
            "month_end_closes.csv",
            _csv_bytes(
                [
                    "id",
                    "period_start",
                    "period_end",
                    "bank_reconciled",
                    "accruals_posted",
                    "prepayments_posted",
                    "depreciation_posted",
                    "payroll_posted",
                    "review_signed_off",
                    "status",
                    "closed_by",
                    "closed_at",
                ],
                MonthEndClose.objects.filter(tenant=tenant)
                .order_by("period_start", "period_end")
                .values_list(
                    "id",
                    "period_start",
                    "period_end",
                    "bank_reconciled",
                    "accruals_posted",
                    "prepayments_posted",
                    "depreciation_posted",
                    "payroll_posted",
                    "review_signed_off",
                    "status",
                    "closed_by",
                    "closed_at",
                ),
            ),
        )
        export.writestr(
            "accounting_period_locks.csv",
            _csv_bytes(
                ["id", "period_start", "period_end", "status", "locked_by", "locked_at", "reason"],
                AccountingPeriodLock.objects.filter(tenant=tenant)
                .order_by("period_start", "period_end")
                .values_list("id", "period_start", "period_end", "status", "locked_by", "locked_at", "reason"),
            ),
        )
        export.writestr(
            "fixed_assets.csv",
            _csv_bytes(
                ["id", "asset_name", "purchase_date", "cost", "accumulated_depreciation", "depreciation_rate", "status"],
                FixedAsset.objects.filter(tenant=tenant)
                .order_by("asset_name")
                .values_list("id", "asset_name", "purchase_date", "cost", "accumulated_depreciation", "depreciation_rate", "status"),
            ),
        )
        export.writestr(
            "payroll_summaries.csv",
            _csv_bytes(
                [
                    "id",
                    "period_start",
                    "period_end",
                    "gross_pay",
                    "paye",
                    "employee_ni",
                    "employer_ni",
                    "pension",
                    "cis_deductions",
                    "journal_posted",
                    "status",
                ],
                PayrollSummary.objects.filter(tenant=tenant)
                .order_by("period_start", "period_end")
                .values_list(
                    "id",
                    "period_start",
                    "period_end",
                    "gross_pay",
                    "paye",
                    "employee_ni",
                    "employer_ni",
                    "pension",
                    "cis_deductions",
                    "journal_posted",
                    "status",
                ),
            ),
        )
        export.writestr(
            "corporation_tax_estimates.csv",
            _csv_bytes(
                [
                    "id",
                    "period_start",
                    "period_end",
                    "accounting_profit",
                    "disallowable_expenses",
                    "capital_allowances",
                    "taxable_profit",
                    "tax_rate",
                    "estimated_tax",
                    "status",
                ],
                CorporationTaxEstimate.objects.filter(tenant=tenant)
                .order_by("period_start", "period_end")
                .values_list(
                    "id",
                    "period_start",
                    "period_end",
                    "accounting_profit",
                    "disallowable_expenses",
                    "capital_allowances",
                    "taxable_profit",
                    "tax_rate",
                    "estimated_tax",
                    "status",
                ),
            ),
        )
        export.writestr(
            "statutory_accounts_drafts.csv",
            _csv_bytes(
                [
                    "id",
                    "period_start",
                    "period_end",
                    "accounts_type",
                    "directors_report_ready",
                    "balance_sheet_ready",
                    "notes_ready",
                    "ixbrl_ready",
                    "client_approved",
                    "status",
                    "review_note",
                ],
                StatutoryAccountsDraft.objects.filter(tenant=tenant)
                .order_by("period_start", "period_end", "accounts_type")
                .values_list(
                    "id",
                    "period_start",
                    "period_end",
                    "accounts_type",
                    "directors_report_ready",
                    "balance_sheet_ready",
                    "notes_ready",
                    "ixbrl_ready",
                    "client_approved",
                    "status",
                    "review_note",
                ),
            ),
        )
        export.writestr(
            "management_pack_sections.csv",
            _csv_bytes(
                ["id", "section_name", "period_end", "commentary", "owner", "status"],
                ManagementPackSection.objects.filter(tenant=tenant)
                .order_by("period_end", "section_name")
                .values_list("id", "section_name", "period_end", "commentary", "owner", "status"),
            ),
        )
        export.writestr(
            "document_intelligence_rules.csv",
            _csv_bytes(
                ["id", "name", "keyword", "document_category", "suggested_account_code", "confidence", "is_active"],
                DocumentIntelligenceRule.objects.filter(tenant=tenant)
                .order_by("name")
                .values_list("id", "name", "keyword", "document_category", "suggested_account_code", "confidence", "is_active"),
            ),
        )
        export.writestr(
            "client_approval_records.csv",
            _csv_bytes(
                [
                    "id",
                    "approval_type",
                    "reference",
                    "title",
                    "summary",
                    "status",
                    "requested_by",
                    "requested_at",
                    "decided_by",
                    "decided_at",
                    "decision_note",
                ],
                ClientApprovalRecord.objects.filter(tenant=tenant)
                .order_by("requested_at", "id")
                .values_list(
                    "id",
                    "approval_type",
                    "reference",
                    "title",
                    "summary",
                    "status",
                    "requested_by",
                    "requested_at",
                    "decided_by",
                    "decided_at",
                    "decision_note",
                ),
            ),
        )
        export.writestr(
            "accounting_tasks.csv",
            _csv_bytes(
                ["id", "phase", "title", "owner", "due_date", "priority", "status", "detail", "completed_at"],
                AccountingTask.objects.filter(tenant=tenant)
                .order_by("phase", "title")
                .values_list("id", "phase", "title", "owner", "due_date", "priority", "status", "detail", "completed_at"),
            ),
        )
        export.writestr(
            "notification_events.csv",
            _csv_bytes(
                ["id", "channel", "recipient", "subject", "status", "created_at", "sent_at"],
                NotificationEvent.objects.filter(tenant=tenant)
                .order_by("created_at", "id")
                .values_list("id", "channel", "recipient", "subject", "status", "created_at", "sent_at"),
            ),
        )
    return buffer.getvalue()
