from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import render

from .models import (
    BankReconciliation,
    BankTransaction,
    EvidenceDocument,
    Journal,
    JournalLine,
    Tenant,
    VatReturn,
)


def _money(value):
    value = value or Decimal("0")
    return f"GBP {value:,.2f}"


@login_required(login_url="/login/")
def dashboard(request):
    tenants = list(
        Tenant.objects.annotate(
            journals_count=Count("journal", distinct=True),
            bank_count=Count("banktransaction", distinct=True),
            evidence_count=Count("evidencedocument", distinct=True),
            latest_activity=Max("journal__created_at"),
        ).order_by("name")
    )

    revenue = JournalLine.objects.filter(account__category="Revenue").aggregate(
        total=Sum("credit")
    )["total"]
    expenses = JournalLine.objects.filter(
        Q(account__category="Expense") | Q(account__category="Cost of Sales")
    ).aggregate(total=Sum("debit"))["total"]
    vat_due = VatReturn.objects.aggregate(total=Sum("net_vat_payable"))["total"]

    reconciled_ids = BankReconciliation.objects.values("bank_transaction_id")
    unreconciled_count = BankTransaction.objects.exclude(id__in=reconciled_ids).count()

    vat_returns = VatReturn.objects.select_related("tenant").order_by("-end_date")[:5]
    recent_journals = Journal.objects.select_related("tenant").order_by("-created_at")[:6]

    context = {
        "tenants": tenants,
        "tenant_count": len(tenants),
        "journal_count": Journal.objects.count(),
        "bank_count": BankTransaction.objects.count(),
        "evidence_count": EvidenceDocument.objects.count(),
        "unreconciled_count": unreconciled_count,
        "revenue": _money(revenue),
        "expenses": _money(expenses),
        "margin": _money((revenue or Decimal("0")) - (expenses or Decimal("0"))),
        "vat_due": _money(vat_due),
        "vat_returns": vat_returns,
        "recent_journals": recent_journals,
    }
    return render(request, "accounting/dashboard.html", context)
