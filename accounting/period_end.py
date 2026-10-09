"""Local, auditable period-end postings for routine accounting schedules."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import (
    AccountingPeriodLock,
    AuditEvent,
    BankReconciliation,
    BankTransaction,
    EvidenceDocument,
    FixedAsset,
    Journal,
    JournalLine,
    MonthEndClose,
    NominalAccount,
    PayrollSummary,
)


PENNY = Decimal("0.01")


def _account(tenant, code, name, category):
    account, _ = NominalAccount.objects.get_or_create(
        tenant=tenant,
        code=code,
        defaults={"name": name, "category": category, "canonical_taxonomy": name},
    )
    return account


def _money(value):
    return Decimal(value).quantize(PENNY, rounding=ROUND_HALF_UP)


def _period_is_locked(tenant, period_start, period_end):
    return AccountingPeriodLock.objects.filter(
        tenant=tenant,
        period_start=period_start,
        period_end=period_end,
        status=AccountingPeriodLock.STATUS_LOCKED,
    ).exists()


def period_end_control_status(tenant, period_start: date, period_end: date):
    """Return factual close gates without changing accounting records."""
    close = MonthEndClose.objects.filter(
        tenant=tenant, period_start=period_start, period_end=period_end
    ).first()
    reconciled_ids = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    unreconciled_banks = BankTransaction.objects.filter(
        tenant=tenant, date__range=(period_start, period_end)
    ).exclude(id__in=reconciled_ids).count()
    unreviewed_evidence = EvidenceDocument.objects.filter(
        tenant=tenant, uploaded_at__date__range=(period_start, period_end)
    ).exclude(review_status="ReadyForPosting").count()
    payroll_posted = PayrollSummary.objects.filter(
        tenant=tenant,
        period_start__lte=period_end,
        period_end__gte=period_start,
        journal_posted=True,
    ).exists()
    return {
        "close": close,
        "locked": _period_is_locked(tenant, period_start, period_end),
        "unreconciled_banks": unreconciled_banks,
        "unreviewed_evidence": unreviewed_evidence,
        "payroll_posted": payroll_posted,
        "payroll_not_applicable": bool(close and close.payroll_not_applicable),
        "payroll_ready": payroll_posted or bool(close and close.payroll_not_applicable),
        "schedules_posted": bool(close and close.accruals_posted and close.prepayments_posted and close.depreciation_posted),
        "review_signed_off": bool(close and close.review_signed_off),
    }


def _post_pair(tenant, source_type, source_id, period_end, description, debit_account, credit_account, amount, username):
    existing = Journal.objects.filter(
        tenant=tenant, source_type=source_type, source_id=source_id
    ).first()
    if existing:
        return existing, False
    journal = Journal.objects.create(
        tenant=tenant,
        date=period_end,
        description=description,
        source_type=source_type,
        source_id=source_id,
        created_by=username,
    )
    JournalLine.objects.create(tenant=tenant, journal=journal, account=debit_account, debit=amount)
    JournalLine.objects.create(tenant=tenant, journal=journal, account=credit_account, credit=amount)
    return journal, True


@transaction.atomic
def post_period_end_schedules(
    tenant,
    period_start: date,
    period_end: date,
    username: str,
    *,
    accrual_amount=Decimal("0.00"),
    prepayment_amount=Decimal("0.00"),
):
    """Post local routine schedules once, without changing locked accounting periods."""
    if period_start > period_end:
        raise ValueError("The period start must not be after the period end.")
    if _period_is_locked(tenant, period_start, period_end):
        raise ValueError("This accounting period is locked and cannot receive routine postings.")

    accrual_amount = _money(accrual_amount)
    prepayment_amount = _money(prepayment_amount)
    if accrual_amount < 0 or prepayment_amount < 0:
        raise ValueError("Accrual and prepayment amounts must not be negative.")

    expense = _account(tenant, "6100", "Operating expenses", "Expense")
    accrued_liability = _account(tenant, "2100", "Accrued expenses", "Liability")
    prepaid_asset = _account(tenant, "1500", "Prepayments", "Asset")
    depreciation_expense = _account(tenant, "6900", "Depreciation", "Expense")
    accumulated_depreciation = _account(tenant, "1600", "Accumulated depreciation", "Asset")
    created = []

    if accrual_amount:
        _, was_created = _post_pair(
            tenant, "PeriodEndAccrual", f"{period_end}:accrual", period_end,
            f"Accrual for period ending {period_end}", expense, accrued_liability,
            accrual_amount, username,
        )
        if was_created:
            created.append("accrual")
    if prepayment_amount:
        _, was_created = _post_pair(
            tenant, "PeriodEndPrepayment", f"{period_end}:prepayment", period_end,
            f"Prepayment release for period ending {period_end}", expense, prepaid_asset,
            prepayment_amount, username,
        )
        if was_created:
            created.append("prepayment")

    depreciation_total = Decimal("0.00")
    for asset in FixedAsset.objects.select_for_update().filter(tenant=tenant, status="Active"):
        remaining = max(Decimal("0.00"), asset.cost - asset.accumulated_depreciation)
        monthly_charge = _money(asset.cost * asset.depreciation_rate / Decimal("1200"))
        charge = min(remaining, monthly_charge)
        if not charge:
            continue
        _, was_created = _post_pair(
            tenant, "PeriodEndDepreciation", f"{period_end}:asset:{asset.id}", period_end,
            f"Depreciation: {asset.asset_name} for period ending {period_end}",
            depreciation_expense, accumulated_depreciation, charge, username,
        )
        if was_created:
            asset.accumulated_depreciation += charge
            asset.save(update_fields=["accumulated_depreciation"])
            depreciation_total += charge
            created.append(f"depreciation:{asset.id}")

    close, _ = MonthEndClose.objects.get_or_create(
        tenant=tenant, period_start=period_start, period_end=period_end
    )
    close.accruals_posted = bool(accrual_amount) or close.accruals_posted
    close.prepayments_posted = bool(prepayment_amount) or close.prepayments_posted
    close.depreciation_posted = bool(depreciation_total) or close.depreciation_posted
    close.save(update_fields=["accruals_posted", "prepayments_posted", "depreciation_posted"])
    AuditEvent.objects.create(
        tenant=tenant,
        event_type="PeriodEndSchedules",
        username=username,
        description=f"Routine schedules processed for period ending {period_end}.",
        details={"period_start": str(period_start), "period_end": str(period_end), "created": created, "depreciation": str(depreciation_total)},
    )
    return {"created": created, "depreciation": depreciation_total, "month_end_close": close}


@transaction.atomic
def close_period_end(
    tenant, period_start: date, period_end: date, username: str, *, payroll_not_applicable=False
):
    """Close one period only after all local accounting control gates pass."""
    controls = period_end_control_status(tenant, period_start, period_end)
    if controls["locked"]:
        raise ValueError("This accounting period is already locked.")
    close = controls["close"]
    if not close or not controls["schedules_posted"]:
        raise ValueError("Post accruals, prepayments and depreciation before closing this period.")
    if controls["unreconciled_banks"]:
        raise ValueError("Reconcile all bank transactions in this period before closing it.")
    if controls["unreviewed_evidence"]:
        raise ValueError("Review all evidence uploaded in this period before closing it.")
    if not controls["payroll_ready"] and not payroll_not_applicable:
        raise ValueError("Post the payroll journal for this period before closing it.")

    close.bank_reconciled = True
    close.payroll_posted = controls["payroll_posted"]
    close.payroll_not_applicable = bool(payroll_not_applicable or controls["payroll_not_applicable"])
    close.review_signed_off = True
    close.status = MonthEndClose.STATUS_CLOSED
    close.closed_by = username
    close.closed_at = timezone.now()
    close.save(update_fields=["bank_reconciled", "payroll_posted", "payroll_not_applicable", "review_signed_off", "status", "closed_by", "closed_at"])
    AccountingPeriodLock.objects.create(
        tenant=tenant, period_start=period_start, period_end=period_end,
        locked_by=username, reason="Month-end close completed through LedgerHouse control gates.",
    )
    AuditEvent.objects.create(
        tenant=tenant, event_type="PeriodEndClosed", username=username,
        description=f"Period {period_start} to {period_end} closed and locked.",
        details={
            "period_start": str(period_start),
            "period_end": str(period_end),
            "payroll_not_applicable": close.payroll_not_applicable,
        },
    )
    return close
