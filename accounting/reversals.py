from datetime import date
from django.db import transaction
from .models import Journal, JournalLine, AccountingPeriod


def reverse_journal(tenant, original_journal, created_by):
    """
    Transactionally creates a reversal journal with debits and credits swapped.
    If the original journal's date falls in a closed period, the reversal is posted
    on the current date (today) if that period is open, preventing locked period violations.
    """
    # 1. Verification checks
    if original_journal.tenant != tenant:
        raise ValueError("Tenant mismatch.")

    # Prevent double reversals or reversing a reversal
    if original_journal.description.startswith("Reversal of Journal"):
        raise ValueError("Cannot reverse a journal that is itself a reversal.")

    if Journal.objects.filter(tenant=tenant, description__startswith=f"Reversal of Journal {original_journal.id}").exists():
        raise ValueError("Journal already reversed.")

    # 2. Determine reversal journal date
    reversal_date = original_journal.date
    is_original_period_closed = AccountingPeriod.objects.filter(
        tenant=tenant,
        start_date__lte=reversal_date,
        end_date__gte=reversal_date,
        is_closed=True
    ).exists()

    if is_original_period_closed:
        reversal_date = date.today()
        # Ensure the current date falls within an open period
        is_today_period_closed = AccountingPeriod.objects.filter(
            tenant=tenant,
            start_date__lte=reversal_date,
            end_date__gte=reversal_date,
            is_closed=True
        ).exists()
        if is_today_period_closed:
            raise ValueError("Cannot reverse journal. Both the original period and the current period are closed.")

    # 3. Create reversal postings transactionally
    with transaction.atomic():
        reversal_journal = Journal.objects.create(
            tenant=tenant,
            date=reversal_date,
            description=f"Reversal of Journal {original_journal.id}: {original_journal.description}",
            source_type="ManualJournal",
            created_by=created_by
        )

        for line in original_journal.lines.all():
            JournalLine.objects.create(
                tenant=tenant,
                journal=reversal_journal,
                account=line.account,
                debit=line.credit,   # Swap debit and credit
                credit=line.debit,
                vat_code=line.vat_code,
                vat_rate=line.vat_rate,
                vat_amount=line.vat_amount,
                department=line.department
            )

    return reversal_journal


def get_review_metrics(tenant):
    """
    Returns metrics tracking transaction review counts.
    """
    requires_review = Journal.objects.filter(tenant=tenant, status='RequiresReview').count()
    evidenced = Journal.objects.filter(
        tenant=tenant,
        source_type__in=['SalesInvoice', 'SupplierInvoice', 'EmployeeExpense'],
        status='Posted'
    ).count()
    
    return {
        "requires_review_count": requires_review,
        "evidenced_count": evidenced
    }
