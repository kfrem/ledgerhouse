"""A single operational exception register for the practice team."""

from dataclasses import dataclass

from .models import (
    BankReconciliation,
    BankTransaction,
    ClientApprovalRecord,
    EvidenceDocument,
    Journal,
    MonthEndClose,
)


@dataclass(frozen=True)
class AccountingException:
    kind: str
    severity: str
    title: str
    detail: str
    target: str


def exception_register(tenant):
    """Return actionable exceptions without altering accounting records."""
    exceptions = []
    for document in EvidenceDocument.objects.filter(tenant=tenant).exclude(review_status="ReadyForPosting"):
        exceptions.append(AccountingException(
            "Document", "High", f"Review document: {document.filename}",
            "The upload has not been approved for posting.",
            f"/practice/evidence/{document.id}/",
        ))
    reconciled = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    for transaction in BankTransaction.objects.filter(tenant=tenant).exclude(id__in=reconciled):
        is_missing_feed_match = transaction.review_status == "NeedsInfo"
        exceptions.append(AccountingException(
            "Bank", "High",
            (
                f"Investigate bank-feed match: {transaction.reference or transaction.fitid}"
                if is_missing_feed_match else f"Match bank line: {transaction.reference or transaction.fitid}"
            ),
            (
                "The bank feed expected a related ledger item but could not find one. Review before posting."
                if is_missing_feed_match else "This bank transaction is not reconciled to a ledger journal."
            ),
            f"/practice/banking/?company={tenant.id}",
        ))
    for journal in Journal.objects.filter(tenant=tenant, status="RequiresReview"):
        exceptions.append(AccountingException(
            "Ledger", "High", f"Review journal: {journal.description}",
            "The posting is held for practice review.",
            f"/practice/ledger/?company={tenant.id}&status=RequiresReview",
        ))
    for approval in ClientApprovalRecord.objects.filter(
        tenant=tenant, status=ClientApprovalRecord.STATUS_PENDING
    ):
        exceptions.append(AccountingException(
            "Approval", "Normal", f"Client decision needed: {approval.title}",
            "The client approval pack has not been approved or rejected.",
            f"/?company={tenant.id}#approvals",
        ))
    for close in MonthEndClose.objects.filter(tenant=tenant).exclude(status=MonthEndClose.STATUS_CLOSED):
        exceptions.append(AccountingException(
            "Month close", "Normal", f"Complete close: {close.period_end}",
            "The month-end checklist is not closed.",
            f"/practice/accounts-department/?company={tenant.id}",
        ))
    severity_order = {"High": 0, "Normal": 1, "Low": 2}
    return sorted(exceptions, key=lambda item: (severity_order[item.severity], item.kind, item.title))
