from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from .intake import process_uploaded_file
from .mtd import (
    HmrcApiError,
    build_hmrc_authorisation_url,
    exchange_hmrc_authorisation_code,
    hmrc_sandbox_status,
    retrieve_vat_obligations,
    retrieve_vat_return,
    serialize_vat_return_9_box,
    submit_vat_return_payload,
    to_hmrc_vat_return_payload,
    unpack_hmrc_state,
)
from .models import (
    AuditEvent,
    BankReconciliation,
    BankTransaction,
    ClientRequest,
    EvidenceDocument,
    HmrcVatConnection,
    Journal,
    JournalEvidenceLink,
    JournalLine,
    NominalAccount,
    Tenant,
    VatReturn,
    VatReview,
)
from .reports import management_report_context, management_report_csv, management_report_pdf


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


def _ensure_vat_review_for_obligation(tenant, obligation):
    prepared = serialize_vat_return_9_box(
        tenant,
        obligation["start"],
        obligation["end"],
    )
    prepared["periodKey"] = obligation["periodKey"]
    review, created = VatReview.objects.get_or_create(
        tenant=tenant,
        period_key=obligation["periodKey"],
        defaults={
            "start_date": date.fromisoformat(obligation["start"]),
            "end_date": date.fromisoformat(obligation["end"]),
            "due_date": date.fromisoformat(obligation["due"]) if obligation.get("due") else None,
            "prepared_payload": prepared,
        },
    )
    if not created:
        review.start_date = date.fromisoformat(obligation["start"])
        review.end_date = date.fromisoformat(obligation["end"])
        review.due_date = date.fromisoformat(obligation["due"]) if obligation.get("due") else None
        review.prepared_payload = prepared
        review.save(update_fields=["start_date", "end_date", "due_date", "prepared_payload", "updated_at"])
    return review, prepared


def _ensure_default_nominals(tenant):
    accounts = [
        ("1200", "Bank", "Asset", "Cash"),
        ("2100", "Trade creditors", "Liability", "Payables"),
        ("2200", "VAT control", "Liability", "VAT"),
        ("4000", "Sales", "Revenue", "Revenue"),
        ("5000", "Cost of sales", "Cost of Sales", "CostOfSales"),
        ("6000", "Office costs", "Expense", "Expense"),
    ]
    for code, name, category, taxonomy in accounts:
        NominalAccount.objects.get_or_create(
            tenant=tenant,
            code=code,
            defaults={
                "name": name,
                "category": category,
                "canonical_taxonomy": taxonomy,
            },
        )


def _ensure_nominal(tenant, code, name, category, taxonomy):
    account, _ = NominalAccount.objects.get_or_create(
        tenant=tenant,
        code=code,
        defaults={
            "name": name,
            "category": category,
            "canonical_taxonomy": taxonomy,
        },
    )
    return account


def _record_audit_event(tenant, event_type, username, description, details=None):
    AuditEvent.objects.create(
        tenant=tenant,
        event_type=event_type,
        username=username or "practice",
        description=description,
        details=details or {},
    )


def _create_evidence_review_journal(document, username):
    source_id = f"EVIDENCE-{document.id}"
    existing = Journal.objects.filter(
        tenant=document.tenant,
        source_type="EvidenceReview",
        source_id=source_id,
    ).first()
    if existing:
        return existing, False

    suspense = _ensure_nominal(document.tenant, "9999", "Evidence review suspense", "Asset", "Suspense")

    with transaction.atomic():
        journal = Journal.objects.create(
            tenant=document.tenant,
            date=timezone.localdate(),
            description=f"Evidence review: {document.filename}",
            source_type="EvidenceReview",
            source_id=source_id,
            created_by=username or "practice",
            status="RequiresReview",
        )
        JournalLine.objects.create(
            tenant=document.tenant,
            journal=journal,
            account=suspense,
            debit=Decimal("0.00"),
            credit=Decimal("0.00"),
        )
        JournalLine.objects.create(
            tenant=document.tenant,
            journal=journal,
            account=suspense,
            debit=Decimal("0.00"),
            credit=Decimal("0.00"),
        )
        JournalEvidenceLink.objects.get_or_create(
            tenant=document.tenant,
            journal=journal,
            document=document,
            defaults={"linked_by": username or "practice"},
        )
        journal.status = "RequiresReview"
        journal.save(update_fields=["status"])

    return journal, True


