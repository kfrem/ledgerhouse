from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hmac
import logging
import re
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.db import connection, transaction
from django.db.models import Count, F, Max, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .companies_house import (
    CompaniesHouseApiError,
    assess_companies_house_approval_gate,
    build_get_submission_status_xml,
    companies_house_next_local_build_items,
    companies_house_initial_filing_scope,
    companies_house_rejection_actions,
    companies_house_status,
    company_profile_snapshot,
    normalise_company_number,
    poll_companies_house_submission_status,
    prepare_companies_house_test_submission,
    retrieve_company_profile,
    submit_companies_house_test_submission,
)
from .companies_house_scenarios import build_companies_house_local_scenarios, companies_house_scenario_summary
from .exceptions import exception_register
from .ixbrl import generate_micro_entity_ixbrl, validate_micro_entity_ixbrl
from .intake import process_uploaded_file
from .local_completion import build_no_hmrc_completion_zip
from .middleware import tenant_context
from .mtd import (
    HmrcApiError,
    build_web_app_via_server_fraud_prevention_headers,
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
from .hmrc_services import (
    HMRC_SERVICES,
    ensure_hmrc_service_approvals,
    run_hmrc_filing_preflight,
    set_case_payload,
)
from .hmrc_income_tax import income_tax_subscription_status
from .models import (
    AuditEvent,
    BankReconciliation,
    BankTransaction,
    BankRule,
    ClientInvitation,
    ClientApprovalRecord,
    CompaniesHouseApprovalGate,
    CompaniesHouseFilingSubmission,
    CompaniesHouseSubmissionPoll,
    ClientRequest,
    EvidenceDocument,
    HmrcVatConnection,
    HmrcFilingCase,
    HmrcServiceApproval,
    HmrcTaxProfile,
    Journal,
    JournalEvidenceLink,
    JournalLine,
    NominalAccount,
    AccountingTask,
    AccountingPeriodLock,
    CorporationTaxEstimate,
    DocumentIntelligenceRule,
    FixedAsset,
    ManagementPackSection,
    SubscriptionPlan,
    MonthEndClose,
    NotificationEvent,
    PayrollSummary,
    PurchaseBill,
    PurchaseOrder,
    SalesInvoice,
    SalesQuote,
    StatutoryAccountsDraft,
    SupplierPaymentRun,
    Tenant,
    TenantUserAccess,
    VatReturn,
    VatReview,
)
from .operations import (
    accounts_department_snapshot,
    build_local_accounts_department_suite,
)
from .payroll_cis import post_payroll_period
from .period_end import close_period_end, period_end_control_status, post_period_end_schedules
from .workflow_controls import (
    mark_supplier_payment_run_paid,
    record_sales_receipt,
    release_approved_pack,
    transition_task,
)
from .production import accounts_production_snapshot
from .notifications import record_notification_preview
from .reports import (
    accounts_department_pack_pdf,
    client_data_export_zip,
    management_report_context,
    management_report_csv,
    management_report_pack_pdf,
    management_report_pdf,
)


logger = logging.getLogger(__name__)


def _money(value):
    value = value or Decimal("0")
    return f"GBP {value:,.2f}"


def _is_practice_staff(user):
    return user.is_authenticated and user.is_staff


practice_staff_required = user_passes_test(_is_practice_staff, login_url="/login/")


def health_check(request):
    """Return a non-sensitive liveness and database-readiness response."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _tenants_for_user(user):
    if user.is_staff or user.is_superuser:
        return Tenant.objects.order_by("name")
    return Tenant.objects.filter(
        user_access__user=user,
        user_access__is_active=True,
    ).distinct().order_by("name")


def _selected_tenant(request):
    tenants = list(_tenants_for_user(request.user))
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


def _authorised_tenant_for_user(user, tenant_id):
    tenant = _tenants_for_user(user).filter(id=tenant_id).first()
    if not tenant:
        raise Http404("Company not found")
    return tenant


def _request_public_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def _hmrc_web_fraud_headers(request, tenant):
    public_ip = _request_public_ip(request)
    return build_web_app_via_server_fraud_prevention_headers(
        device_id=request.POST.get("fraud_device_id") or f"ledgerhouse-{tenant.id}",
        public_ip=public_ip,
        public_port=request.META.get("REMOTE_PORT", "0"),
        browser_js_user_agent=(
            request.POST.get("fraud_browser_js_user_agent")
            or request.META.get("HTTP_USER_AGENT", "")
        ),
        screens=request.POST.get("fraud_screens", ""),
        timezone=request.POST.get("fraud_timezone", ""),
        user_id=request.user.get_username() or str(request.user.id),
        window_size=request.POST.get("fraud_window_size", ""),
        vendor_public_ip=getattr(settings, "HMRC_VENDOR_PUBLIC_IP", "127.0.0.1"),
        vendor_version=getattr(settings, "HMRC_VENDOR_VERSION", "LedgerHouse=local"),
    )


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


def _invitation_accept_url(request, invitation):
    return request.build_absolute_uri(f"/invite/{invitation.id}/")


def _decimal_or_none(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError("Enter a valid amount.")


def _date_or_none(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Enter a valid date in YYYY-MM-DD format.")


def _accounts_department_workflow(tenant):
    reconciled_ids = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    evidence_total = EvidenceDocument.objects.filter(tenant=tenant).count()
    unreviewed_evidence = (
        EvidenceDocument.objects.filter(tenant=tenant)
        .exclude(review_status="ReadyForPosting")
        .count()
    )
    bank_total = BankTransaction.objects.filter(tenant=tenant).count()
    unmatched_bank = (
        BankTransaction.objects.filter(tenant=tenant)
        .exclude(id__in=reconciled_ids)
        .count()
    )
    journal_total = Journal.objects.filter(tenant=tenant).count()
    review_journals = Journal.objects.filter(
        tenant=tenant,
        status="RequiresReview",
    ).count()
    open_requests = ClientRequest.objects.filter(tenant=tenant).exclude(status="Resolved").count()
    waiting_returns = VatReview.objects.filter(
        tenant=tenant,
        status="Ready",
        client_approved=False,
    ).count()

    def tone(open_count, total_count=0):
        if open_count:
            return "attention"
        if total_count:
            return "ready"
        return ""

    return [
        {
            "label": "Source documents",
            "status": "Needs review" if unreviewed_evidence else "Under control",
            "count": unreviewed_evidence,
            "detail": f"{evidence_total} file(s) received; {unreviewed_evidence} still need bookkeeping treatment.",
            "href": "practice_evidence_review",
            "anchor": "#upload",
            "tone": tone(unreviewed_evidence, evidence_total),
        },
        {
            "label": "Bank matching",
            "status": "Needs matching" if unmatched_bank else "Reconciled",
            "count": unmatched_bank,
            "detail": f"{bank_total} bank line(s) imported; {unmatched_bank} still need allocation.",
            "href": "practice_banking_review",
            "anchor": "#support",
            "tone": tone(unmatched_bank, bank_total),
        },
        {
            "label": "Bookkeeping",
            "status": "Needs approval" if review_journals else "Posted",
            "count": review_journals,
            "detail": f"{journal_total} ledger entries prepared; {review_journals} require accountant sign-off.",
            "href": "practice_ledger_review",
            "anchor": "#reports",
            "tone": tone(review_journals, journal_total),
        },
        {
            "label": "Management reporting",
            "status": "Available" if journal_total else "Waiting for records",
            "count": journal_total,
            "detail": "Reports are generated from the latest ledger, bank and evidence records.",
            "href": "management_report",
            "anchor": "#reports",
            "tone": "ready" if journal_total else "",
        },
        {
            "label": "Statutory compliance",
            "status": "Approval needed" if waiting_returns else "No approval waiting",
            "count": waiting_returns,
            "detail": f"{waiting_returns} return period(s) currently need client approval.",
            "href": "hmrc_vat_workspace",
            "anchor": "",
            "tone": tone(waiting_returns),
        },
        {
            "label": "Advice and questions",
            "status": "Open" if open_requests else "Clear",
            "count": open_requests,
            "detail": f"{open_requests} client question(s) are open with the accounts team.",
            "href": "practice_clients",
            "anchor": "#support",
            "tone": tone(open_requests),
        },
    ]


def _client_operating_snapshot(tenant, report):
    subscription = SubscriptionPlan.objects.filter(tenant=tenant).first()
    hmrc_connection = HmrcVatConnection.objects.filter(tenant=tenant).first()
    companies_house = companies_house_status()
    has_payment_provider = bool(
        subscription
        and subscription.billing_provider != SubscriptionPlan.PROVIDER_MANUAL
        and subscription.provider_customer_id
    )
    has_live_filing = bool(hmrc_connection and hmrc_connection.status == "Connected")
    runway = report.get("cash_runway_months")
    runway_label = "Not enough spending history"
    if runway is not None:
        runway_label = f"{runway} month(s)"

    return [
        {
            "label": "Accounts department",
            "status": "Live locally",
            "detail": f"{report['evidence_count']} files, {report['journal_count']} ledger entries and {report['bank_count']} bank lines are in the workspace.",
            "tone": "ready" if report["journal_count"] else "",
        },
        {
            "label": "Reporting pack",
            "status": "Ready" if report["journal_count"] else "Waiting for records",
            "detail": f"Profit {_money(report['profit'])}; net margin {report['net_margin']}%; cash runway {runway_label}.",
            "tone": "ready" if report["journal_count"] else "",
        },
        {
            "label": "Client service",
            "status": "Open queue" if report["open_client_requests"] else "Clear",
            "detail": f"{report['open_client_requests']} advice request(s), {report['unreviewed_evidence']} file(s) in review and {report['unreconciled_count']} unmatched bank line(s).",
            "tone": "attention" if report["open_client_requests"] or report["unreviewed_evidence"] or report["unreconciled_count"] else "ready",
        },
        {
            "label": "Billing readiness",
            "status": "Provider linked" if has_payment_provider else "Local/manual",
            "detail": "Subscription records are active locally; live card/direct debit collection waits for provider credentials.",
            "tone": "ready" if has_payment_provider else "",
        },
        {
            "label": "Government services",
            "status": "Live filing connected" if has_live_filing else "Sandbox/local",
            "detail": "HMRC and Companies House screens can be tested locally; live submissions depend on external approval.",
            "tone": "ready" if has_live_filing and companies_house.get("configured") else "",
        },
    ]


def _client_accounts_health_plan(report, waiting_vat_count, pending_approval_count):
    plan = []
    if not report:
        return plan

    def status_label(count, clear_label, action_label):
        return action_label if count else clear_label

    journal_label = "bookkeeping entry" if report["journal_count"] == 1 else "bookkeeping entries"
    journal_verb = "is" if report["journal_count"] == 1 else "are"
    plan.append(
        {
            "label": "Records received",
            "status": status_label(report["evidence_count"], "Waiting for first upload", "Source records active"),
            "detail": (
                f"{report['evidence_count']} uploaded document(s) are in the evidence vault. "
                f"{report['unreviewed_evidence']} still need accountant review."
            ),
            "next_action": "Upload missing receipts, invoices, payroll files or spreadsheets.",
            "href": "#upload",
            "tone": "attention" if report["unreviewed_evidence"] else "ready",
        }
    )
    plan.append(
        {
            "label": "Bank matching",
            "status": status_label(report["unreconciled_count"], "Matched", "Needs explanation"),
            "detail": f"{report['unreconciled_count']} bank transaction(s) still need matching or explanation.",
            "next_action": "Send the accountant a note for any unknown card payments or receipts.",
            "href": "#support",
            "tone": "attention" if report["unreconciled_count"] else "ready",
        }
    )
    plan.append(
        {
            "label": "Bookkeeping position",
            "status": status_label(report["journal_count"], "Waiting for postings", "Books being built"),
            "detail": (
                f"{report['journal_count']} {journal_label} {journal_verb} recorded. "
                f"Current profit is {_money(report['profit'])}."
            ),
            "next_action": "Review the plain-English figures and ask for advice where the numbers look wrong.",
            "href": "#reports",
            "tone": "ready" if report["journal_count"] else "",
        }
    )
    approvals_waiting = waiting_vat_count + pending_approval_count
    plan.append(
        {
            "label": "Approvals",
            "status": status_label(approvals_waiting, "Nothing waiting", "Review needed"),
            "detail": f"{approvals_waiting} report, accounts or statutory approval item(s) are waiting.",
            "next_action": "Open approvals before anything is treated as final.",
            "href": "#approvals",
            "tone": "attention" if approvals_waiting else "ready",
        }
    )
    plan.append(
        {
            "label": "Management pack",
            "status": status_label(report["journal_count"], "Waiting for bookkeeping", "Available locally"),
            "detail": (
                "The report pack uses ledger, bank, evidence and client-query data already held locally."
            ),
            "next_action": "Download the pack when you need figures for management, lenders or advisers.",
            "href": "#reports",
            "tone": "ready" if report["journal_count"] else "",
        }
    )
    return plan


def privacy_notice(request):
    return render(request, "accounting/privacy.html")


def terms_and_conditions(request):
    return render(request, "accounting/terms.html")


def accept_invitation(request, invitation_id):
    invitation = ClientInvitation.objects.select_related("tenant").filter(id=invitation_id).first()
    if not invitation:
        raise Http404("Invitation not found")

    if invitation.status == ClientInvitation.STATUS_REVOKED:
        messages.error(request, "This invitation has been revoked.")
        return redirect("login")

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        password = request.POST.get("password") or ""
        if len(password) < 8:
            messages.error(request, "Enter a password with at least 8 characters.")
        else:
            User = get_user_model()
            username = invitation.email.lower()
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": invitation.email,
                    "first_name": full_name[:150],
                },
            )
            if not created and not user.email:
                user.email = invitation.email
            if full_name:
                user.first_name = full_name[:150]
            user.set_password(password)
            user.save()

            TenantUserAccess.objects.update_or_create(
                tenant=invitation.tenant,
                user=user,
                defaults={
                    "role": invitation.role,
                    "is_active": True,
                },
            )
            invitation.status = ClientInvitation.STATUS_ACCEPTED
            invitation.accepted_at = timezone.now()
            invitation.accepted_by = user.username
            invitation.save(update_fields=["status", "accepted_at", "accepted_by"])
            _record_audit_event(
                invitation.tenant,
                "ClientInvitationAccepted",
                user.username,
                f"Invitation accepted by {user.username}.",
                {"email": invitation.email, "role": invitation.role},
            )
            messages.success(request, "Your LedgerHouse access has been created. Sign in to continue.")
            return redirect("login")

    return render(
        request,
        "accounting/accept_invitation.html",
        {
            "invitation": invitation,
            "tenant": invitation.tenant,
        },
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

    if document.gross_amount:
        gross = document.gross_amount
        vat = document.vat_amount or Decimal("0.00")
        net = gross - vat
        document_date = document.document_date or timezone.localdate()
        suggested_code = document.suggested_account_code or (
            "4000" if document.document_category == "SalesInvoice" else "6000"
        )
        if document.document_category == "SalesInvoice":
            control_account = _ensure_nominal(document.tenant, "1100", "Aged debtors", "Asset", "Trade Debtors")
            posting_account = _ensure_nominal(document.tenant, suggested_code, "Sales", "Revenue", "Revenue")
            vat_account = _ensure_nominal(document.tenant, "2200", "VAT control", "Liability", "VAT")
            with transaction.atomic():
                journal = Journal.objects.create(
                    tenant=document.tenant,
                    date=document_date,
                    description=f"Sales evidence: {document.supplier_or_customer or document.filename}",
                    source_type="EvidenceReview",
                    source_id=source_id,
                    created_by=username or "practice",
                    status="RequiresReview",
                )
                JournalLine.objects.create(tenant=document.tenant, journal=journal, account=control_account, debit=gross, credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=document.tenant, journal=journal, account=posting_account, debit=Decimal("0.00"), credit=net)
                if vat:
                    JournalLine.objects.create(tenant=document.tenant, journal=journal, account=vat_account, debit=Decimal("0.00"), credit=vat)
                JournalEvidenceLink.objects.get_or_create(
                    tenant=document.tenant,
                    journal=journal,
                    document=document,
                    defaults={"linked_by": username or "practice"},
                )
                journal.status = "RequiresReview"
                journal.save(update_fields=["status"])
            return journal, True

        control_account = _ensure_nominal(document.tenant, "2100", "Aged creditors", "Liability", "Trade Creditors")
        posting_account = _ensure_nominal(document.tenant, suggested_code, "Office costs", "Expense", "Expense")
        vat_account = _ensure_nominal(document.tenant, "2200", "VAT control", "Liability", "VAT")
        with transaction.atomic():
            journal = Journal.objects.create(
                tenant=document.tenant,
                date=document_date,
                description=f"Purchase evidence: {document.supplier_or_customer or document.filename}",
                source_type="EvidenceReview",
                source_id=source_id,
                created_by=username or "practice",
                status="RequiresReview",
            )
            JournalLine.objects.create(tenant=document.tenant, journal=journal, account=posting_account, debit=net, credit=Decimal("0.00"))
            if vat:
                JournalLine.objects.create(tenant=document.tenant, journal=journal, account=vat_account, debit=vat, credit=Decimal("0.00"))
            JournalLine.objects.create(tenant=document.tenant, journal=journal, account=control_account, debit=Decimal("0.00"), credit=gross)
            JournalEvidenceLink.objects.get_or_create(
                tenant=document.tenant,
                journal=journal,
                document=document,
                defaults={"linked_by": username or "practice"},
            )
            journal.status = "RequiresReview"
            journal.save(update_fields=["status"])
        return journal, True

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


def _extract_evidence_suggestions(document):
    raw = f"{document.filename}\n"
    if document.content_type.startswith("text/") or document.filename.lower().endswith((".csv", ".txt")):
        raw += bytes(document.file_content).decode("utf-8", errors="ignore")[:4000]
    lower = raw.lower()

    category = document.document_category
    matched_rule = None
    for rule in DocumentIntelligenceRule.objects.filter(tenant=document.tenant, is_active=True).order_by("-confidence", "name"):
        if rule.keyword.lower() in lower:
            matched_rule = rule
            category = rule.document_category
            break
    if category == "Uncategorised":
        if "sales" in lower or "customer" in lower:
            category = "SalesInvoice"
        elif "invoice" in lower or "bill" in lower or "supplier" in lower:
            category = "PurchaseInvoice"
        elif "receipt" in lower:
            category = "Receipt"
        elif "bank" in lower or "statement" in lower:
            category = "BankStatement"
        elif "payroll" in lower or "paye" in lower:
            category = "Payroll"
        elif "contract" in lower:
            category = "Contract"
        elif "tax" in lower or "hmrc" in lower:
            category = "Tax"
        else:
            category = "Other"

    amount = document.gross_amount
    if amount is None:
        amount_match = re.search(r"(?:£|gbp\s*)?([0-9]{1,7}(?:,[0-9]{3})*(?:\.[0-9]{2}))", lower, re.I)
        if amount_match:
            amount = Decimal(amount_match.group(1).replace(",", ""))

    document_date = document.document_date
    if document_date is None:
        iso_match = re.search(r"(20[0-9]{2})[-_/](0[1-9]|1[0-2])[-_/]([0-3][0-9])", raw)
        uk_match = re.search(r"([0-3][0-9])[-_/](0[1-9]|1[0-2])[-_/](20[0-9]{2})", raw)
        try:
            if iso_match:
                document_date = date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            elif uk_match:
                document_date = date(int(uk_match.group(3)), int(uk_match.group(2)), int(uk_match.group(1)))
        except ValueError:
            document_date = None

    supplier = document.supplier_or_customer
    if not supplier:
        name = re.sub(r"\.[^.]+$", "", document.filename)
        name = re.sub(r"[_-]+", " ", name)
        name = re.sub(r"\b(20[0-9]{2}|invoice|receipt|bill|pdf|csv|xlsx|jpg|png)\b", "", name, flags=re.I)
        supplier = " ".join(name.split()).title()[:160]

    suggested_code = document.suggested_account_code
    if matched_rule:
        suggested_code = matched_rule.suggested_account_code
    elif not suggested_code:
        if category == "SalesInvoice":
            suggested_code = "4000"
        elif category == "Payroll":
            suggested_code = "7000"
        elif category == "BankStatement":
            suggested_code = "1200"
        else:
            suggested_code = "6000"

    vat_amount = document.vat_amount
    if amount is not None and vat_amount is None and (" vat" in lower or "vat " in lower or category in {"PurchaseInvoice", "SalesInvoice"}):
        vat_amount = (amount / Decimal("6")).quantize(Decimal("0.01"))

    return {
        "document_category": category,
        "supplier_or_customer": supplier,
        "document_date": document_date,
        "gross_amount": amount,
        "vat_amount": vat_amount,
        "suggested_account_code": suggested_code,
    }


def _bank_rule_suggestion(bank_transaction):
    reference = (bank_transaction.reference or "").lower()
    for rule in BankRule.objects.filter(tenant=bank_transaction.tenant, is_active=True).order_by("-confidence", "name"):
        if rule.match_text.lower() in reference:
            return {
                "rule": rule,
                "account": _ensure_nominal(
                    bank_transaction.tenant,
                    rule.account_code,
                    f"Suggested account {rule.account_code}",
                    "Expense" if bank_transaction.amount < 0 else "Revenue",
                    "BankRule",
                ),
            }
    return {"rule": None, "account": None}


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
    suggestion = _bank_rule_suggestion(bank_transaction)
    expense = suggestion["account"] or _ensure_nominal(bank_transaction.tenant, "6000", "Office costs", "Expense", "Expense")
    revenue = suggestion["account"] or _ensure_nominal(bank_transaction.tenant, "4000", "Sales", "Revenue", "Revenue")
    amount = abs(bank_transaction.amount)
    source_type = "BankPayment" if bank_transaction.amount < 0 else "BankReceipt"

    with transaction.atomic():
        journal = existing_journal or Journal.objects.create(
            tenant=bank_transaction.tenant,
            date=bank_transaction.date,
            description=(
                f"Auto-posted unmatched bank line: {bank_transaction.reference}"
                + (f" via bank rule {suggestion['rule'].name}" if suggestion["rule"] else "")
            ),
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
        if action in {"approve_client_item", "reject_client_item"}:
            approval = ClientApprovalRecord.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("approval_id"),
            ).first()
            note = (request.POST.get("decision_note") or "").strip()
            if not approval:
                messages.error(request, "Approval item was not found.")
            elif approval.status != ClientApprovalRecord.STATUS_PENDING:
                messages.info(request, "This item has already been decided.")
            else:
                approval.status = (
                    ClientApprovalRecord.STATUS_APPROVED
                    if action == "approve_client_item"
                    else ClientApprovalRecord.STATUS_REJECTED
                )
                approval.decided_by = request.user.get_username() or "client"
                approval.decided_at = timezone.now()
                approval.decision_note = note
                approval.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
                _record_audit_event(
                    selected_tenant,
                    "ClientApproval",
                    request.user.get_username(),
                    f"Client marked '{approval.title}' as {approval.status}.",
                    {"approval_id": approval.id, "approval_type": approval.approval_type},
                )
                messages.success(request, f"{approval.title} marked {approval.status.lower()}.")
            return redirect(f"{request.path}?company={selected_tenant.id}#approvals")

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
    unreviewed_evidence_count = 0
    journal_count = 0
    open_request_count = 0
    ready_vat_count = 0
    waiting_vat_count = 0
    latest_documents = []
    latest_journals = []
    vat_returns = []
    client_requests = []
    approval_records = []
    pending_approval_count = 0
    action_cards = []
    accounts_workflow = []
    operating_snapshot = []
    accounts_health_plan = []
    report = None

    if selected_tenant:
        report = management_report_context(selected_tenant)
        revenue = report["revenue"]
        expenses = report["expenses"]
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
        unreviewed_evidence_count = (
            EvidenceDocument.objects.filter(tenant=selected_tenant)
            .exclude(review_status="ReadyForPosting")
            .count()
        )
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
        approval_records = ClientApprovalRecord.objects.filter(
            tenant=selected_tenant
        ).order_by("status", "-requested_at")[:8]
        pending_approval_count = ClientApprovalRecord.objects.filter(
            tenant=selected_tenant,
            status=ClientApprovalRecord.STATUS_PENDING,
        ).count()
        open_request_count = ClientRequest.objects.filter(
            tenant=selected_tenant
        ).exclude(status="Resolved").count()
        ready_vat_count = VatReview.objects.filter(
            tenant=selected_tenant,
            status="ClientApproved",
        ).count()
        waiting_vat_count = VatReview.objects.filter(
            tenant=selected_tenant,
            status="Ready",
            client_approved=False,
        ).count()
        action_cards = [
            {
                "title": "Upload outstanding paperwork",
                "detail": f"{unreviewed_evidence_count} uploaded file(s) are still being reviewed.",
                "status": "In review" if unreviewed_evidence_count else "Clear",
                "href": "#upload",
                "tone": "attention" if unreviewed_evidence_count else "ready",
            },
            {
                "title": "Explain unmatched bank lines",
                "detail": f"{unreconciled_count} bank transaction(s) still need matching or explanation.",
                "status": "Needs input" if unreconciled_count else "Matched",
                "href": "#support",
                "tone": "attention" if unreconciled_count else "ready",
            },
            {
                "title": "Review statutory approvals",
                "detail": f"{waiting_vat_count + pending_approval_count} approval item(s) are waiting for review.",
                "status": "Review" if waiting_vat_count or pending_approval_count else "None waiting",
                "href": "#approvals" if pending_approval_count else "client_vat_review",
                "tone": "attention" if waiting_vat_count or pending_approval_count else "ready",
            },
            {
                "title": "Read accountant replies",
                "detail": f"{open_request_count} open question(s) are in the advice queue.",
                "status": "Open" if open_request_count else "Clear",
                "href": "#support",
                "tone": "ready" if not open_request_count else "",
            },
        ]
        accounts_workflow = _accounts_department_workflow(selected_tenant)
        operating_snapshot = _client_operating_snapshot(selected_tenant, report)
        accounts_health_plan = _client_accounts_health_plan(
            report,
            waiting_vat_count,
            pending_approval_count,
        )

    context = {
        "tenants": tenants,
        "selected_tenant": selected_tenant,
        "report": report,
        "revenue": _money(revenue),
        "expenses": _money(expenses),
        "profit": _money(revenue - expenses),
        "gross_profit": _money(report["gross_profit"]) if report else _money(Decimal("0")),
        "gross_margin": report["gross_margin"] if report else Decimal("0"),
        "net_margin": report["net_margin"] if report else Decimal("0"),
        "cash_runway_months": report["cash_runway_months"] if report else None,
        "vat_due": _money(vat_due),
        "bank_count": bank_count,
        "unreconciled_count": unreconciled_count,
        "evidence_count": evidence_count,
        "unreviewed_evidence_count": unreviewed_evidence_count,
        "journal_count": journal_count,
        "open_request_count": open_request_count,
        "ready_vat_count": ready_vat_count,
        "waiting_vat_count": waiting_vat_count,
        "latest_documents": latest_documents,
        "latest_journals": latest_journals,
        "vat_returns": vat_returns,
        "client_requests": client_requests,
        "approval_records": approval_records,
        "pending_approval_count": pending_approval_count,
        "action_cards": action_cards,
        "accounts_workflow": accounts_workflow,
        "operating_snapshot": operating_snapshot,
        "accounts_health_plan": accounts_health_plan,
    }
    return render(request, "accounting/client_portal.html", context)


@login_required(login_url="/login/")
def management_report_view(request, tenant_id):
    tenant = _authorised_tenant_for_user(request.user, tenant_id)

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
            "operating_snapshot": _client_operating_snapshot(tenant, report),
            "revenue": _money(report["revenue"]),
            "expenses": _money(report["expenses"]),
            "gross_profit": _money(report["gross_profit"]),
            "profit": _money(report["profit"]),
            "gross_margin": report["gross_margin"],
            "net_margin": report["net_margin"],
            "cash_runway_months": report["cash_runway_months"],
            "cash_balance": _money(report["cash_balance"]),
            "gross_assets": _money(report["gross_assets"]),
            "liabilities": _money(report["liabilities"]),
            "net_assets": _money(report["net_assets"]),
            "equity": _money(report["equity"]),
            "vat_due": _money(report["vat_due"]),
            "aged_debtors": _money(report["aged_debtors"]),
            "aged_creditors": _money(report["aged_creditors"]),
        },
    )


@login_required(login_url="/login/")
def download_management_report(request, tenant_id, file_format):
    tenant = _authorised_tenant_for_user(request.user, tenant_id)

    if file_format == "csv":
        response = HttpResponse(management_report_csv(tenant), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-management-report.csv"'
        return response
    if file_format == "pdf":
        response = HttpResponse(management_report_pdf(tenant), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-management-report.pdf"'
        return response
    if file_format == "pack":
        response = HttpResponse(management_report_pack_pdf(tenant), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-management-pack.pdf"'
        return response
    if file_format == "accounts-department-pack":
        response = HttpResponse(accounts_department_pack_pdf(tenant), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-accounts-department-pack.pdf"'
        return response
    if file_format == "zip":
        response = HttpResponse(client_data_export_zip(tenant), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{tenant.name}-data-export.zip"'
        return response
    raise Http404("Report format not supported")


@login_required(login_url="/login/")
@practice_staff_required
def download_no_hmrc_completion_pack(request):
    pack_bytes, results = build_no_hmrc_completion_zip(
        "output/no_hmrc_completion_web",
        username=request.user.get_username() or "practice",
    )
    failed = [result for result in results if not result.passed]
    if failed:
        raise Http404("Local no-HMRC completion pack is not ready.")
    response = HttpResponse(pack_bytes, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="ledgerhouse-no-hmrc-local-completion-pack.zip"'
    return response


@login_required(login_url="/login/")
@practice_staff_required
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
                # New company setup runs inside the new tenant context so the
                # restricted PostgreSQL role cannot seed another tenant by
                # accident.
                with tenant_context(tenant.id):
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
@practice_staff_required
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
        elif action == "create_invitation":
            email = (request.POST.get("email") or "").strip().lower()
            role = request.POST.get("role") or TenantUserAccess.ROLE_CLIENT
            if not email or "@" not in email:
                messages.error(request, "Enter a valid client email before creating an invitation.")
            elif role not in {TenantUserAccess.ROLE_CLIENT, TenantUserAccess.ROLE_PRACTICE}:
                messages.error(request, "Choose a valid invitation role.")
            else:
                invitation, created = ClientInvitation.objects.get_or_create(
                    tenant=tenant,
                    email=email,
                    defaults={
                        "role": role,
                        "invited_by": request.user.get_username() or "practice",
                    },
                )
                if not created and invitation.status != ClientInvitation.STATUS_REVOKED:
                    messages.info(request, "That invitation already exists for this client.")
                else:
                    invitation.role = role
                    invitation.status = ClientInvitation.STATUS_PENDING
                    invitation.invited_by = request.user.get_username() or "practice"
                    invitation.accepted_at = None
                    invitation.accepted_by = ""
                    invitation.save()
                    messages.success(request, f"Invitation prepared for {email}. Accept link: {_invitation_accept_url(request, invitation)}")
                _record_audit_event(
                    tenant,
                    "ClientInvitation",
                    request.user.get_username(),
                    f"Invitation {'created' if created else 'updated'} for {email}.",
                    {"email": email, "role": role},
                )
        elif action == "update_subscription":
            plan, _ = SubscriptionPlan.objects.get_or_create(tenant=tenant)
            plan.plan_name = (request.POST.get("plan_name") or "Local trial").strip()[:80]
            plan.status = request.POST.get("status") or SubscriptionPlan.STATUS_TRIAL
            try:
                plan.monthly_price = _decimal_or_none(request.POST.get("monthly_price")) or Decimal("0.00")
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("practice_client_detail", tenant_id=tenant.id)
            plan.currency = (request.POST.get("currency") or "GBP").strip().upper()[:3]
            provider = request.POST.get("billing_provider") or SubscriptionPlan.PROVIDER_MANUAL
            if provider not in dict(SubscriptionPlan.PROVIDER_CHOICES):
                provider = SubscriptionPlan.PROVIDER_MANUAL
            collection_method = request.POST.get("collection_method") or SubscriptionPlan.COLLECTION_DIRECT_DEBIT
            if collection_method not in dict(SubscriptionPlan.COLLECTION_CHOICES):
                collection_method = SubscriptionPlan.COLLECTION_DIRECT_DEBIT
            plan.billing_provider = provider
            plan.collection_method = collection_method
            plan.provider_customer_id = (request.POST.get("provider_customer_id") or "").strip()[:120]
            plan.provider_subscription_id = (request.POST.get("provider_subscription_id") or "").strip()[:120]
            try:
                plan.next_invoice_date = _date_or_none(request.POST.get("next_invoice_date"))
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("practice_client_detail", tenant_id=tenant.id)
            plan.billing_note = (request.POST.get("billing_note") or "").strip()
            plan.save()
            _record_audit_event(
                tenant,
                "SubscriptionUpdate",
                request.user.get_username(),
                f"Subscription set to {plan.plan_name} ({plan.status}).",
                {"plan_name": plan.plan_name, "status": plan.status, "monthly_price": str(plan.monthly_price)},
            )
            messages.success(request, "Subscription and billing status saved.")
        elif action in {"mark_invoice_sent", "record_manual_payment"}:
            plan, _ = SubscriptionPlan.objects.get_or_create(tenant=tenant)
            if action == "mark_invoice_sent":
                plan.latest_invoice_status = "Issued"
                if not plan.next_invoice_date:
                    plan.next_invoice_date = timezone.localdate() + timedelta(days=30)
                message = "Invoice marked as issued."
            else:
                plan.latest_invoice_status = "Paid"
                plan.last_payment_at = timezone.now()
                plan.status = SubscriptionPlan.STATUS_ACTIVE
                message = "Manual payment recorded."
            plan.save()
            _record_audit_event(
                tenant,
                "BillingAction",
                request.user.get_username(),
                message,
                {
                    "plan_name": plan.plan_name,
                    "provider": plan.billing_provider,
                    "collection_method": plan.collection_method,
                    "latest_invoice_status": plan.latest_invoice_status,
                },
            )
            messages.success(request, message)
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
            "gross_profit": _money(report["gross_profit"]),
            "gross_margin": report["gross_margin"],
            "net_margin": report["net_margin"],
            "cash_runway_months": report["cash_runway_months"],
            "vat_due": _money(report["vat_due"]),
            "latest_documents": EvidenceDocument.objects.filter(tenant=tenant).order_by("-uploaded_at")[:8],
            "latest_journals": Journal.objects.filter(tenant=tenant).order_by("-date", "-id")[:8],
            "vat_returns": VatReturn.objects.filter(tenant=tenant).order_by("-end_date")[:6],
            "client_requests": ClientRequest.objects.filter(tenant=tenant).order_by("-submitted_at")[:8],
            "client_invitations": ClientInvitation.objects.filter(tenant=tenant).order_by("-invited_at")[:8],
            "subscription": SubscriptionPlan.objects.filter(tenant=tenant).first(),
            "subscription_status_choices": SubscriptionPlan.STATUS_CHOICES,
            "billing_provider_choices": SubscriptionPlan.PROVIDER_CHOICES,
            "collection_method_choices": SubscriptionPlan.COLLECTION_CHOICES,
            "audit_events": AuditEvent.objects.filter(tenant=tenant).order_by("-timestamp")[:8],
            "unmatched_bank_transactions": unmatched_bank_transactions,
            "review_journals": review_journals,
            "hmrc_connection": HmrcVatConnection.objects.filter(tenant=tenant).first(),
            "accounts_workflow": _accounts_department_workflow(tenant),
            "operating_snapshot": _client_operating_snapshot(tenant, report),
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_accounts_production(request):
    """A read-only production register built from existing client records."""
    tenants, selected_tenant = _selected_tenant(request)
    if request.method == "POST":
        if not selected_tenant:
            messages.error(request, "Select a client before changing a production record.")
        else:
            action = request.POST.get("action")
            username = request.user.get_username() or "practice"
            if action == "release_approval_pack":
                approval = ClientApprovalRecord.objects.filter(
                    tenant=selected_tenant, id=request.POST.get("approval_id")
                ).first()
                if not approval:
                    messages.error(request, "Approval record was not found.")
                else:
                    try:
                        _event, created = release_approved_pack(approval, username)
                        messages.success(request, "Approval pack released to the client record." if created else "This approval pack was already released.")
                    except ValueError as exc:
                        messages.error(request, str(exc))
            elif action in {"start_task", "complete_task"}:
                task = AccountingTask.objects.filter(tenant=selected_tenant, id=request.POST.get("task_id")).first()
                if not task:
                    messages.error(request, "Practice task was not found.")
                else:
                    target = AccountingTask.STATUS_IN_PROGRESS if action == "start_task" else AccountingTask.STATUS_DONE
                    try:
                        transition_task(task, target, username)
                        messages.success(request, f"Task moved to {target}.")
                    except ValueError as exc:
                        messages.error(request, str(exc))
        suffix = f"?company={selected_tenant.id}" if selected_tenant else ""
        return redirect(f"{request.path}{suffix}")
    return render(
        request,
        "accounting/practice_accounts_production.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "production": accounts_production_snapshot(selected_tenant) if selected_tenant else None,
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_period_end(request):
    tenants, selected_tenant = _selected_tenant(request)
    period_start = _date_or_none(request.GET.get("period_start"))
    period_end = _date_or_none(request.GET.get("period_end"))
    if request.method == "POST":
        period_start = _date_or_none(request.POST.get("period_start"))
        period_end = _date_or_none(request.POST.get("period_end"))
        if not selected_tenant or not period_start or not period_end:
            messages.error(request, "Select a client and enter both period dates.")
        else:
            username = request.user.get_username() or "practice"
            try:
                with tenant_context(selected_tenant.id):
                    if request.POST.get("action") == "post_schedules":
                        result = post_period_end_schedules(
                            selected_tenant, period_start, period_end, username,
                            accrual_amount=request.POST.get("accrual_amount") or "0",
                            prepayment_amount=request.POST.get("prepayment_amount") or "0",
                        )
                        messages.success(request, f"Period-end schedules processed: {len(result['created'])} new posting(s).")
                    elif request.POST.get("action") == "close_period":
                        close_period_end(
                            selected_tenant,
                            period_start,
                            period_end,
                            username,
                            payroll_not_applicable=request.POST.get("payroll_not_applicable") == "on",
                        )
                        messages.success(request, "Period closed and locked.")
            except (ValueError, InvalidOperation) as exc:
                messages.error(request, str(exc))
        query = f"?company={selected_tenant.id}&period_start={period_start or ''}&period_end={period_end or ''}" if selected_tenant else ""
        return redirect(f"{request.path}{query}")
    controls = period_end_control_status(selected_tenant, period_start, period_end) if selected_tenant and period_start and period_end else None
    return render(request, "accounting/practice_period_end.html", {
        "tenants": tenants, "selected_tenant": selected_tenant, "period_start": period_start,
        "period_end": period_end, "controls": controls,
    })


@login_required(login_url="/login/")
@practice_staff_required
def practice_payroll_review(request):
    """Import a validated payroll export and retain an auditable period summary."""
    tenants, selected_tenant = _selected_tenant(request)
    if request.method == "POST":
        payroll_file = request.FILES.get("payroll_file")
        if not selected_tenant:
            messages.error(request, "Select a client before posting payroll.")
        elif not payroll_file or not payroll_file.name.lower().endswith(".csv"):
            messages.error(request, "Upload a payroll CSV file.")
        elif payroll_file.size > 5 * 1024 * 1024:
            messages.error(request, "Payroll CSV exceeds the 5 MB processing limit.")
        else:
            try:
                period_start = _date_or_none(request.POST.get("period_start"))
                period_end = _date_or_none(request.POST.get("period_end"))
                if not period_start or not period_end:
                    raise ValueError("Enter both payroll period dates.")
                csv_content = payroll_file.read().decode("utf-8-sig")
                with tenant_context(selected_tenant.id):
                    summary, journal = post_payroll_period(
                        selected_tenant, csv_content, period_start, period_end,
                        request.user.get_username() or "practice",
                    )
                    _record_audit_event(
                        selected_tenant, "PayrollPosted", request.user.get_username(),
                        f"Payroll for {period_start} to {period_end} posted to journal {journal.id}.",
                        {"journal_id": journal.id, "period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
                    )
                messages.success(request, f"Payroll posted to journal {journal.id}; gross pay GBP {summary.gross_pay:,.2f}.")
            except UnicodeDecodeError:
                messages.error(request, "Payroll CSV must use UTF-8 text encoding.")
            except ValueError as exc:
                messages.error(request, str(exc))
        suffix = f"?company={selected_tenant.id}" if selected_tenant else ""
        return redirect(f"{request.path}{suffix}")

    summaries = PayrollSummary.objects.filter(tenant=selected_tenant).order_by("-period_end")[:24] if selected_tenant else []
    return render(request, "accounting/practice_payroll_review.html", {
        "tenants": tenants, "selected_tenant": selected_tenant, "summaries": summaries,
    })


@login_required(login_url="/login/")
@practice_staff_required
def practice_operations_timeline(request):
    """Show a filterable, tenant-scoped history of immutable control events."""
    tenants, selected_tenant = _selected_tenant(request)
    if not selected_tenant:
        messages.info(request, "Create a client before reviewing operational history.")
        return redirect("practice_dashboard")

    event_type = (request.GET.get("event_type") or "").strip()
    date_from = _date_or_none(request.GET.get("from"))
    date_to = _date_or_none(request.GET.get("to"))
    if date_from and date_to and date_from > date_to:
        messages.error(request, "The start date must be before the end date.")
        date_from = date_to = None

    events = AuditEvent.objects.filter(tenant=selected_tenant).order_by("-timestamp", "-id")
    if event_type:
        events = events.filter(event_type=event_type)
    if date_from:
        events = events.filter(timestamp__date__gte=date_from)
    if date_to:
        events = events.filter(timestamp__date__lte=date_to)

    event_types = (
        AuditEvent.objects.filter(tenant=selected_tenant)
        .values_list("event_type", flat=True)
        .distinct()
        .order_by("event_type")
    )
    return render(
        request,
        "accounting/practice_operations_timeline.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "events": events[:200],
            "event_types": event_types,
            "selected_event_type": event_type,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_exception_register(request):
    tenants, selected_tenant = _selected_tenant(request)
    if not selected_tenant:
        messages.info(request, "Create a client before reviewing accounting exceptions.")
        return redirect("practice_dashboard")
    exceptions = exception_register(selected_tenant)
    return render(
        request,
        "accounting/practice_exception_register.html",
        {"tenants": tenants, "selected_tenant": selected_tenant, "exceptions": exceptions},
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_accounts_department(request):
    tenants = list(Tenant.objects.order_by("name"))
    requested_tenant = request.GET.get("company") or request.POST.get("company")
    selected_tenant = None
    if requested_tenant:
        selected_tenant = next((tenant for tenant in tenants if str(tenant.id) == requested_tenant), None)
    if selected_tenant is None and tenants:
        selected_tenant = tenants[0]

    if request.method == "POST":
        action = request.POST.get("action")
        if not selected_tenant:
            messages.error(request, "Create or select a client before building the local accounts department suite.")
            return redirect("practice_accounts_department")
        if action == "build_local_suite":
            snapshot = build_local_accounts_department_suite(
                selected_tenant,
                request.user.get_username() or "practice",
            )
            messages.success(
                request,
                f"Local accounts department suite refreshed: {snapshot['passed_count']} of {snapshot['total_count']} phases have local working records.",
            )
        elif action == "record_invoice_receipt":
            invoice = SalesInvoice.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("invoice_id"),
            ).first()
            if not invoice:
                messages.error(request, "Sales invoice was not found.")
            else:
                try:
                    _, updated_invoice = record_sales_receipt(
                        invoice,
                        request.POST.get("receipt_amount", ""),
                        request.POST.get("receipt_reference", ""),
                        request.user.get_username() or "practice",
                    )
                    if updated_invoice.status == SalesInvoice.STATUS_PAID:
                        AccountingTask.objects.filter(
                            tenant=selected_tenant,
                            title__icontains="overdue customer invoice",
                        ).update(status=AccountingTask.STATUS_DONE, completed_at=timezone.now())
                    messages.success(
                        request,
                        f"Receipt recorded for {invoice.invoice_number}; status is {updated_invoice.get_status_display()}.",
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
        elif action == "approve_purchase_bill":
            bill = PurchaseBill.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("bill_id"),
            ).first()
            if not bill:
                messages.error(request, "Purchase bill was not found.")
            else:
                bill.status = PurchaseBill.STATUS_APPROVED
                bill.approval_note = "Approved from the local accounts department workspace."
                bill.save(update_fields=["status", "approval_note", "updated_at"])
                _record_audit_event(
                    selected_tenant,
                    "PurchaseApproval",
                    request.user.get_username(),
                    f"Bill {bill.bill_number} approved locally.",
                    {"bill_id": bill.id, "bill_number": bill.bill_number},
                )
                messages.success(request, f"{bill.bill_number} approved locally.")
        elif action == "mark_payment_run_paid":
            payment_run = SupplierPaymentRun.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("payment_run_id"),
            ).first()
            if not payment_run:
                messages.error(request, "Payment run was not found.")
            else:
                try:
                    mark_supplier_payment_run_paid(
                        payment_run,
                        request.user.get_username() or "practice",
                        request.POST.get("payment_reference", ""),
                    )
                    messages.success(
                        request,
                        f"{payment_run.run_reference} confirmed against its linked supplier bills.",
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
        elif action in {"start_task", "complete_task"}:
            task = AccountingTask.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("task_id"),
            ).first()
            if not task:
                messages.error(request, "Task was not found.")
            else:
                target = AccountingTask.STATUS_IN_PROGRESS if action == "start_task" else AccountingTask.STATUS_DONE
                try:
                    transition_task(task, target, request.user.get_username() or "practice")
                    messages.success(request, f"Task moved to {target}.")
                except ValueError as exc:
                    messages.error(request, str(exc))
        elif action == "review_notification_preview":
            notification = NotificationEvent.objects.filter(
                tenant=selected_tenant,
                id=request.POST.get("notification_id"),
            ).first()
            if not notification:
                messages.error(request, "Notification event was not found.")
            else:
                created = record_notification_preview(
                    notification,
                    request.user.get_username() or "practice",
                )
                messages.success(
                    request,
                    (
                        "Notification preview reviewed. Delivery remains queued until a provider confirms it."
                        if created
                        else "This notification preview was already reviewed; delivery remains unchanged."
                    ),
                )
        return redirect(f"{request.path}?company={selected_tenant.id}")

    snapshot = accounts_department_snapshot(selected_tenant) if selected_tenant else None
    suite_context = {}
    if selected_tenant:
        suite_context = {
            "sales_quotes": SalesQuote.objects.filter(tenant=selected_tenant).order_by("-issue_date", "quote_number")[:6],
            "sales_invoices": SalesInvoice.objects.filter(tenant=selected_tenant).order_by("due_date", "invoice_number")[:12],
            "purchase_orders": PurchaseOrder.objects.filter(tenant=selected_tenant).order_by("-order_date", "order_number")[:6],
            "purchase_bills": PurchaseBill.objects.filter(tenant=selected_tenant).order_by("due_date", "bill_number")[:12],
            "payment_runs": SupplierPaymentRun.objects.filter(tenant=selected_tenant).order_by("scheduled_date")[:6],
            "bank_rules": BankRule.objects.filter(tenant=selected_tenant).order_by("name")[:8],
            "month_end_closes": MonthEndClose.objects.filter(tenant=selected_tenant).order_by("-period_end")[:4],
            "period_locks": AccountingPeriodLock.objects.filter(tenant=selected_tenant).order_by("-period_end")[:4],
            "fixed_assets": FixedAsset.objects.filter(tenant=selected_tenant).order_by("asset_name")[:8],
            "payroll_summaries": PayrollSummary.objects.filter(tenant=selected_tenant).order_by("-period_end")[:4],
            "tax_estimates": CorporationTaxEstimate.objects.filter(tenant=selected_tenant).order_by("-period_end")[:4],
            "statutory_drafts": StatutoryAccountsDraft.objects.filter(tenant=selected_tenant).order_by("-period_end")[:4],
            "pack_sections": ManagementPackSection.objects.filter(tenant=selected_tenant).order_by("-period_end", "section_name")[:6],
            "document_rules": DocumentIntelligenceRule.objects.filter(tenant=selected_tenant).order_by("name")[:6],
            "accounting_tasks": AccountingTask.objects.filter(tenant=selected_tenant).order_by("status", "-priority", "due_date")[:12],
            "notifications": NotificationEvent.objects.filter(tenant=selected_tenant).order_by("-created_at")[:6],
            "sales_balance_display": _money(snapshot["sales_balance"] if snapshot else Decimal("0")),
            "purchase_balance_display": _money(snapshot["purchase_balance"] if snapshot else Decimal("0")),
            "fixed_asset_nbv_display": _money(snapshot["fixed_asset_nbv"] if snapshot else Decimal("0")),
        }
    return render(
        request,
        "accounting/practice_accounts_department.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "snapshot": snapshot,
            **suite_context,
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
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
    for bank_line in unmatched_bank_transactions:
        suggestion = _bank_rule_suggestion(bank_line)
        bank_line.suggested_bank_rule = suggestion["rule"]
        bank_line.suggested_account = suggestion["account"]
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
@practice_staff_required
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
@practice_staff_required
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
        if action not in {"update_evidence_review", "analyse_evidence", "post_evidence_journal"} or not document:
            messages.error(request, "Evidence document was not found.")
        elif action == "analyse_evidence":
            suggestions = _extract_evidence_suggestions(document)
            for field, value in suggestions.items():
                if value not in {None, ""}:
                    setattr(document, field, value)
            document.review_note = (document.review_note + "\n" if document.review_note else "") + "Local document intelligence populated suggested fields."
            document.save(update_fields=[
                "document_category",
                "supplier_or_customer",
                "document_date",
                "gross_amount",
                "vat_amount",
                "suggested_account_code",
                "review_note",
            ])
            _record_audit_event(
                document.tenant,
                "EvidenceAnalysis",
                request.user.get_username(),
                f"Evidence document {document.id} analysed locally.",
                {"document_id": document.id, "document_category": document.document_category},
            )
            messages.success(request, "Document intelligence suggestions were applied.")
        elif action == "post_evidence_journal":
            username = request.user.get_username() or "practice"
            journal, created = _create_evidence_review_journal(document, username)
            document.review_status = "ReadyForPosting"
            document.reviewed_at = timezone.now()
            document.reviewed_by = username
            document.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
            _record_audit_event(
                document.tenant,
                "EvidencePosting",
                username,
                f"Evidence document {document.id} posted to journal {journal.id}.",
                {"document_id": document.id, "journal_id": journal.id, "created": created},
            )
            messages.success(request, f"Evidence linked to journal {journal.id}.")
        elif status not in valid_statuses:
            messages.error(request, "Choose a valid evidence review status.")
        else:
            username = request.user.get_username() or "practice"
            journal = None
            try:
                document.document_date = _date_or_none(request.POST.get("document_date"))
                document.gross_amount = _decimal_or_none(request.POST.get("gross_amount"))
                document.vat_amount = _decimal_or_none(request.POST.get("vat_amount"))
            except ValueError as exc:
                messages.error(request, str(exc))
                redirect_url = request.path
                if request.POST.get("company"):
                    redirect_url = f"{redirect_url}?company={request.POST.get('company')}"
                return redirect(redirect_url)
            document.review_status = status
            document.document_category = request.POST.get("document_category") or document.document_category
            document.supplier_or_customer = (request.POST.get("supplier_or_customer") or "").strip()[:160]
            document.suggested_account_code = (request.POST.get("suggested_account_code") or "").strip()[:10]
            document.review_note = (request.POST.get("review_note") or "").strip()
            if status == "ReadyForPosting":
                journal, created = _create_evidence_review_journal(document, username)
            if status == "Unreviewed":
                document.reviewed_at = None
                document.reviewed_by = ""
            else:
                document.reviewed_at = timezone.now()
                document.reviewed_by = username
            document.save(update_fields=[
                "review_status",
                "reviewed_at",
                "reviewed_by",
                "document_category",
                "supplier_or_customer",
                "document_date",
                "gross_amount",
                "vat_amount",
                "suggested_account_code",
                "review_note",
            ])
            _record_audit_event(
                document.tenant,
                "EvidenceReview",
                username,
                f"Evidence document {document.id} marked {status}.",
                {
                    "document_id": document.id,
                    "review_status": status,
                    "journal_id": journal.id if journal else None,
                    "document_category": document.document_category,
                    "gross_amount": str(document.gross_amount) if document.gross_amount is not None else "",
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
            "category_choices": EvidenceDocument.CATEGORY_CHOICES,
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_evidence_detail(request, document_id):
    document = EvidenceDocument.objects.select_related("tenant").filter(id=document_id).first()
    if not document:
        raise Http404("Evidence document not found")
    if request.method == "POST":
        action = request.POST.get("action")
        username = request.user.get_username() or "practice"
        if action == "analyse_evidence":
            suggestions = _extract_evidence_suggestions(document)
            for field, value in suggestions.items():
                if value not in {None, ""}:
                    setattr(document, field, value)
            document.review_note = (document.review_note + "\n" if document.review_note else "") + "Local document intelligence populated suggested fields."
            document.save(update_fields=[
                "document_category",
                "supplier_or_customer",
                "document_date",
                "gross_amount",
                "vat_amount",
                "suggested_account_code",
                "review_note",
            ])
            _record_audit_event(
                document.tenant,
                "EvidenceAnalysis",
                username,
                f"Evidence document {document.id} analysed locally.",
                {"document_id": document.id, "document_category": document.document_category},
            )
            messages.success(request, "Document intelligence suggestions were applied.")
        elif action == "post_evidence_journal":
            journal, created = _create_evidence_review_journal(document, username)
            document.review_status = "ReadyForPosting"
            document.reviewed_at = timezone.now()
            document.reviewed_by = username
            document.save(update_fields=["review_status", "reviewed_at", "reviewed_by"])
            _record_audit_event(
                document.tenant,
                "EvidencePosting",
                username,
                f"Evidence document {document.id} posted to journal {journal.id}.",
                {"document_id": document.id, "journal_id": journal.id, "created": created},
            )
            messages.success(request, f"Evidence linked to journal {journal.id}.")
        return redirect("practice_evidence_detail", document_id=document.id)
    linked_journals = Journal.objects.filter(evidence_links__document=document).order_by("-date", "-id")
    audit_events = AuditEvent.objects.filter(
        tenant=document.tenant,
        details__document_id=document.id,
    ).order_by("-timestamp")[:10]
    return render(
        request,
        "accounting/practice_evidence_detail.html",
        {
            "document": document,
            "linked_journals": linked_journals,
            "audit_events": audit_events,
            "category_choices": EvidenceDocument.CATEGORY_CHOICES,
            "is_pdf": document.content_type == "application/pdf",
            "is_image": document.content_type.startswith("image/"),
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def practice_evidence_file(request, document_id):
    document = EvidenceDocument.objects.filter(id=document_id).first()
    if not document:
        raise Http404("Evidence document not found")
    disposition = "inline" if request.GET.get("download") != "1" else "attachment"
    response = HttpResponse(bytes(document.file_content), content_type=document.content_type or "application/octet-stream")
    response["Content-Disposition"] = f'{disposition}; filename="{document.filename}"'
    return response


@login_required(login_url="/login/")
@practice_staff_required
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
    workflow_summary = [
        {
            "label": "Client uploads",
            "count": upload_inbox.count() if hasattr(upload_inbox, "count") else len(upload_inbox),
            "detail": "New evidence waiting for review",
            "href": "practice_evidence_review",
        },
        {
            "label": "Bank matching",
            "count": unreconciled_count,
            "detail": "Transactions not yet reconciled",
            "href": "practice_banking_review",
        },
        {
            "label": "Ledger review",
            "count": Journal.objects.filter(status="RequiresReview").count(),
            "detail": "Journals requiring accountant approval",
            "href": "practice_ledger_review",
        },
        {
            "label": "Client questions",
            "count": open_client_requests_count,
            "detail": "Open advice or information requests",
            "href": "practice_clients",
        },
        {
            "label": "Client approvals",
            "count": awaiting_client_vat_count,
            "detail": "Returns waiting on clients",
            "href": "hmrc_vat_workspace",
        },
        {
            "label": "Statutory filing",
            "count": ready_to_file_vat_count,
            "detail": "Client-approved returns ready to file",
            "href": "hmrc_vat_workspace",
        },
    ]

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
        "workflow_summary": workflow_summary,
        "hmrc_status": hmrc_sandbox_status(),
    }
    return render(request, "accounting/dashboard.html", context)


def _launch_readiness_sections():
    hmrc_status = hmrc_sandbox_status()
    ch_status = companies_house_status()
    has_subscription_provider = SubscriptionPlan.objects.exclude(billing_provider=SubscriptionPlan.PROVIDER_MANUAL).exists()
    has_accepted_invite = ClientInvitation.objects.filter(status=ClientInvitation.STATUS_ACCEPTED).exists()
    has_review_journals = Journal.objects.filter(status="RequiresReview").exists()
    has_reports = Journal.objects.exists()
    data_counts = {
        "clients": Tenant.objects.count(),
        "documents": EvidenceDocument.objects.count(),
        "bank_lines": BankTransaction.objects.count(),
        "journals": Journal.objects.count(),
        "questions": ClientRequest.objects.exclude(status="Resolved").count(),
    }

    return [
        {
            "title": "Customer and Legal Pack",
            "items": [
                {"label": "Public privacy notice", "passed": True, "detail": "Available at /privacy/."},
                {"label": "Public service terms", "passed": True, "detail": "Available at /terms/."},
                {"label": "Security contact route", "passed": True, "detail": "info@kafs-ltd.com is shown in policy documents."},
                {"label": "Final legal review", "passed": False, "detail": "External legal/commercial sign-off is still required before paid public launch."},
            ],
        },
        {
            "title": "Product Workflow",
            "items": [
                {"label": "Client records", "passed": data_counts["clients"] > 0, "detail": f"{data_counts['clients']} client record(s) exist."},
                {"label": "Client invite acceptance", "passed": has_accepted_invite, "detail": "At least one accepted invite is required before public onboarding can be considered proven."},
                {"label": "Evidence and document intake", "passed": data_counts["documents"] > 0, "detail": f"{data_counts['documents']} document(s) stored locally."},
                {"label": "Bookkeeping review queue", "passed": has_review_journals, "detail": "Evidence and ledger journals can be held for accountant approval."},
                {"label": "Management reports", "passed": has_reports, "detail": "Reports generate from current ledger data."},
            ],
        },
        {
            "title": "Billing and Subscriptions",
            "items": [
                {"label": "Local subscription records", "passed": SubscriptionPlan.objects.exists(), "detail": "Plan/status/provider data can be tracked locally."},
                {"label": "Provider abstraction", "passed": True, "detail": "Stripe, GoCardless and manual collection are modelled without live API calls."},
                {"label": "Live payment keys", "passed": has_subscription_provider, "detail": "Live Stripe/GoCardless credentials and webhooks are still external setup items."},
            ],
        },
        {
            "title": "Government Integrations",
            "items": [
                {"label": "HMRC local configuration", "passed": bool(hmrc_status.get("configured")), "detail": "HMRC sandbox/local credentials are detected when configured."},
                {"label": "HMRC production approval", "passed": False, "detail": "Requires HMRC approval and live client OAuth authorisation."},
                {"label": "Companies House public API", "passed": bool(ch_status.get("configured")), "detail": "Public company-data lookup works when API key is configured."},
                {"label": "Companies House filing access", "passed": bool(ch_status.get("filing_enabled")), "detail": ch_status.get("filing_detail") or "Submission/filing access requires the correct external Companies House route."},
            ],
        },
        {
            "title": "Deployment",
            "items": [
                {"label": "PostgreSQL backend", "passed": connection.vendor == "postgresql", "detail": f"Current database backend: {connection.vendor}."},
                {"label": "Production DEBUG off", "passed": not settings.DEBUG, "detail": "DEBUG must be False in production."},
                {"label": "HTTPS/DNS live", "passed": False, "detail": "Public deployment is intentionally paused to control cost."},
                {"label": "Restricted DB role", "passed": False, "detail": "Use deploy/create_app_role.sql for production runtime."},
            ],
        },
    ]


@login_required(login_url="/login/")
@practice_staff_required
def launch_readiness(request):
    sections = _launch_readiness_sections()
    passed = sum(1 for section in sections for item in section["items"] if item["passed"])
    total = sum(len(section["items"]) for section in sections)
    blockers = [item for section in sections for item in section["items"] if not item["passed"]]
    return render(
        request,
        "accounting/launch_readiness.html",
        {
            "sections": sections,
            "passed": passed,
            "total": total,
            "blockers": blockers,
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
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
@practice_staff_required
def hmrc_services_workspace(request):
    tenants, selected_tenant = _selected_tenant(request)
    approvals = ensure_hmrc_service_approvals()
    profile = None
    if selected_tenant:
        profile, _ = HmrcTaxProfile.objects.get_or_create(tenant=selected_tenant)

    if request.method == "POST":
        if not selected_tenant:
            messages.error(request, "Choose a client before preparing an HMRC filing case.")
            return redirect("hmrc_services_workspace")

        action = request.POST.get("action")
        if action == "save_tax_profile":
            field_labels = {
                "corporation_tax_utr": "Corporation Tax UTR",
                "company_number": "company number",
                "paye_reference": "PAYE reference",
                "accounts_office_reference": "Accounts Office reference",
                "cis_utr": "CIS UTR",
                "self_assessment_utr": "Self Assessment UTR",
                "national_insurance_number": "National Insurance number",
                "income_tax_business_id": "Income Tax business ID",
            }
            changed = []
            validation_errors = []
            for field, label in field_labels.items():
                value = (request.POST.get(field) or "").strip().upper()
                if not value:
                    continue
                if field in {"corporation_tax_utr", "cis_utr", "self_assessment_utr"} and not re.fullmatch(r"\d{10}", value):
                    validation_errors.append(f"{label} must contain exactly 10 digits.")
                    continue
                if field == "company_number" and not re.fullmatch(r"[A-Z0-9]{8}", value):
                    validation_errors.append("Company number must contain exactly 8 letters or digits.")
                    continue
                setattr(profile, field, value)
                changed.append(field)
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
            elif changed:
                profile.save(update_fields=[*changed, "updated_at"])
                messages.success(request, "Encrypted HMRC tax references updated for this client.")
            else:
                messages.info(request, "No HMRC tax references were changed.")
        elif action == "prepare_ct600":
            estimate = CorporationTaxEstimate.objects.filter(tenant=selected_tenant).order_by("-period_end").first()
            accounts = StatutoryAccountsDraft.objects.filter(tenant=selected_tenant).order_by("-period_end").first()
            if not estimate or not accounts:
                messages.error(request, "Prepare both a Corporation Tax estimate and statutory accounts before CT600 preflight.")
            else:
                case = HmrcFilingCase.objects.create(
                    tenant=selected_tenant,
                    service=HmrcServiceApproval.SERVICE_CORPORATION_TAX,
                    filing_type="CT600",
                    period_start=estimate.period_start,
                    period_end=estimate.period_end,
                )
                set_case_payload(
                    case,
                    {
                        "company_tax_reference": profile.corporation_tax_utr,
                        "company_number": profile.company_number,
                        "accounting_period_start": estimate.period_start.isoformat(),
                        "accounting_period_end": estimate.period_end.isoformat(),
                        "taxable_profit": str(estimate.taxable_profit),
                        "corporation_tax_due": str(estimate.estimated_tax),
                        "accounts_ixbrl_ready": accounts.ixbrl_ready,
                        "computations_ixbrl_ready": False,
                    },
                )
                case.save(update_fields=["encrypted_payload", "updated_at"])
                case = run_hmrc_filing_preflight(case)
                messages.success(request, f"CT600 preparation case created with {len(case.validation_errors)} blocker(s).")
        elif action == "prepare_fps":
            payroll = PayrollSummary.objects.filter(tenant=selected_tenant).order_by("-period_end").first()
            if not payroll:
                messages.error(request, "Post a payroll period before preparing an FPS case.")
            else:
                case = HmrcFilingCase.objects.create(
                    tenant=selected_tenant,
                    service=HmrcServiceApproval.SERVICE_PAYE_RTI,
                    filing_type="FPS",
                    period_start=payroll.period_start,
                    period_end=payroll.period_end,
                )
                set_case_payload(
                    case,
                    {
                        "paye_reference": profile.paye_reference,
                        "accounts_office_reference": profile.accounts_office_reference,
                        "payment_date": payroll.period_end.isoformat(),
                        "employees": [],
                        "summary": {
                            "gross_pay": str(payroll.gross_pay),
                            "paye": str(payroll.paye),
                            "employee_ni": str(payroll.employee_ni),
                            "employer_ni": str(payroll.employer_ni),
                        },
                    },
                )
                case.save(update_fields=["encrypted_payload", "updated_at"])
                case = run_hmrc_filing_preflight(case)
                messages.success(request, f"FPS preparation case created with {len(case.validation_errors)} blocker(s).")
        elif action in {
            "prepare_eps", "prepare_cis", "prepare_itsa", "prepare_itsa_annual",
            "prepare_sa100", "prepare_sa800", "prepare_sa900",
        }:
            today = timezone.localdate()
            tax_year_start = today.year if (today.month, today.day) >= (4, 6) else today.year - 1
            tax_year = f"{tax_year_start}-{str(tax_year_start + 1)[-2:]}"
            period_start = date(tax_year_start, 4, 6)
            period_end = date(tax_year_start + 1, 4, 5)
            preparation = {
                "prepare_eps": (
                    HmrcServiceApproval.SERVICE_PAYE_RTI,
                    "EPS",
                    {
                        "paye_reference": profile.paye_reference,
                        "accounts_office_reference": profile.accounts_office_reference,
                        "tax_year": tax_year,
                        "tax_month": None,
                    },
                ),
                "prepare_cis": (
                    HmrcServiceApproval.SERVICE_CIS,
                    "CIS300",
                    {
                        "paye_reference": profile.paye_reference,
                        "tax_year": tax_year,
                        "tax_month": None,
                        "subcontractors": [],
                    },
                ),
                "prepare_itsa": (
                    HmrcServiceApproval.SERVICE_INCOME_TAX_MTD,
                    "QUARTERLY_UPDATE",
                    {
                        "nino": profile.national_insurance_number,
                        "business_id": profile.income_tax_business_id,
                        "tax_year": tax_year,
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "income": None,
                        "expenses": None,
                    },
                ),
                "prepare_itsa_annual": (
                    HmrcServiceApproval.SERVICE_INCOME_TAX_MTD,
                    "ANNUAL_SUMMARY",
                    {
                        "nino": profile.national_insurance_number,
                        "business_id": profile.income_tax_business_id,
                        "tax_year": tax_year,
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "income": None,
                        "expenses": None,
                    },
                ),
                "prepare_sa100": (
                    HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
                    "SA100",
                    {
                        "utr": profile.self_assessment_utr,
                        "tax_year": tax_year,
                        "declaration": False,
                    },
                ),
                "prepare_sa800": (
                    HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
                    "SA800",
                    {
                        "utr": profile.self_assessment_utr,
                        "tax_year": tax_year,
                        "declaration": False,
                    },
                ),
                "prepare_sa900": (
                    HmrcServiceApproval.SERVICE_SELF_ASSESSMENT,
                    "SA900",
                    {
                        "utr": profile.self_assessment_utr,
                        "tax_year": tax_year,
                        "declaration": False,
                    },
                ),
            }
            service, filing_type, payload = preparation[action]
            case = HmrcFilingCase.objects.create(
                tenant=selected_tenant,
                service=service,
                filing_type=filing_type,
                period_start=period_start,
                period_end=period_end,
            )
            set_case_payload(case, payload)
            case.save(update_fields=["encrypted_payload", "updated_at"])
            case = run_hmrc_filing_preflight(case)
            messages.success(
                request,
                f"{filing_type} preparation case created with {len(case.validation_errors)} blocker(s).",
            )
        elif action == "run_preflight":
            case = HmrcFilingCase.objects.filter(tenant=selected_tenant, id=request.POST.get("case_id")).first()
            if not case:
                messages.error(request, "Choose a valid HMRC filing case.")
            else:
                case = run_hmrc_filing_preflight(case)
                if case.validation_errors:
                    messages.error(request, f"Preflight found {len(case.validation_errors)} blocker(s).")
                else:
                    messages.success(request, "Local HMRC preflight passed; provider testing is still required.")
        return redirect(f"{request.path}?company={selected_tenant.id}")

    approval_by_service = {approval.service: approval for approval in approvals}
    service_rows = [
        {
            "definition": definition,
            "approval": approval_by_service[definition.code],
        }
        for definition in HMRC_SERVICES.values()
    ]
    filing_cases = (
        HmrcFilingCase.objects.filter(tenant=selected_tenant)[:20] if selected_tenant else []
    )
    return render(
        request,
        "accounting/hmrc_services_workspace.html",
        {
            "tenants": tenants,
            "selected_tenant": selected_tenant,
            "tax_profile": profile,
            "service_rows": service_rows,
            "filing_cases": filing_cases,
            "income_tax_api_requirements": income_tax_subscription_status(),
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def companies_house_workspace(request):
    status = companies_house_status()
    company_number = (request.GET.get("company_number") or request.POST.get("company_number") or "").strip()
    profile = None
    snapshot = None
    linked_tenant = None
    statutory_drafts = []
    filing_submissions = CompaniesHouseFilingSubmission.objects.select_related("tenant", "statutory_accounts").prefetch_related("poll_history")[:10]
    filing_submission_rows = [
        {
            "submission": submission,
            "actions": companies_house_rejection_actions(submission.validation_messages),
            "polls": list(submission.poll_history.all()[:3]),
        }
        for submission in filing_submissions
    ]
    scenario_summary = companies_house_scenario_summary()
    approval_gates = CompaniesHouseApprovalGate.objects.select_related("tenant", "statutory_accounts", "client_approval")[:10]
    next_local_build_items = companies_house_next_local_build_items()

    if request.method == "POST" and request.POST.get("action") == "build_local_scenarios":
        results = build_companies_house_local_scenarios(username=request.user.get_username() or "practice")
        failures = [result for result in results if not result.passed]
        if failures:
            messages.error(
                request,
                f"Built Companies House local scenarios, but {len(failures)} scenario(s) need review.",
            )
        else:
            messages.success(request, f"Built and validated {len(results)} local Companies House scenarios.")
        return redirect("companies_house_workspace")

    if request.method == "POST" and request.POST.get("action") == "poll_submission":
        submission_id = request.POST.get("submission_id")
        submission = CompaniesHouseFilingSubmission.objects.filter(id=submission_id).select_related("tenant").first()
        if not submission:
            messages.error(request, "Choose a valid Companies House submission to poll.")
        else:
            try:
                updated = poll_companies_house_submission_status(
                    submission,
                    username=request.user.get_username() or "practice",
                )
                messages.success(
                    request,
                    f"Submission {updated.submission_number:06d} status is now {updated.status}.",
                )
            except CompaniesHouseApiError as exc:
                messages.error(request, f"Companies House status polling failed: {exc}")
        return redirect("companies_house_workspace")

    if request.method == "POST" and request.POST.get("action") in {"assess_filing_gate", "practice_signoff"}:
        draft_id = request.POST.get("statutory_accounts_id")
        draft = StatutoryAccountsDraft.objects.filter(id=draft_id).select_related("tenant").first()
        if not draft:
            messages.error(request, "Choose a statutory accounts draft before assessing the filing gate.")
        else:
            gate = assess_companies_house_approval_gate(
                draft,
                username=request.user.get_username() or "practice",
                signoff=request.POST.get("action") == "practice_signoff",
            )
            if gate.status == gate.STATUS_BLOCKED:
                messages.warning(request, "Companies House filing gate is blocked: " + " ".join(gate.readiness_messages))
            elif gate.status == gate.STATUS_SIGNED_OFF:
                messages.success(request, "Practice signoff completed for the Companies House local filing gate.")
            else:
                messages.success(request, "Companies House filing gate is ready for practice signoff.")
            _record_audit_event(
                draft.tenant,
                "CompaniesHouseApprovalGateAssessed",
                request.user.get_username(),
                f"Companies House approval gate assessed as {gate.status}.",
                {
                    "draft_id": draft.id,
                    "status": gate.status,
                    "readiness_messages": gate.readiness_messages,
                    "practice_signed_off": gate.practice_signed_off,
                    "test_mode_only": gate.test_mode_only,
                },
            )
        return redirect("companies_house_workspace")

    if company_number:
        try:
            profile = retrieve_company_profile(company_number)
            snapshot = company_profile_snapshot(profile)
            linked_tenant = Tenant.objects.filter(name__iexact=snapshot["company_name"]).first()
            if linked_tenant:
                statutory_drafts = linked_tenant.statutory_accounts_drafts.order_by("-period_end", "-created_at")[:10]
        except ValueError as exc:
            messages.error(request, str(exc))
        except CompaniesHouseApiError as exc:
            if exc.status_code == 404:
                messages.error(request, "Companies House could not find that company number.")
            else:
                messages.error(request, f"Companies House lookup failed: {exc}")

    if request.method == "POST" and request.POST.get("action") == "create_client":
        if not snapshot:
            messages.error(request, "Lookup the company before creating a client record.")
        else:
            tenant, created = Tenant.objects.get_or_create(name=snapshot["company_name"])
            _ensure_default_nominals(tenant)
            _record_audit_event(
                tenant,
                "CompaniesHouseSync",
                request.user.get_username(),
                f"Companies House profile {'created' if created else 'matched'} for {snapshot['company_number']}.",
                {
                    "company_number": snapshot["company_number"],
                    "company_status": snapshot["company_status"],
                    "accounts_next_due": snapshot["accounts_next_due"],
                    "confirmation_next_due": snapshot["confirmation_next_due"],
                },
            )
            messages.success(
                request,
                f"{'Created' if created else 'Matched'} LedgerHouse client record for {tenant.name}.",
            )
            return redirect("practice_client_detail", tenant_id=tenant.id)

    if request.method == "POST" and request.POST.get("action") in {"validate_ixbrl", "prepare_test_submission", "send_test_submission"}:
        action = request.POST.get("action")
        draft_id = request.POST.get("statutory_accounts_id")
        company_authentication_code = (request.POST.get("company_authentication_code") or "TEST12").strip().upper()
        draft = StatutoryAccountsDraft.objects.filter(id=draft_id).select_related("tenant").first()
        if not snapshot:
            messages.error(request, "Lookup the company before preparing Companies House accounts filing data.")
        elif not draft:
            messages.error(request, "Choose a statutory accounts draft for this client.")
        elif draft.tenant != linked_tenant:
            messages.error(request, "The selected accounts draft does not belong to this Companies House client.")
        elif not re.fullmatch(r"[A-Z0-9]{6,8}", company_authentication_code):
            messages.error(request, "Company authentication code must be 6 to 8 letters or numbers.")
        elif action == "validate_ixbrl":
            ixbrl_text = generate_micro_entity_ixbrl(draft, snapshot["company_number"], snapshot["company_name"])
            validation = validate_micro_entity_ixbrl(ixbrl_text, draft, snapshot["company_number"])
            draft.ixbrl_ready = validation.passed
            if validation.passed and draft.locally_complete:
                draft.status = StatutoryAccountsDraft.STATUS_READY_FOR_FILING
            draft.save(update_fields=["ixbrl_ready", "status"])
            _record_audit_event(
                draft.tenant,
                "CompaniesHouseIxbrlValidated",
                request.user.get_username(),
                f"Companies House iXBRL validation {'passed' if validation.passed else 'failed'}.",
                {
                    "company_number": snapshot["company_number"],
                    "period_end": str(draft.period_end),
                    "message_count": len(validation.messages),
                },
            )
            if validation.passed:
                messages.success(request, "Generated XHTML/iXBRL accounts passed local validation and the draft is marked iXBRL-ready.")
            else:
                messages.error(request, "Generated iXBRL failed validation: " + " ".join(validation.messages))
        elif action == "prepare_test_submission":
            try:
                prepared = prepare_companies_house_test_submission(
                    draft,
                    snapshot["company_number"],
                    snapshot["company_name"],
                    company_authentication_code,
                    created_by=request.user.get_username() or "practice",
                )
                _record_audit_event(
                    draft.tenant,
                    "CompaniesHouseTestSubmissionPrepared",
                    request.user.get_username(),
                    f"Companies House test submission {prepared.submission_number:06d} prepared.",
                    {
                        "submission_number": f"{prepared.submission_number:06d}",
                        "company_number": prepared.company_number,
                        "status": prepared.status,
                        "readiness_blockers": prepared.validation_messages,
                    },
                )
                if prepared.validation_messages:
                    messages.warning(
                        request,
                        "Test package prepared but gateway send remains blocked: "
                        + " ".join(prepared.validation_messages),
                    )
                else:
                    messages.success(
                        request,
                        f"Companies House test package {prepared.submission_number:06d} prepared and ready for gateway send.",
                    )
            except (ValueError, CompaniesHouseApiError) as exc:
                messages.error(request, f"Companies House test preparation failed: {exc}")
        else:
            try:
                submitted = submit_companies_house_test_submission(
                    draft,
                    snapshot["company_number"],
                    snapshot["company_name"],
                    company_authentication_code,
                    created_by=request.user.get_username() or "practice",
                )
                _record_audit_event(
                    draft.tenant,
                    "CompaniesHouseTestSubmissionSent",
                    request.user.get_username(),
                    f"Companies House test submission {submitted.submission_number:06d} gateway status {submitted.status}.",
                    {
                        "submission_number": f"{submitted.submission_number:06d}",
                        "company_number": submitted.company_number,
                        "status": submitted.status,
                        "message_count": len(submitted.validation_messages),
                    },
                )
                if submitted.status in {submitted.STATUS_SUBMITTED, submitted.STATUS_PENDING, submitted.STATUS_ACCEPTED}:
                    messages.success(
                        request,
                        f"Companies House XML Gateway test submission {submitted.submission_number:06d} sent. Status: {submitted.status}.",
                    )
                else:
                    messages.error(
                        request,
                        f"Companies House XML Gateway test submission {submitted.submission_number:06d} did not pass. "
                        + " ".join(submitted.validation_messages),
                    )
            except (ValueError, CompaniesHouseApiError) as exc:
                messages.error(request, f"Companies House test gateway send failed: {exc}")
        return redirect(f"{request.path}?company_number={company_number}")

    return render(
        request,
        "accounting/companies_house_workspace.html",
        {
            "companies_house_status": status,
            "company_number": company_number,
            "snapshot": snapshot,
            "linked_tenant": linked_tenant,
            "statutory_drafts": statutory_drafts,
            "filing_submissions": filing_submissions,
            "filing_submission_rows": filing_submission_rows,
            "scenario_summary": scenario_summary,
            "approval_gates": approval_gates,
            "next_local_build_items": next_local_build_items,
            "initial_filing_scope": companies_house_initial_filing_scope(),
        },
    )


@login_required(login_url="/login/")
@practice_staff_required
def companies_house_accounts_preview(request, draft_id):
    """Render generated XHTML/iXBRL for mandatory human review before sending."""
    draft = StatutoryAccountsDraft.objects.select_related("tenant").filter(id=draft_id).first()
    if not draft:
        raise Http404("Statutory accounts draft not found.")
    try:
        company_number = normalise_company_number(request.GET.get("company_number") or "00000006")
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    document = generate_micro_entity_ixbrl(draft, company_number, draft.tenant.name)
    response = HttpResponse(document, content_type="application/xhtml+xml; charset=utf-8")
    response["Content-Disposition"] = f'inline; filename="ledgerhouse-{draft.id}-accounts.xhtml"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required(login_url="/login/")
@practice_staff_required
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
                        fraud_headers=_hmrc_web_fraud_headers(request, selected_tenant),
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
            elif VatReturn.objects.filter(
                tenant=selected_tenant,
                period_key=period_key,
                status="Submitted",
            ).exists():
                messages.error(
                    request,
                    "A submission is already recorded for this VAT period. No new HMRC request was sent.",
                )
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
                        fraud_headers=_hmrc_web_fraud_headers(request, selected_tenant),
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
                            fraud_headers=_hmrc_web_fraud_headers(request, selected_tenant),
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
@practice_staff_required
def hmrc_authorise(request):
    requested_next = request.GET.get("next") or reverse("hmrc_sandbox_status")
    next_url = (
        requested_next
        if url_has_allowed_host_and_scheme(
            requested_next,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
        and requested_next.startswith("/")
        and not requested_next.startswith("//")
        else reverse("hmrc_sandbox_status")
    )
    try:
        authorisation_url = build_hmrc_authorisation_url(next_url)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("hmrc_sandbox_status")
    state = (parse_qs(urlparse(authorisation_url).query).get("state") or [""])[0]
    request.session["hmrc_oauth_state"] = state
    return redirect(authorisation_url)


@login_required(login_url="/login/")
@practice_staff_required
def hmrc_callback(request):
    state = request.GET.get("state") or ""
    expected_state = request.session.pop("hmrc_oauth_state", "")
    if not state or not expected_state or not hmac.compare_digest(state, expected_state):
        messages.error(
            request,
            "HMRC authorisation could not be verified. Please start the connection again.",
        )
        return redirect("hmrc_sandbox_status")

    error = request.GET.get("error")
    if error:
        messages.error(request, "HMRC authorisation was not completed.")
        return redirect("hmrc_sandbox_status")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "HMRC callback did not include an authorisation code.")
        return redirect("hmrc_sandbox_status")

    try:
        unpacked_state = unpack_hmrc_state(state)
        token_payload = exchange_hmrc_authorisation_code(code)
    except Exception:
        logger.exception("HMRC OAuth callback failed without saving authorisation")
        messages.error(
            request,
            "HMRC could not complete the connection. No authorisation was saved.",
        )
        return redirect("hmrc_sandbox_status")

    request.session["hmrc_sandbox_token"] = {
        "scope": token_payload.get("scope"),
        "expires_in": token_payload.get("expires_in"),
        "authorised": True,
    }

    next_url = unpacked_state.get("next") or ""
    tenant_id = (parse_qs(urlparse(next_url).query).get("company") or [None])[0]
    if tenant_id:
        try:
            tenant = _authorised_tenant_for_user(request.user, tenant_id)
            connection, _ = HmrcVatConnection.objects.get_or_create(tenant=tenant)
            expires_in = token_payload["expires_in"]
            connection.access_token = token_payload.get("access_token") or ""
            connection.refresh_token = token_payload.get("refresh_token") or ""
            connection.scope = token_payload.get("scope") or ""
            connection.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            connection.last_authorised_at = timezone.now()
            connection.status = "Connected"
            connection.save()
        except (Http404, ValueError):
            messages.warning(request, "HMRC authorised, but the selected client could not be linked.")
    messages.success(request, "HMRC VAT sandbox authorisation completed.")
    return redirect(unpacked_state.get("next") or "hmrc_sandbox_status")
