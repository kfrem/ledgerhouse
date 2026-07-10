from decimal import Decimal
from django.db import models, transaction
from .models import NominalAccount, Journal, JournalLine, VatReturn
from .vat import calculate_vat_report
from .reconciliation import verify_ledger_to_bank_balance


def generate_trial_balance(tenant, as_of_date=None):
    """
    Generates a structured read-only Trial Balance report for the accountant.
    Summarizes debits, credits, and net balances for all nominal accounts.
    """
    trial_balance = []
    accounts = NominalAccount.objects.filter(tenant=tenant).order_by('code')
    
    for acc in accounts:
        lines = JournalLine.objects.filter(tenant=tenant, account=acc)
        if as_of_date:
            lines = lines.filter(journal__date__lte=as_of_date)
            
        agg = lines.aggregate(total_debit=models.Sum('debit'), total_credit=models.Sum('credit'))
        deb = agg['total_debit'] or Decimal("0.00")
        crd = agg['total_credit'] or Decimal("0.00")
        net = deb - crd
        
        trial_balance.append({
            "code": acc.code,
            "name": acc.name,
            "category": acc.category,
            "debit": float(round(deb, 2)),
            "credit": float(round(crd, 2)),
            "net": float(round(net, 2))
        })
        
    return trial_balance


def lock_vat_period(tenant, start_date, end_date, locked_by):
    """
    Submits a VAT return and locks the date range in the database.
    Any future modifications or insertions to journals in this period will be blocked by triggers.
    """
    report = calculate_vat_report(tenant, start_date, end_date)
    
    with transaction.atomic():
        vat_return = VatReturn.objects.create(
            tenant=tenant,
            start_date=start_date,
            end_date=end_date,
            locked_by=locked_by,
            total_output_vat=report["output_vat"],
            total_input_vat=report["input_vat"],
            net_vat_payable=report["net_vat_payable"]
        )
        
    return vat_return


def run_accountant_audit_check(tenant):
    """
    Executes a comprehensive system-wide audit check for the accountant.
    Ensures:
      1. Trial balance nets to exactly 0.00.
      2. No journals remain in 'RequiresReview' status.
      3. Bank reconciliation is fully completed with a difference of 0.00.
    """
    # 1. Trial Balance Check
    tb = generate_trial_balance(tenant)
    tb_sum = sum(acc["net"] for acc in tb)
    tb_balanced = abs(round(tb_sum, 2)) == 0.0
    
    # 2. Unreviewed Journals Check
    requires_review_count = Journal.objects.filter(tenant=tenant, status='RequiresReview').count()
    
    # 3. Bank Reconciliation Check
    # Retrieve pre-migration starting balance of Cash/Bank (1200) from ManualJournal entries
    starting_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code="1200",
        journal__source_type="ManualJournal"
    )
    starting_balance = sum(line.debit - line.credit for line in starting_lines)
    
    bank_check = verify_ledger_to_bank_balance(tenant, starting_balance=starting_balance)
    
    is_clean = tb_balanced and (requires_review_count == 0) and bank_check["reconciled"]
    
    return {
        "trial_balance_balanced": tb_balanced,
        "trial_balance_sum": float(round(tb_sum, 2)),
        "requires_review_count": requires_review_count,
        "bank_reconciliation": bank_check,
        "is_clean": is_clean
    }