def _post_unmatched_bank_transaction(bank_transaction, username):
    existing_link = BankReconciliation.objects.filter(bank_transaction=bank_transaction).first()
    existing_journal = Journal.objects.filter(
        tenant=bank_transaction.tenant,
        source_id=bank_transaction.fitid,
        source_type__in=["BankPayment", "BankReceipt"],
    ).first()
    if existing_link and existing_journal:
        return existing_journal, False

    bank = _ensure_nominal(bank_transaction.tenant, "1200", "Bank", "Asset", "Cash")
    expense = _ensure_nominal(bank_transaction.tenant, "6000", "Office costs", "Expense", "Expense")
    revenue = _ensure_nominal(bank_transaction.tenant, "4000", "Sales", "Revenue", "Revenue")
    amount = abs(bank_transaction.amount)
    source_type = "BankPayment" if bank_transaction.amount < 0 else "BankReceipt"

    with transaction.atomic():
        journal = existing_journal or Journal.objects.create(
            tenant=bank_transaction.tenant,
            date=bank_transaction.date,
            description=f"Auto-posted unmatched bank line: {bank_transaction.reference}",
            source_type=source_type,
            source_id=bank_transaction.fitid,
            created_by=username or "practice",
        )
        if not existing_journal:
            if bank_transaction.amount < 0:
                JournalLine.objects.create(
                    tenant=bank_transaction.tenant,
                    journal=journal,
                    account=expense,
                    debit=amount,
                    credit=Decimal("0.00"),
                )
                JournalLine.objects.create(
                    tenant=bank_transaction.tenant,
                    journal=journal,
                    account=bank,
                    debit=Decimal("0.00"),
                    credit=amount,
                )
            else:
                JournalLine.objects.create(
                    tenant=bank_transaction.tenant,
                    journal=journal,
                    account=bank,
                    debit=amount,
                    credit=Decimal("0.00"),
                )
                JournalLine.objects.create(
                    tenant=bank_transaction.tenant,
                    journal=journal,
                    account=revenue,
                    debit=Decimal("0.00"),
                    credit=amount,
                )
        BankReconciliation.objects.get_or_create(
            tenant=bank_transaction.tenant,
            bank_transaction=bank_transaction,
            defaults={
                "matched_journal": journal,
                "reconciled_by": username or "practice",
            },
        )

    return journal, existing_journal is None


@login_required(login_url="/login/")
def client_portal(request):
    tenants, selected_tenant = _selected_tenant(request)

    if request.method == "POST":
        if not selected_tenant:
            messages.error(request, "No company is available for this request.")
            return redirect("client_portal")
        action = request.POST.get("action") or "upload_documents"
        if action == "submit_client_request":
            subject = (request.POST.get("subject") or "").strip()
            category = (request.POST.get("category") or "General").strip()
            priority = (request.POST.get("priority") or "Normal").strip()
            message = (request.POST.get("message") or "").strip()
            if not subject or not message:
                messages.error(request, "Add a subject and message before sending your question.")
            else:
                ClientRequest.objects.create(
                    tenant=selected_tenant,
                    subject=subject[:160],
                    category=category[:50] or "General",
                    priority=priority[:20] or "Normal",
                    message=message,
                    submitted_by=request.user.get_username() or "client",
                )
                messages.success(request, "Your question has been sent to the accounts team.")
            return redirect(f"{request.path}?company={selected_tenant.id}#support")

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
    client_requests = []

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
        client_requests = ClientRequest.objects.filter(
            tenant=selected_tenant
        ).order_by("-submitted_at")[:4]

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
        "client_requests": client_requests,
    }
    return render(request, "accounting/client_portal.html", context)


