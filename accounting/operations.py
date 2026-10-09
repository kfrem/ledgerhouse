from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
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
    SupplierPaymentRunBill,
    Tenant,
)


PHASE_LABELS = [
    ("Phase 1", "Core operating ledgers"),
    ("Phase 2", "Month-end accounts department"),
    ("Phase 3", "Payroll, CIS and tax workflows"),
    ("Phase 4", "Statutory accounts preparation"),
    ("Phase 5", "Client/practice collaboration"),
    ("Phase 6", "Permissions and SaaS controls"),
    ("Phase 7", "Reports and packs"),
    ("Phase 8", "Local filing readiness"),
]


def _money_total(queryset, field):
    return sum((getattr(item, field) for item in queryset), Decimal("0.00"))


def accounts_department_snapshot(tenant):
    sales = list(SalesInvoice.objects.filter(tenant=tenant))
    quotes = SalesQuote.objects.filter(tenant=tenant)
    purchases = list(PurchaseBill.objects.filter(tenant=tenant))
    purchase_orders = PurchaseOrder.objects.filter(tenant=tenant)
    credit_actions = CreditControlAction.objects.filter(tenant=tenant)
    payment_runs = SupplierPaymentRun.objects.filter(tenant=tenant)
    bank_rules = BankRule.objects.filter(tenant=tenant)
    closes = MonthEndClose.objects.filter(tenant=tenant)
    period_locks = AccountingPeriodLock.objects.filter(tenant=tenant)
    assets = FixedAsset.objects.filter(tenant=tenant)
    payroll = PayrollSummary.objects.filter(tenant=tenant)
    tax_estimates = CorporationTaxEstimate.objects.filter(tenant=tenant)
    statutory = StatutoryAccountsDraft.objects.filter(tenant=tenant)
    pack_sections = ManagementPackSection.objects.filter(tenant=tenant)
    document_rules = DocumentIntelligenceRule.objects.filter(tenant=tenant)
    approvals = ClientApprovalRecord.objects.filter(tenant=tenant)
    tasks = AccountingTask.objects.filter(tenant=tenant)
    notifications = NotificationEvent.objects.filter(tenant=tenant)

    open_sales = [invoice for invoice in sales if invoice.status != SalesInvoice.STATUS_PAID]
    open_purchases = [bill for bill in purchases if bill.status != PurchaseBill.STATUS_PAID]
    complete_closes = [close for close in closes if close.checklist_complete]
    complete_statutory = [draft for draft in statutory if draft.locally_complete]

    phases = [
        {
            "phase": "Phase 1",
            "label": "Core operating ledgers",
            "passed": bool(quotes.exists() and sales and purchase_orders.exists() and purchases and credit_actions.exists() and payment_runs.exists()),
            "detail": f"{quotes.count()} quote(s), {len(sales)} sales invoice(s), {purchase_orders.count()} purchase order(s), {len(purchases)} purchase bill(s), {credit_actions.count()} credit action(s), {payment_runs.count()} payment run(s).",
        },
        {
            "phase": "Phase 2",
            "label": "Month-end accounts department",
            "passed": bool(complete_closes and assets.exists() and period_locks.exists()),
            "detail": f"{closes.count()} close file(s), {len(complete_closes)} complete, {assets.count()} fixed asset(s), {period_locks.count()} locked period(s).",
        },
        {
            "phase": "Phase 3",
            "label": "Payroll, CIS and tax workflows",
            "passed": bool(payroll.exists() and tax_estimates.exists() and bank_rules.exists()),
            "detail": f"{payroll.count()} payroll summary record(s), {tax_estimates.count()} corporation tax estimate(s), {bank_rules.count()} bank rule(s).",
        },
        {
            "phase": "Phase 4",
            "label": "Statutory accounts preparation",
            "passed": bool(statutory.exists() and complete_statutory),
            "detail": f"{statutory.count()} draft(s), {len(complete_statutory)} locally complete before iXBRL/XML Gateway filing.",
        },
        {
            "phase": "Phase 5",
            "label": "Client/practice collaboration",
            "passed": bool(tasks.exists() and notifications.exists() and approvals.exists()),
            "detail": f"{tasks.count()} task(s), {notifications.count()} notification event(s), {approvals.count()} approval item(s).",
        },
        {
            "phase": "Phase 6",
            "label": "Permissions and SaaS controls",
            "passed": True,
            "detail": "Practice screens remain staff-only and client reports remain tenant-scoped.",
        },
        {
            "phase": "Phase 7",
            "label": "Reports and packs",
            "passed": bool(pack_sections.exists()),
            "detail": f"Management report CSV, PDF, pack, data export and {pack_sections.count()} commentary section(s) are generated from local records.",
        },
        {
            "phase": "Phase 8",
            "label": "Local filing readiness",
            "passed": bool(statutory.exists() and document_rules.exists()),
            "detail": f"Local readiness and {document_rules.count()} document intelligence rule(s) are tracked; live Companies House/HMRC filing remains externally gated.",
        },
    ]

    return {
        "tenant": tenant,
        "sales_count": len(sales),
        "quote_count": quotes.count(),
        "purchase_count": len(purchases),
        "purchase_order_count": purchase_orders.count(),
        "bank_rule_count": bank_rules.count(),
        "period_lock_count": period_locks.count(),
        "pack_section_count": pack_sections.count(),
        "document_rule_count": document_rules.count(),
        "approval_count": approvals.count(),
        "pending_approval_count": approvals.filter(status=ClientApprovalRecord.STATUS_PENDING).count(),
        "open_sales_count": len(open_sales),
        "open_purchase_count": len(open_purchases),
        "sales_balance": _money_total(open_sales, "balance_due"),
        "purchase_balance": _money_total(open_purchases, "balance_due"),
        "fixed_asset_nbv": sum((asset.net_book_value for asset in assets), Decimal("0.00")),
        "task_count": tasks.count(),
        "open_task_count": tasks.exclude(status=AccountingTask.STATUS_DONE).count(),
        "notification_count": notifications.count(),
        "phases": phases,
        "passed_count": sum(1 for phase in phases if phase["passed"]),
        "total_count": len(phases),
    }


