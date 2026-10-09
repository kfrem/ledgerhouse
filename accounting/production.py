"""Read-only production registers assembled from LedgerHouse accounting records."""

from collections import defaultdict

from .models import (
    AccountingTask,
    AuditEvent,
    ClientApprovalRecord,
    CompaniesHouseFilingSubmission,
    ManagementPackSection,
    StatutoryAccountsDraft,
)


def _approval_for(tenant, approval_type, reference):
    return ClientApprovalRecord.objects.filter(
        tenant=tenant,
        approval_type=approval_type,
        reference=reference,
    ).first()


def accounts_production_snapshot(tenant):
    """Return a client production view without writing or inferring accounting data."""
    drafts = list(
        StatutoryAccountsDraft.objects.filter(tenant=tenant).order_by("-period_end", "-id")
    )
    submissions = list(
        CompaniesHouseFilingSubmission.objects.filter(tenant=tenant)
        .select_related("statutory_accounts")
        .order_by("-submission_number", "-created_at")
    )
    submissions_by_draft = defaultdict(list)
    for submission in submissions:
        if submission.statutory_accounts_id:
            submissions_by_draft[submission.statutory_accounts_id].append(submission)

    annual_register = []
    for draft in drafts:
        approval = _approval_for(
            tenant,
            ClientApprovalRecord.TYPE_STATUTORY_ACCOUNTS,
            f"STAT-{draft.period_end.isoformat()}",
        )
        filing = submissions_by_draft[draft.id][0] if submissions_by_draft[draft.id] else None
        annual_register.append(
            {
                "reference": f"AC-{draft.id:04d}",
                "draft": draft,
                "approval": approval,
                "filing": filing,
                "source": "Statutory accounts draft",
                "lifecycle": draft.get_status_display(),
                "delivery_status": filing.get_status_display() if filing else "Not submitted",
            }
        )

    sections_by_period = defaultdict(list)
    for section in ManagementPackSection.objects.filter(tenant=tenant).order_by("-period_end", "section_name"):
        sections_by_period[section.period_end].append(section)
    management_register = []
    for period_end, sections in sections_by_period.items():
        approval = _approval_for(
            tenant,
            ClientApprovalRecord.TYPE_MANAGEMENT_PACK,
            f"PACK-{period_end.isoformat()}",
        )
        releases = AuditEvent.objects.filter(
            tenant=tenant,
            event_type="ApprovalPackReleased",
            details__reference=f"PACK-{period_end.isoformat()}",
        ).count()
        management_register.append(
            {
                "reference": f"PACK-{period_end.isoformat()}",
                "period_end": period_end,
                "sections": sections,
                "approval": approval,
                "release_count": releases,
                "lifecycle": "Released" if releases else sections[0].get_status_display(),
            }
        )

    open_tasks = list(
        AccountingTask.objects.filter(tenant=tenant)
        .exclude(status=AccountingTask.STATUS_DONE)
        .order_by("due_date", "-priority", "id")
    )
    owners = sorted({task.owner for task in open_tasks if task.owner})
    release_ready = [
        row for row in management_register
        if row["approval"]
        and row["approval"].status == ClientApprovalRecord.STATUS_APPROVED
        and not row["release_count"]
    ]
    latest_submission = submissions[0] if submissions else None
    latest_draft = drafts[0] if drafts else None
    latest_events = AuditEvent.objects.filter(tenant=tenant).order_by("-timestamp", "-id")[:8]

    return {
        "company": {
            "name": tenant.name,
            "company_number": latest_submission.company_number if latest_submission else "Not recorded",
            "year_end": latest_draft.period_end if latest_draft else None,
            "accounts_type": latest_draft.accounts_type if latest_draft else "Not recorded",
            "status": "Dormant" if latest_draft and latest_draft.accounts_type == "Dormant" else "Active",
        },
        "annual_register": annual_register,
        "management_register": management_register,
        "release_ready": release_ready,
        "open_tasks": open_tasks,
        "owners": owners,
        "latest_events": latest_events,
        "pending_approvals": ClientApprovalRecord.objects.filter(
            tenant=tenant, status=ClientApprovalRecord.STATUS_PENDING
        ).count(),
        "submitted_accounts": sum(1 for row in annual_register if row["filing"]),
    }
