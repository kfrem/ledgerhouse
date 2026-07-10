from decimal import Decimal
from django.db.models import Q
from .models import VatRate, VatDecisionRule, JournalLine


def resolve_vat_treatment(tenant, supplier_name, account_code, date):
    """
    Resolves the appropriate VAT code and active rate for a given transaction.
    Matches rules by priority, checking supplier name and account code patterns.
    """
    # Query rules ordered by priority (lower priority number matches first)
    rules = VatDecisionRule.objects.filter(tenant=tenant).order_by('priority')
    
    resolved_code = None
    supplier_name = (supplier_name or '').strip().lower()
    account_code = (account_code or '').strip()

    for rule in rules:
        match_supplier = True
        match_account = True
        
        # Check supplier pattern
        if rule.supplier_name_pattern:
            pattern = rule.supplier_name_pattern.strip().lower()
            if pattern not in supplier_name:
                match_supplier = False
                
        # Check account pattern (matches prefixes e.g. "6" matches "6100", "6200")
        if rule.account_code_pattern:
            pattern = rule.account_code_pattern.strip()
            if not account_code.startswith(pattern):
                match_account = False
                
        # If both patterns match, resolve and stop
        if match_supplier and match_account:
            resolved_code = rule.vat_code
            break
            
    # Default fallback if no rule matches
    if not resolved_code:
        # Default standard rate for sales revenue (4xxx)
        if account_code.startswith("4000"):
            resolved_code = "SR"
        elif account_code.startswith("4010"):
            resolved_code = "ZR"
        elif account_code.startswith("4020"):
            resolved_code = "EX"
        else:
            resolved_code = "OS"  # Outside Scope default fallback
            
    # Lookup rate active on the given date
    rate_record = VatRate.objects.filter(
        tenant=tenant,
        vat_code=resolved_code,
        effective_from__lte=date
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=date)
    ).order_by('-effective_from').first()
    
    rate_val = rate_record.rate if rate_record else Decimal("0.0000")
    return resolved_code, rate_val


def calculate_vat_report(tenant, start_date, end_date):
    """
    Calculates Output VAT (from Sales), Input VAT (from purchases), and Net VAT payable.
    Reconciles these figures against the net balance of the VAT Control Account (2200).
    """
    # Output VAT: Sales Invoices & Credit Notes
    # We query journal lines associated with sales revenue (starts with 4) and VAT account (2200)
    # Output VAT is the total credit posted to VAT account (2200) from Sales Invoices, minus any debits from Credit Notes
    sales_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SalesInvoice", "SalesCreditNote"]
    )
    
    output_vat = Decimal("0.00")
    for line in sales_lines:
        if line.account.code == "2200":
            # For output VAT: credits increase the liability (SalesInvoice credits 2200),
            # debits decrease it (SalesCreditNote debits 2200)
            output_vat += (line.credit - line.debit)

    # Input VAT: Purchases/Expenses
    purchase_lines = JournalLine.objects.filter(
        tenant=tenant,
        journal__date__gte=start_date,
        journal__date__lte=end_date,
        journal__source_type__in=["SupplierInvoice", "EmployeeExpense"]
    )
    
    input_vat = Decimal("0.00")
    for line in purchase_lines:
        if line.account.code == "2200":
            # For input VAT: debits increase the recoverable VAT (debit 2200)
            input_vat += (line.debit - line.credit)
            
    net_vat_payable = output_vat - input_vat

    # Reconcile against the total posted balance on the VAT Control Account (2200)
    vat_control_lines = JournalLine.objects.filter(
        tenant=tenant,
        account__code="2200",
        journal__date__gte=start_date,
        journal__date__lte=end_date
    )
    debits = sum(line.debit for line in vat_control_lines)
    credits = sum(line.credit for line in vat_control_lines)
    
    # Ledger balance: debits - credits
    ledger_balance = debits - credits
    
    # Reconciled if: input_vat - output_vat == ledger_balance (i.e. -net_vat_payable == ledger_balance)
    reconciled = round(ledger_balance + net_vat_payable, 2) == Decimal("0.00")

    return {
        "output_vat": float(round(output_vat, 2)),
        "input_vat": float(round(input_vat, 2)),
        "net_vat_payable": float(round(net_vat_payable, 2)),
        "ledger_balance": float(round(ledger_balance, 2)),
        "reconciled": reconciled
    }