@transaction.atomic
def build_local_accounts_department_suite(tenant, username="practice"):
    today = timezone.localdate()
    year_start = date(today.year, 1, 1)
    quarter_start = today - timedelta(days=90)
    period_end = today

    sales_invoice, _ = SalesInvoice.objects.update_or_create(
        tenant=tenant,
        invoice_number="LH-SI-0001",
        defaults={
            "customer_name": "Example Customer Ltd",
            "issue_date": today - timedelta(days=35),
            "due_date": today - timedelta(days=5),
            "net_amount": Decimal("2500.00"),
            "vat_amount": Decimal("500.00"),
            "gross_amount": Decimal("3000.00"),
            "paid_amount": Decimal("1200.00"),
            "status": SalesInvoice.STATUS_OVERDUE,
            "notes": "Local demo sales ledger invoice for credit control testing.",
        },
    )
    SalesInvoice.objects.update_or_create(
        tenant=tenant,
        invoice_number="LH-SI-0002",
        defaults={
            "customer_name": "Prompt Payer Ltd",
            "issue_date": today - timedelta(days=12),
            "due_date": today + timedelta(days=18),
            "net_amount": Decimal("1800.00"),
            "vat_amount": Decimal("360.00"),
            "gross_amount": Decimal("2160.00"),
            "paid_amount": Decimal("2160.00"),
            "status": SalesInvoice.STATUS_PAID,
            "notes": "Paid invoice for debtor workflow comparison.",
        },
    )
    SalesQuote.objects.update_or_create(
        tenant=tenant,
        quote_number="LH-Q-0001",
        defaults={
            "customer_name": "Growth Client Ltd",
            "issue_date": today - timedelta(days=8),
            "expiry_date": today + timedelta(days=22),
            "net_amount": Decimal("4200.00"),
            "vat_amount": Decimal("840.00"),
            "gross_amount": Decimal("5040.00"),
            "status": SalesQuote.STATUS_ACCEPTED,
            "converted_invoice": sales_invoice,
            "notes": "Accepted local quote linked to the sales workflow.",
        },
    )
    purchase_bill, _ = PurchaseBill.objects.update_or_create(
        tenant=tenant,
        bill_number="LH-PB-0001",
        defaults={
            "supplier_name": "Office Supplier Ltd",
            "bill_date": today - timedelta(days=20),
            "due_date": today + timedelta(days=10),
            "net_amount": Decimal("900.00"),
            "vat_amount": Decimal("180.00"),
            "gross_amount": Decimal("1080.00"),
            "paid_amount": Decimal("0.00"),
            "status": PurchaseBill.STATUS_APPROVED,
            "approval_note": "Approved locally for payment-run testing.",
        },
    )
    PurchaseBill.objects.update_or_create(
        tenant=tenant,
        bill_number="LH-PB-0002",
        defaults={
            "supplier_name": "Software Vendor Ltd",
            "bill_date": today - timedelta(days=10),
            "due_date": today + timedelta(days=20),
            "net_amount": Decimal("300.00"),
            "vat_amount": Decimal("60.00"),
            "gross_amount": Decimal("360.00"),
            "paid_amount": Decimal("0.00"),
            "status": PurchaseBill.STATUS_AWAITING_APPROVAL,
            "approval_note": "Awaiting manager approval.",
        },
    )
    PurchaseOrder.objects.update_or_create(
        tenant=tenant,
        order_number="LH-PO-0001",
        defaults={
            "supplier_name": "Office Supplier Ltd",
            "order_date": today - timedelta(days=25),
            "expected_date": today - timedelta(days=15),
            "net_amount": Decimal("900.00"),
            "vat_amount": Decimal("180.00"),
            "gross_amount": Decimal("1080.00"),
            "status": PurchaseOrder.STATUS_BILLED,
            "approved_by": username,
            "linked_bill": purchase_bill,
            "notes": "Approved local purchase order matched to supplier bill.",
        },
    )
    CreditControlAction.objects.update_or_create(
        tenant=tenant,
        sales_invoice=sales_invoice,
        action_type=CreditControlAction.ACTION_EMAIL,
        defaults={
            "action_date": today,
            "owner": username,
            "note": "Reminder queued for overdue local demo invoice.",
            "next_action_date": today + timedelta(days=7),
            "resolved": False,
        },
    )
    payment_run, _ = SupplierPaymentRun.objects.update_or_create(
        tenant=tenant,
        run_reference="LH-PAYRUN-0001",
        defaults={
            "scheduled_date": today + timedelta(days=3),
            "total_amount": purchase_bill.balance_due,
            "status": SupplierPaymentRun.STATUS_APPROVED,
            "approved_by": username,
        },
    )
    SupplierPaymentRunBill.objects.update_or_create(
        tenant=tenant,
        payment_run=payment_run,
        bill=purchase_bill,
    )
    BankRule.objects.update_or_create(
        tenant=tenant,
        name="Software subscriptions",
        defaults={
            "match_text": "SOFTWARE VENDOR",
            "account_code": "6200",
            "action": BankRule.ACTION_SUGGEST_JOURNAL,
            "confidence": Decimal("91.00"),
            "is_active": True,
        },
    )
    MonthEndClose.objects.update_or_create(
        tenant=tenant,
        period_start=quarter_start,
        period_end=period_end,
        defaults={
            "bank_reconciled": True,
            "accruals_posted": True,
            "prepayments_posted": True,
            "depreciation_posted": True,
            "payroll_posted": True,
            "review_signed_off": True,
            "status": MonthEndClose.STATUS_CLOSED,
            "closed_by": username,
            "closed_at": timezone.now(),
        },
    )
    AccountingPeriodLock.objects.update_or_create(
        tenant=tenant,
        period_start=quarter_start,
        period_end=period_end,
        defaults={
            "status": AccountingPeriodLock.STATUS_LOCKED,
            "locked_by": username,
            "reason": "Local controls lock the closed period until partner-approved reopening.",
        },
    )
    FixedAsset.objects.update_or_create(
        tenant=tenant,
        asset_name="Laptop fleet",
        defaults={
            "purchase_date": today - timedelta(days=180),
            "cost": Decimal("4800.00"),
            "accumulated_depreciation": Decimal("1200.00"),
            "depreciation_rate": Decimal("25.00"),
            "status": "Active",
        },
    )
    PayrollSummary.objects.update_or_create(
        tenant=tenant,
        period_start=today.replace(day=1),
        period_end=period_end,
        defaults={
            "gross_pay": Decimal("8500.00"),
            "paye": Decimal("1250.00"),
            "employee_ni": Decimal("620.00"),
            "employer_ni": Decimal("780.00"),
            "pension": Decimal("420.00"),
            "cis_deductions": Decimal("0.00"),
            "journal_posted": True,
            "status": "Posted",
        },
    )
    taxable_profit = Decimal("15330.00") + Decimal("250.00") - Decimal("1000.00")
    CorporationTaxEstimate.objects.update_or_create(
        tenant=tenant,
        period_start=year_start,
        period_end=period_end,
        defaults={
            "accounting_profit": Decimal("15330.00"),
            "disallowable_expenses": Decimal("250.00"),
            "capital_allowances": Decimal("1000.00"),
            "taxable_profit": taxable_profit,
            "tax_rate": Decimal("25.00"),
            "estimated_tax": (taxable_profit * Decimal("0.25")).quantize(Decimal("0.01")),
            "status": "Estimated",
        },
    )
    StatutoryAccountsDraft.objects.update_or_create(
        tenant=tenant,
        period_start=year_start,
        period_end=period_end,
        accounts_type="MicroEntity",
        defaults={
            "directors_report_ready": True,
            "balance_sheet_ready": True,
            "notes_ready": True,
            "ixbrl_ready": False,
            "client_approved": True,
            "status": StatutoryAccountsDraft.STATUS_CLIENT_APPROVAL,
            "review_note": "Local statutory draft is prepared; iXBRL/XML Gateway filing remains disabled.",
        },
    )
    ManagementPackSection.objects.update_or_create(
        tenant=tenant,
        section_name="Director commentary",
        period_end=period_end,
        defaults={
            "commentary": "Revenue, debtor control, supplier payments, payroll and tax estimates are ready for management review from local records.",
            "owner": username,
            "status": ManagementPackSection.STATUS_REVIEWED,
        },
    )
    ClientApprovalRecord.objects.update_or_create(
        tenant=tenant,
        approval_type=ClientApprovalRecord.TYPE_MANAGEMENT_PACK,
        reference=f"PACK-{period_end.isoformat()}",
        defaults={
            "title": f"Management pack to {period_end}",
            "summary": "Review and approve the local management pack before it is released as final.",
            "status": ClientApprovalRecord.STATUS_PENDING,
            "requested_by": username,
            "decided_by": "",
            "decided_at": None,
            "decision_note": "",
        },
    )
    ClientApprovalRecord.objects.update_or_create(
        tenant=tenant,
        approval_type=ClientApprovalRecord.TYPE_STATUTORY_ACCOUNTS,
        reference=f"STAT-{period_end.isoformat()}",
        defaults={
            "title": f"Statutory accounts draft to {period_end}",
            "summary": "Review the local accounts draft. Live Companies House filing remains externally gated.",
            "status": ClientApprovalRecord.STATUS_PENDING,
            "requested_by": username,
            "decided_by": "",
            "decided_at": None,
            "decision_note": "",
        },
    )
    DocumentIntelligenceRule.objects.update_or_create(
        tenant=tenant,
        name="Supplier invoice detector",
        defaults={
            "keyword": "invoice",
            "document_category": "PurchaseInvoice",
            "suggested_account_code": "6000",
            "confidence": Decimal("88.00"),
            "is_active": True,
        },
    )
    task_specs = [
        ("Phase 1", "Review overdue customer invoice", "High"),
        ("Phase 2", "Confirm month-end close file", "Normal"),
        ("Phase 3", "Review payroll and corporation tax estimate", "Normal"),
        ("Phase 4", "Partner review statutory accounts draft", "High"),
        ("Phase 5", "Send client query summary", "Normal"),
        ("Phase 6", "Confirm client access permissions", "Normal"),
        ("Phase 7", "Release management pack", "Normal"),
        ("Phase 8", "Hold Companies House filing until iXBRL is ready", "High"),
    ]
    for phase, title, priority in task_specs:
        AccountingTask.objects.update_or_create(
            tenant=tenant,
            phase=phase,
            title=title,
            defaults={
                "owner": username,
                "due_date": today + timedelta(days=7),
                "priority": priority,
                "status": AccountingTask.STATUS_IN_PROGRESS if phase in {"Phase 4", "Phase 8"} else AccountingTask.STATUS_DONE,
                "detail": "Created by the local accounts department build pass.",
                "completed_at": timezone.now() if phase not in {"Phase 4", "Phase 8"} else None,
            },
        )
    NotificationEvent.objects.update_or_create(
        tenant=tenant,
        channel=NotificationEvent.CHANNEL_EMAIL_MOCK,
        recipient="client@example.com",
        subject="LedgerHouse local accounts department update",
        defaults={
            "body": "Your local accounts department workflow has been prepared for review.",
            "status": "Queued",
        },
    )
    AuditEvent.objects.create(
        tenant=tenant,
        event_type="AccountsDepartmentSuite",
        username=username,
        description="Local accounts department suite created or refreshed.",
        details={"phases": [phase for phase, _label in PHASE_LABELS]},
    )
    return accounts_department_snapshot(tenant)