@login_required(login_url="/login/")
def management_report_view(request, tenant_id):
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist as exc:
        raise Http404("Company not found") from exc

    report = management_report_context(tenant)
    latest_journals = Journal.objects.filter(tenant=tenant).order_by("-date", "-id")[:8]
    latest_documents = EvidenceDocument.objects.filter(tenant=tenant).order_by("-uploaded_at")[:8]
    vat_returns = VatReturn.objects.filter(tenant=tenant).order_by("-end_date")[:6]

    return render(
        request,
        "accounting/management_report.html",
        {
            "tenant": tenant,
            "report": report,
            "latest_journals": latest_journals,
            "latest_documents": latest_documents,
            "vat_returns": vat_returns,
            "revenue": _money(report["revenue"]),
            "expenses": _money(report["expenses"]),
            "profit": _money(report["profit"]),
            "vat_due": _money(report["vat_due"]),
        },
    )


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
def practice_clients(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_client":
            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, "Enter a client name before creating the record.")
            elif Tenant.objects.filter(name__iexact=name).exists():
                messages.error(request, "A client with this name already exists.")
            else:
                tenant = Tenant.objects.create(name=name[:100])
                _ensure_default_nominals(tenant)
                messages.success(request, f"{tenant.name} was created with a starter chart of accounts.")
                return redirect("practice_client_detail", tenant_id=tenant.id)
        return redirect("practice_clients")

    tenants = list(
        Tenant.objects.annotate(
            journals_count=Count("journal", distinct=True),
            bank_count=Count("banktransaction", distinct=True),
            evidence_count=Count("evidencedocument", distinct=True),
            open_questions=Count(
                "client_requests",
                filter=~Q(client_requests__status="Resolved"),
                distinct=True,
            ),
            latest_activity=Max("journal__created_at"),
        ).order_by("name")
    )

    return render(
        request,
        "accounting/practice_clients.html",
        {
            "tenants": tenants,
            "tenant_count": len(tenants),
        },
    )


@login_required(login_url="/login/")
def practice_client_detail(request, tenant_id):
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist as exc:
        raise Http404("Company not found") from exc

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_client_request":
            request_id = request.POST.get("request_id")
            status = request.POST.get("status")
            valid_statuses = {"Open", "InProgress", "Resolved"}
            client_request = ClientRequest.objects.filter(tenant=tenant, id=request_id).first()
            if not client_request:
                messages.error(request, "Client question was not found for this client.")
            elif status not in valid_statuses:
                messages.error(request, "Choose a valid client question status.")
            else:
                client_request.status = status
                if status == "Resolved":
                    client_request.resolved_at = timezone.now()
                    client_request.resolved_by = request.user.get_username() or "practice"
                else:
                    client_request.resolved_at = None
                    client_request.resolved_by = ""
                client_request.save(update_fields=["status", "resolved_at", "resolved_by", "updated_at"])
                messages.success(request, f"Client question marked {status}.")
        return redirect("practice_client_detail", tenant_id=tenant.id)

    report = management_report_context(tenant)
    reconciled_ids = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    unmatched_bank_transactions = (
        BankTransaction.objects.filter(tenant=tenant)
        .exclude(id__in=reconciled_ids)
        .select_related("imported_file")
        .order_by("-date", "-id")[:8]
    )
    review_journals = Journal.objects.filter(
        tenant=tenant,
        status="RequiresReview",
    ).order_by("-created_at")[:8]

    return render(
        request,
        "accounting/practice_client_detail.html",
        {
            "tenant": tenant,
            "report": report,
            "revenue": _money(report["revenue"]),
            "expenses": _money(report["expenses"]),
            "profit": _money(report["profit"]),
            "vat_due": _money(report["vat_due"]),
            "latest_documents": EvidenceDocument.objects.filter(tenant=tenant).order_by("-uploaded_at")[:8],
            "latest_journals": Journal.objects.filter(tenant=tenant).order_by("-date", "-id")[:8],
            "vat_returns": VatReturn.objects.filter(tenant=tenant).order_by("-end_date")[:6],
            "client_requests": ClientRequest.objects.filter(tenant=tenant).order_by("-submitted_at")[:8],
            "unmatched_bank_transactions": unmatched_bank_transactions,
            "review_journals": review_journals,
            "hmrc_connection": HmrcVatConnection.objects.filter(tenant=tenant).first(),
        },
    )


