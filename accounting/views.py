from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import redirect, render

from .intake import process_uploaded_file
from .mtd import (
    build_hmrc_authorisation_url,
    exchange_hmrc_authorisation_code,
    hmrc_sandbox_status,
    unpack_hmrc_state,
)
from .models import (
    BankReconciliation,
    BankTransaction,
    EvidenceDocument,
    Journal,
    JournalLine,
    Tenant,
    VatReturn,
)
from .reports import management_report_csv, management_report_pdf


def _money(value):
    value = value or Decimal("0")
    return f"GBP {value:,.2f}"


def _selected_tenant(request):
    tenants = list(Tenant.objects.order_by("name"))
    selected_tenant = None
    requested_tenant = request.GET.get("company") or request.POST.get("company")

    if requested_tenant:
        selected_tenant = next(
            (tenant for tenant in tenants if str(tenant.id) == requested_tenant),
            None,
        )
    if selected_tenant is None and tenants:
        selected_tenant = tenants[0]
    return tenants, selected_tenant


@login_required(login_url="/login/")
def client_portal(request):
    tenants, selected_tenant = _selected_tenant(request)

    if request.method == "POST":
        if not selected_tenant:
            messages.error(request, "No company is available for uploads.")
            return redirect("client_portal")
        uploaded_files = request.FILES.getlist("documents")
        if not uploaded_files:
            messages.error(request, "Choose at least one file to upload.")
        else:
            for uploaded_file in uploaded_files:
                try:
                    result = process_uploaded_file(
                        selected_tenant,
                        uploaded_file,
                        request.user.get_username() or "client",
                    )
                    messages.success(request, f"{uploaded_file.name}: {result.message}")
                except Exception as exc:
                    messages.error(request, f"{uploaded_file.name}: {exc}")
        return redirect(f"{request.path}?company={selected_tenant.id}#upload")

    revenue = Decimal("0")
    expenses = Decimal("0")
    vat_due = Decimal("0")
    bank_count = 0
    unreconciled_count = 0
    evidence_count = 0
    journal_count = 0
    latest_documents = []
    latest_journals = []
    vat_returns = []

    if selected_tenant:
        revenue = JournalLine.objects.filter(
            tenant=selected_tenant,
            account__category="Revenue",
        ).aggregate(total=Sum("credit"))["total"] or Decimal("0")
        expenses = JournalLine.objects.filter(
            Q(account__category="Expense") | Q(account__category="Cost of Sales"),
            tenant=selected_tenant,
        ).aggregate(total=Sum("debit"))["total"] or Decimal("0")
        vat_due = VatReturn.objects.filter(tenant=selected_tenant).aggregate(
            total=Sum("net_vat_payable")
        )["total"] or Decimal("0")

        reconciled_ids = BankReconciliation.objects.filter(
            tenant=selected_tenant
        ).values("bank_transaction_id")
        bank_count = BankTransaction.objects.filter(tenant=selected_tenant).count()
        unreconciled_count = (
            BankTransaction.objects.filter(tenant=selected_tenant)
            .exclude(id__in=reconciled_ids)
            .count()
        )
        evidence_count = EvidenceDocument.objects.filter(tenant=selected_tenant).count()
        journal_count = Journal.objects.filter(tenant=selected_tenant).count()
        latest_documents = EvidenceDocument.objects.filter(
            tenant=selected_tenant
        ).order_by("-uploaded_at")[:4]
        latest_journals = Journal.objects.filter(
            tenant=selected_tenant
        ).order_by("-created_at")[:5]
        vat_returns = VatReturn.objects.filter(
            tenant=selected_tenant
        ).order_by("-end_date")[:3]

    context = {
        "tenants": tenants,
        "selected_tenant": selected_tenant,
        "revenue": _money(revenue),
        "expenses": _money(expenses),
        "profit": _money(revenue - expenses),
        "vat_due": _money(vat_due),
        "bank_count": bank_count,
        "unreconciled_count": unreconciled_count,
        "evidence_count": evidence_count,
        "journal_count": journal_count,
        "latest_documents": latest_documents,
        "latest_journals": latest_journals,
        "vat_returns": vat_returns,
    }
    return render(request, "accounting/client_portal.html", context)


@login_required(login_url="/login/")
def download_management_report(request, tenant_id, file_format):
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist as exc:
        raise Http404("Company not found") from exc

    if file_format == "csv":
        response = HttpResponse(management_report_csv(tenant), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-management-report.csv"'
        return response
    if file_format == "pdf":
        response = HttpResponse(management_report_pdf(tenant), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-management-report.pdf"'
        return response
    raise Http404("Report format not supported")


@login_required(login_url="/login/")
def practice_dashboard(request):
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
    upload_inbox = EvidenceDocument.objects.select_related("tenant").order_by("-uploaded_at")[:8]
    unmatched_bank_transactions = (
        BankTransaction.objects.exclude(id__in=reconciled_ids)
        .select_related("tenant", "imported_file")
        .order_by("-date", "-id")[:8]
    )
    review_journals = (
        Journal.objects.filter(status="RequiresReview")
        .select_related("tenant")
        .order_by("-created_at")[:8]
    )

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
        "upload_inbox": upload_inbox,
        "unmatched_bank_transactions": unmatched_bank_transactions,
        "review_journals": review_journals,
        "hmrc_status": hmrc_sandbox_status(),
    }
    return render(request, "accounting/dashboard.html", context)


@login_required(login_url="/login/")
def hmrc_sandbox_status_view(request):
    return render(
        request,
        "accounting/hmrc_status.html",
        {"hmrc_status": hmrc_sandbox_status()},
    )


@login_required(login_url="/login/")
def hmrc_authorise(request):
    try:
        authorisation_url = build_hmrc_authorisation_url(
            request.GET.get("next") or "/practice/"
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("hmrc_sandbox_status")
    return redirect(authorisation_url)


@login_required(login_url="/login/")
def hmrc_callback(request):
    error = request.GET.get("error")
    if error:
        messages.error(request, f"HMRC authorisation failed: {error}")
        return redirect("hmrc_sandbox_status")

    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not state:
        messages.error(request, "HMRC callback did not include the expected code and state.")
        return redirect("hmrc_sandbox_status")

    try:
        unpacked_state = unpack_hmrc_state(state)
        token_payload = exchange_hmrc_authorisation_code(code)
    except Exception as exc:
        messages.error(request, f"HMRC token exchange failed: {exc}")
        return redirect("hmrc_sandbox_status")

    request.session["hmrc_sandbox_token"] = {
        "access_token": token_payload.get("access_token"),
        "refresh_token": token_payload.get("refresh_token"),
        "scope": token_payload.get("scope"),
        "expires_in": token_payload.get("expires_in"),
    }
    messages.success(request, "HMRC VAT sandbox authorisation completed.")
    return redirect(unpacked_state.get("next") or "hmrc_sandbox_status")
