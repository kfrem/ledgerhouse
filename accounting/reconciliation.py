from decimal import Decimal
from django.db import transaction
from .models import Journal, JournalLine, NominalAccount, BankTransaction, BankReconciliation


def reconcile_transaction_to_invoice(tenant, bank_transaction, invoice_journal, reconciled_by):
    """
    Transactionally reconciles a BankTransaction to an invoice Journal (SupplierInvoice or SalesInvoice).
    Generates a balanced BankPayment/BankReceipt journal to clear the AR/AP nominal code
    against the Bank nominal account (1200).
    """
    # 1. Verification
    if bank_transaction.tenant != tenant or invoice_journal.tenant != tenant:
        raise ValueError("Tenant mismatch.")

    if BankReconciliation.objects.filter(bank_transaction=bank_transaction).exists():
        raise ValueError("Bank transaction already reconciled.")

    # 2. Get Nominal Accounts
    try:
        acc_bank = NominalAccount.objects.get(tenant=tenant, code="1200")
    except NominalAccount.DoesNotExist:
        raise ValueError("Bank nominal account (1200) not configured for this tenant.")

    # Dynamically determine the clearing code based on the invoice journal lines
    has_creditors = invoice_journal.lines.filter(account__code="2100").exists()
    has_debtors = invoice_journal.lines.filter(account__code="1100").exists()

    if has_creditors:
        clearing_code = "2100"
    elif has_debtors:
        clearing_code = "1100"
    else:
        clearing_code = "2100" if bank_transaction.amount < 0 else "1100"

    try:
        acc_clearing = NominalAccount.objects.get(tenant=tenant, code=clearing_code)
    except NominalAccount.DoesNotExist:
        raise ValueError(f"Clearing nominal account ({clearing_code}) not configured for this tenant.")

    amount_abs = abs(bank_transaction.amount)

    # 3. Create clearing journal and reconciliation link
    with transaction.atomic():
        source_type = "BankPayment" if bank_transaction.amount < 0 else "BankReceipt"
        
        # Create payment/receipt journal
        clearing_journal = Journal.objects.create(
            tenant=tenant,
            date=bank_transaction.date,
            description=f"Settlement of {invoice_journal.source_type} {invoice_journal.id} - Ref: {bank_transaction.reference}",
            source_type=source_type,
            source_id=bank_transaction.fitid,
            created_by=reconciled_by
        )

        if source_type == "BankPayment":
            # Paying supplier: Debit Aged Creditors (2100), Credit Bank (1200)
            JournalLine.objects.create(
                tenant=tenant, journal=clearing_journal, account=acc_clearing,
                debit=amount_abs, credit=Decimal("0.00")
            )
            JournalLine.objects.create(
                tenant=tenant, journal=clearing_journal, account=acc_bank,
                debit=Decimal("0.00"), credit=amount_abs
            )
        else:
            # Customer paid: Debit Bank (1200), Credit Aged Debtors (1100)
            JournalLine.objects.create(
                tenant=tenant, journal=clearing_journal, account=acc_bank,
                debit=amount_abs, credit=Decimal("0.00")
            )
            JournalLine.objects.create(
                tenant=tenant, journal=clearing_journal, account=acc_clearing,
                debit=Decimal("0.00"), credit=amount_abs
            )

        # Create linkage
        link = BankReconciliation.objects.create(
            tenant=tenant,
            bank_transaction=bank_transaction,
            matched_journal=invoice_journal,
            reconciled_by=reconciled_by
        )

    return link, clearing_journal


def verify_ledger_to_bank_balance(tenant, starting_balance=Decimal("0.00")):
    """
    Compares the total balance of the Bank nominal account (1200) ledger
    to the total sum of all imported bank transactions plus starting balance.
    """
    bank_lines = JournalLine.objects.filter(tenant=tenant, account__code="1200")
    debits = sum(line.debit for line in bank_lines)
    credits = sum(line.credit for line in bank_lines)
    
    ledger_balance = debits - credits
    
    tx_sum = sum(tx.amount for tx in BankTransaction.objects.filter(tenant=tenant))
    statement_balance = Decimal(str(starting_balance)) + tx_sum
    
    difference = ledger_balance - statement_balance

    return {
        "ledger_bank_balance": float(round(ledger_balance, 2)),
        "statement_bank_balance": float(round(statement_balance, 2)),
        "difference": float(round(difference, 2)),
        "reconciled": round(difference, 2) == Decimal("0.00")
    }