@login_required(login_url="/login/")
def practice_banking_review(request):
    tenants = list(Tenant.objects.order_by("name"))
    requested_tenant = request.GET.get("company")
    selected_tenant = None

    if request.method == "POST":
        action = request.POST.get("action")
        transaction_id = request.POST.get("transaction_id")
        status = request.POST.get("review_status")
        valid_statuses = {"Unreviewed", "NeedsInfo", "ReadyToPost", "Reviewed"}
        bank_transaction = BankTransaction.objects.filter(id=transaction_id).select_related("tenant").first()
        if action != "update_bank_review" or not bank_transaction:
            messages.error(request, "Bank transaction was not found.")
        elif status not in valid_statuses:
            messages.error(request, "Choose a valid banking review status.")
        else:
            username = request.user.get_username() or "practice"
            posted_journal = None
            if status == "ReadyToPost":
                posted_journal, created = _post_unmatched_bank_transaction(bank_transaction, username)
                status = "Reviewed"
            bank_transaction.review_status = status
            if status == "Unreviewed":
                bank_transaction.reviewed_at = None
                bank_transaction.reviewed_by = ""
            else:
                bank_transaction.reviewed_at = timezone.now()
                bank_transaction.reviewed_by = username
            bank_transaction.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
            _record_audit_event(
                bank_transaction.tenant,
                "BankReview",
                username,
                f"Bank transaction {bank_transaction.id} marked {status}.",
                {
                    "bank_transaction_id": bank_transaction.id,
                    "review_status": status,
                    "posted_journal_id": posted_journal.id if posted_journal else None,
                },
            )
            if posted_journal:
                messages.success(request, f"Bank line posted to journal {posted_journal.id} and marked Reviewed.")
            else:
                messages.success(request, f"Bank line marked {status}.")
        redirect_url = request.path
        if request.POST.get("company"):
            redirect_url = f"{redirect_url}?company={request.POST.get('company')}"
        return redirect(redirect_url)

    queryset = BankTransaction.objects.select_related("tenant", "imported_file")
    if requested_tenant:
        selected_tenant = next(
            (tenant for tenant in tenants if str(tenant.id) == requested_tenant),
            None,
        )
        if selected_tenant:
            queryset = queryset.filter(tenant=selected_tenant)

    reconciled_ids = BankReconciliation.objects.values("bank_transaction_id")
    if selected_tenant:
        reconciled_ids = BankReconciliation.objects.filter(
            tenant=selected_tenant,
        ).values("bank_transaction_id")

    unmatched_bank_transactions = list(
        queryset.exclude(id__in=reconciled_ids).order_by("-date", "-id")[:100]
    )
    unmatched_total = sum(
        (transaction.amount for transaction in unmatched_bank_transactions),
        Decimal("0"),
    )
    affected_clients = len({transaction.tenant_id for transaction in unmatched_bank_transactions})

    return render(
        request,
        "accounting/practice_banking_review.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "unmatched_bank_transactions": unmatched_bank_transactions,
            "unmatched_count": len(unmatched_bank_transactions),
            "unmatched_total": _money(unmatched_total),
            "affected_clients": affected_clients,
        },
    )


@login_required(login_url="/login/")
def practice_ledger_review(request):
    tenants = list(Tenant.objects.order_by("name"))
    requested_tenant = request.GET.get("company")
    selected_tenant = None
    selected_status = request.GET.get("status") or ""

    if request.method == "POST":
        action = request.POST.get("action")
        journal_id = request.POST.get("journal_id")
        journal = Journal.objects.filter(id=journal_id).select_related("tenant").first()
        if action != "approve_journal" or not journal:
            messages.error(request, "Journal was not found.")
        elif journal.status == "Posted":
            messages.info(request, "Journal is already posted.")
        else:
            username = request.user.get_username() or "practice"
            journal.status = "Posted"
            journal.save(update_fields=["status"])
            _record_audit_event(
                journal.tenant,
                "LedgerApproval",
                username,
                f"Journal {journal.id} approved and marked Posted.",
                {"journal_id": journal.id, "source_type": journal.source_type},
            )
            messages.success(request, "Journal approved and marked Posted.")
        redirect_url = request.path
        params = []
        if request.POST.get("company"):
            params.append(f"company={request.POST.get('company')}")
        if request.POST.get("status"):
            params.append(f"status={request.POST.get('status')}")
        if params:
            redirect_url = f"{redirect_url}?{'&'.join(params)}"
        return redirect(redirect_url)

    queryset = Journal.objects.select_related("tenant")
    if requested_tenant:
        selected_tenant = next(
            (tenant for tenant in tenants if str(tenant.id) == requested_tenant),
            None,
        )
        if selected_tenant:
            queryset = queryset.filter(tenant=selected_tenant)
    if selected_status:
        queryset = queryset.filter(status=selected_status)

    journals = list(queryset.order_by("-date", "-id")[:100])
    status_counts = Journal.objects.values("status").annotate(total=Count("id"))
    if selected_tenant:
        status_counts = (
            Journal.objects.filter(tenant=selected_tenant)
            .values("status")
            .annotate(total=Count("id"))
        )
    status_lookup = {row["status"]: row["total"] for row in status_counts}

    return render(
        request,
        "accounting/practice_ledger_review.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "selected_status": selected_status,
            "journals": journals,
            "journal_count": len(journals),
            "posted_count": status_lookup.get("Posted", 0),
            "review_count": status_lookup.get("RequiresReview", 0),
        },
    )


@login_required(login_url="/login/")
def practice_evidence_review(request):
    tenants = list(Tenant.objects.order_by("name"))
    requested_tenant = request.GET.get("company")
    selected_tenant = None

    if request.method == "POST":
        action = request.POST.get("action")
        document_id = request.POST.get("document_id")
        status = request.POST.get("review_status")
        valid_statuses = {"Unreviewed", "NeedsInfo", "ReadyForPosting", "Reviewed"}
        document = EvidenceDocument.objects.filter(id=document_id).select_related("tenant").first()
        if action != "update_evidence_review" or not document:
            messages.error(request, "Evidence document was not found.")
        elif status not in valid_statuses:
            messages.error(request, "Choose a valid evidence review status.")
        else:
            username = request.user.get_username() or "practice"
            journal = None
            if status == "ReadyForPosting":
                journal, created = _create_evidence_review_journal(document, username)
            document.review_status = status
            if status == "Unreviewed":
                document.reviewed_at = None
                document.reviewed_by = ""
            else:
                document.reviewed_at = timezone.now()
                document.reviewed_by = username
            document.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
            _record_audit_event(
                document.tenant,
                "EvidenceReview",
                username,
                f"Evidence document {document.id} marked {status}.",
                {
                    "document_id": document.id,
                    "review_status": status,
                    "journal_id": journal.id if journal else None,
                },
            )
            if journal:
                messages.success(request, f"Evidence review journal {journal.id} created and evidence marked {status}.")
            else:
                messages.success(request, f"Evidence marked {status}.")
        redirect_url = request.path
        if request.POST.get("company"):
            redirect_url = f"{redirect_url}?company={request.POST.get('company')}"
        return redirect(redirect_url)

    queryset = EvidenceDocument.objects.select_related("tenant")
    if requested_tenant:
        selected_tenant = next(
            (tenant for tenant in tenants if str(tenant.id) == requested_tenant),
            None,
        )
        if selected_tenant:
            queryset = queryset.filter(tenant=selected_tenant)

    documents = list(queryset.order_by("-uploaded_at", "-id")[:100])
    document_count = len(documents)
    linked_document_ids = set(
        Journal.objects.filter(evidence_links__document__in=documents)
        .values_list("evidence_links__document_id", flat=True)
        .distinct()
    )
    unlinked_count = document_count - len(linked_document_ids)

    return render(
        request,
        "accounting/practice_evidence_review.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "documents": documents,
            "document_count": document_count,
            "linked_count": len(linked_document_ids),
            "unlinked_count": unlinked_count,
        },
    )


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
    client_requests = (
        ClientRequest.objects.exclude(status="Resolved")
        .select_related("tenant")
        .order_by("-submitted_at")[:8]
    )
    open_client_requests_count = ClientRequest.objects.exclude(status="Resolved").count()
    awaiting_client_vat_count = VatReview.objects.filter(
        status="Ready",
        client_approved=False,
    ).count()
    ready_to_file_vat_count = VatReview.objects.filter(
        client_approved=True,
        status="ClientApproved",
    ).count()

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
        "client_requests": client_requests,
        "open_client_requests_count": open_client_requests_count,
        "awaiting_client_vat_count": awaiting_client_vat_count,
        "ready_to_file_vat_count": ready_to_file_vat_count,
        "hmrc_status": hmrc_sandbox_status(),
    }
    return render(request, "accounting/dashboard.html", context)


@login_required(login_url="/login/")
def hmrc_sandbox_status_view(request):
    tenants, selected_tenant = _selected_tenant(request)
    return render(
        request,
        "accounting/hmrc_status.html",
        {
            "hmrc_status": hmrc_sandbox_status(),
            "tenants": tenants,
            "selected_tenant": selected_tenant,
        },
    )


@login_required(login_url="/login/")
def hmrc_vat_workspace(request):
    tenants, selected_tenant = _selected_tenant(request)
    connection = None
    obligations = []
    prepared_returns = {}
    vat_reviews = {}

    if selected_tenant:
        connection, _ = HmrcVatConnection.objects.get_or_create(tenant=selected_tenant)

    if request.method == "POST" and selected_tenant and connection:
        action = request.POST.get("action")
        if action == "save_vrn":
            vrn = (request.POST.get("vrn") or "").strip().replace(" ", "")
            if not (vrn.isdigit() and len(vrn) == 9):
                messages.error(request, "Enter a valid 9 digit VAT registration number.")
            else:
                connection.vrn = vrn
                connection.save(update_fields=["vrn", "updated_at"])
                messages.success(request, "HMRC VAT registration number saved for this client.")
            return redirect(f"{request.path}?company={selected_tenant.id}")

        if action == "sync_obligations":
            if not connection.access_token or not connection.vrn:
                messages.error(request, "Authorise HMRC and save a VRN before syncing obligations.")
            else:
                try:
                    obligations = retrieve_vat_obligations(
                        connection.access_token,
                        connection.vrn,
                        request.POST.get("from_date") or "2026-01-01",
                        request.POST.get("to_date") or "2026-12-31",
                        f"ledgerhouse-{selected_tenant.id}",
                    )
                    connection.latest_obligations = obligations
                    connection.last_obligations_sync_at = timezone.now()
                    connection.save(update_fields=["latest_obligations", "last_obligations_sync_at", "updated_at"])
                    for obligation in obligations:
                        _ensure_vat_review_for_obligation(selected_tenant, obligation)
                    messages.success(request, f"Synced {len(obligations)} HMRC VAT obligation(s).")
                except HmrcApiError as exc:
                    messages.error(request, f"HMRC obligations sync failed: {exc}")
            return redirect(f"{request.path}?company={selected_tenant.id}")

        if action == "update_review":
            period_key = request.POST.get("period_key")
            review = VatReview.objects.filter(tenant=selected_tenant, period_key=period_key).first()
            if not review:
                messages.error(request, "Sync HMRC obligations before reviewing this period.")
            else:
                review.evidence_complete = request.POST.get("evidence_complete") == "on"
                review.bank_reconciled = request.POST.get("bank_reconciled") == "on"
                review.vat_codes_reviewed = request.POST.get("vat_codes_reviewed") == "on"
                review.exceptions_resolved = request.POST.get("exceptions_resolved") == "on"
                if review.checklist_complete:
                    review.status = "Ready" if not review.client_approved else "ClientApproved"
                    review.practice_approved_at = timezone.now()
                    review.practice_approved_by = request.user.get_username() or "practice"
                else:
                    review.status = "Draft"
                    review.practice_approved_at = None
                    review.practice_approved_by = ""
                review.save()
                messages.success(request, f"Review checklist saved for VAT period {period_key}.")
            return redirect(f"{request.path}?company={selected_tenant.id}")

        if action == "submit_return":
            period_key = request.POST.get("period_key")
            matching_obligation = next(
                (item for item in connection.latest_obligations if item.get("periodKey") == period_key),
                None,
            )
            review = VatReview.objects.filter(tenant=selected_tenant, period_key=period_key).first()
            if not connection.access_token or not connection.vrn:
                messages.error(request, "Authorise HMRC and save a VRN before submitting.")
            elif not matching_obligation:
                messages.error(request, "Sync HMRC obligations before submitting this period.")
            elif matching_obligation.get("status") != "O":
                messages.error(request, "Only open HMRC VAT periods can be submitted.")
            elif not review or not review.ready_to_submit:
                messages.error(request, "Complete the practice checklist and client approval before HMRC submission.")
            else:
                payload = review.prepared_payload or serialize_vat_return_9_box(
                    selected_tenant,
                    matching_obligation["start"],
                    matching_obligation["end"],
                )
                payload["periodKey"] = period_key
                hmrc_payload = to_hmrc_vat_return_payload(payload)
                try:
                    response_payload = submit_vat_return_payload(
                        connection.access_token,
                        connection.vrn,
                        hmrc_payload,
                        f"ledgerhouse-{selected_tenant.id}",
                    )
                    connection.last_submission_response = response_payload
                    connection.save(update_fields=["last_submission_response", "updated_at"])
                    VatReturn.objects.update_or_create(
                        tenant=selected_tenant,
                        period_key=period_key,
                        defaults={
                            "start_date": date.fromisoformat(matching_obligation["start"]),
                            "end_date": date.fromisoformat(matching_obligation["end"]),
                            "locked_by": request.user.get_username() or "system",
                            "total_output_vat": Decimal(str(hmrc_payload["vatDueSales"])),
                            "total_input_vat": Decimal(str(payload["vatReclaimedCurrPeriod"])),
                            "net_vat_payable": Decimal(str(payload["netVatDue"])),
                            "status": "Submitted",
                            "hmrc_receipt_id": response_payload.get("formBundleNumber"),
                            "submitted_at": timezone.now(),
                        },
                    )
                    review.status = "Submitted"
                    review.submitted_at = timezone.now()
                    review.hmrc_receipt_id = response_payload.get("formBundleNumber") or ""
                    review.save(update_fields=["status", "submitted_at", "hmrc_receipt_id", "updated_at"])
                    messages.success(request, f"Submitted VAT period {period_key} to HMRC sandbox.")
                except HmrcApiError as exc:
                    try:
                        existing_return = retrieve_vat_return(
                            connection.access_token,
                            connection.vrn,
                            period_key,
                            f"ledgerhouse-{selected_tenant.id}",
                        )
                        messages.error(
                            request,
                            f"HMRC rejected the submission, but an existing return for {period_key} was retrieved.",
                        )
                        connection.last_submission_response = {"existing_return": existing_return}
                        connection.save(update_fields=["last_submission_response", "updated_at"])
                        review.status = "Submitted"
                        review.submitted_at = timezone.now()
                        review.save(update_fields=["status", "submitted_at", "updated_at"])
                    except HmrcApiError:
                        messages.error(request, f"HMRC VAT submission failed: {exc}")
            return redirect(f"{request.path}?company={selected_tenant.id}")

    if connection:
        obligations = connection.latest_obligations or []
        for obligation in obligations:
            _, prepared = _ensure_vat_review_for_obligation(selected_tenant, obligation)
            prepared_returns[obligation["periodKey"]] = prepared
        vat_reviews = {
            review.period_key: review
            for review in VatReview.objects.filter(
                tenant=selected_tenant,
                period_key__in=[item.get("periodKey") for item in obligations],
            )
        }

    return render(
        request,
        "accounting/hmrc_vat_workspace.html",
        {
            "hmrc_status": hmrc_sandbox_status(),
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "connection": connection,
            "obligations": obligations,
            "prepared_returns": prepared_returns,
            "vat_reviews": vat_reviews,
        },
    )


@login_required(login_url="/login/")
def client_vat_review(request):
    tenants, selected_tenant = _selected_tenant(request)
    reviews = []

    if selected_tenant:
        reviews = VatReview.objects.filter(tenant=selected_tenant).order_by("-end_date", "-id")

    if request.method == "POST" and selected_tenant:
        period_key = request.POST.get("period_key")
        review = VatReview.objects.filter(tenant=selected_tenant, period_key=period_key).first()
        if not review:
            messages.error(request, "VAT review was not found for this client.")
        elif not review.checklist_complete:
            messages.error(request, "The accountant checklist must be complete before client approval.")
        else:
            review.client_approved = True
            review.client_approved_at = timezone.now()
            review.client_approved_by = request.user.get_username() or "client"
            review.status = "ClientApproved"
            review.save()
            messages.success(request, f"VAT period {period_key} approved for filing.")
        return redirect(f"{request.path}?company={selected_tenant.id}")

    return render(
        request,
        "accounting/client_vat_review.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "reviews": reviews,
        },
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

    next_url = unpacked_state.get("next") or ""
    tenant_id = (parse_qs(urlparse(next_url).query).get("company") or [None])[0]
    if tenant_id:
        try:
            tenant = Tenant.objects.get(id=tenant_id)
            connection, _ = HmrcVatConnection.objects.get_or_create(tenant=tenant)
            expires_in = token_payload.get("expires_in") or 0
            connection.access_token = token_payload.get("access_token") or ""
            connection.refresh_token = token_payload.get("refresh_token") or ""
            connection.scope = token_payload.get("scope") or ""
            connection.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            connection.last_authorised_at = timezone.now()
            connection.status = "Connected"
            connection.save()
        except (Tenant.DoesNotExist, ValueError):
            messages.warning(request, "HMRC authorised, but the selected client could not be linked.")
    messages.success(request, "HMRC VAT sandbox authorisation completed.")
    return redirect(unpacked_state.get("next") or "hmrc_sandbox_status")
