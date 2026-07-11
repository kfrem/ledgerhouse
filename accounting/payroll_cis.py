import csv
from io import StringIO
from decimal import Decimal, InvalidOperation
from django.db import transaction
from accounting.models import Journal, JournalLine, NominalAccount

# HMRC CIS deduction rates: verified (20%), unverified (30%), gross payment status (0%)
ALLOWED_CIS_RATES = (Decimal("0.00"), Decimal("0.20"), Decimal("0.30"))


def get_or_create_nominal(tenant, code, name, category, canonical_taxonomy):
    nom, _ = NominalAccount.objects.get_or_create(
        tenant=tenant,
        code=code,
        defaults={
            "name": name,
            "category": category,
            "canonical_taxonomy": canonical_taxonomy
        }
    )
    return nom


def import_payroll_journal(tenant, csv_content, date_val, created_by="System"):
    """
    Parses a payroll CSV, validating that debits equal credits:
    Debits: Gross Salary (6305) + Employer NI (6315)
    Credits: PAYE/NI Liability (2210) + Net Salaries (2220)
    """
    salaries_acc = get_or_create_nominal(tenant, "6305", "Staff Salaries", "Expense", "Operating Expenses")
    emp_ni_acc = get_or_create_nominal(tenant, "6315", "Employer's NI", "Expense", "Operating Expenses")
    paye_nic_acc = get_or_create_nominal(tenant, "2210", "PAYE & NI Control Account", "Liability", "Tax Liabilities")
    net_salaries_acc = get_or_create_nominal(tenant, "2220", "Net Salaries Control Account", "Liability", "Tax Liabilities")

    f = StringIO(csv_content.strip())
    reader = csv.DictReader(f)
    
    total_paye_nic = Decimal("0.00")
    total_net_wages = Decimal("0.00")
    rows_data = []

    for idx, row in enumerate(reader, start=1):
        dept = row.get("Department", "General")
        try:
            gross = Decimal(row.get("GrossPay", "0.00"))
            emp_ni = Decimal(row.get("EmployerNI", "0.00"))
            ee_ni = Decimal(row.get("EmployeeNI", "0.00"))
            paye = Decimal(row.get("PAYETax", "0.00"))
            net = Decimal(row.get("NetWages", "0.00"))
        except InvalidOperation:
            raise ValueError(f"Payroll CSV row {idx} contains a non-numeric amount.")

        if min(gross, emp_ni, ee_ni, paye, net) < 0:
            raise ValueError(f"Payroll CSV row {idx} contains a negative amount.")

        # The journal only balances if each row is internally consistent:
        # GrossPay must fully decompose into PAYE + Employee NI + Net Wages.
        # Validate here so bad files fail with a clear error instead of a
        # database constraint violation at commit.
        deductions_plus_net = paye + ee_ni + net
        if gross != deductions_plus_net:
            raise ValueError(
                f"Payroll CSV row {idx} is inconsistent: GrossPay ({gross}) must equal "
                f"PAYETax + EmployeeNI + NetWages ({deductions_plus_net})."
            )

        rows_data.append((dept, gross, emp_ni))
        total_paye_nic += (emp_ni + ee_ni + paye)
        total_net_wages += net

    with transaction.atomic():
        j = Journal.objects.create(
            tenant=tenant,
            date=date_val,
            description=f"Payroll Journal - {date_val.strftime('%B %Y')}",
            source_type="ManualJournal",
            created_by=created_by,
            status="Posted"
        )
        
        for dept, gross, emp_ni in rows_data:
            if gross > 0:
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=salaries_acc,
                    debit=gross,
                    credit=Decimal("0.00"),
                    vat_code="OS",
                    department=dept
                )
            if emp_ni > 0:
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=emp_ni_acc,
                    debit=emp_ni,
                    credit=Decimal("0.00"),
                    vat_code="OS",
                    department=dept
                )
                
        if total_paye_nic > 0:
            JournalLine.objects.create(
                tenant=tenant,
                journal=j,
                account=paye_nic_acc,
                debit=Decimal("0.00"),
                credit=total_paye_nic,
                vat_code="OS",
                department="General"
            )
            
        if total_net_wages > 0:
            JournalLine.objects.create(
                tenant=tenant,
                journal=j,
                account=net_salaries_acc,
                debit=Decimal("0.00"),
                credit=total_net_wages,
                vat_code="OS",
                department="General"
            )
            
    return j


def post_subcontractor_invoice(tenant, subcontractor_name, gross_amount, cis_rate, date_val, department="General", created_by="System"):
    """
    Subcontractor CIS invoice builder:
    Debits: Subcontractor Expense (5100) (Gross Amount)
    Credits: CIS Tax Withholding Liability (2230) + Aged Creditors (2100) (Net Payable)
    """
    gross = Decimal(str(gross_amount))
    cis_rate = Decimal(str(cis_rate))
    if cis_rate not in ALLOWED_CIS_RATES:
        raise ValueError(
            f"Invalid CIS rate {cis_rate}. HMRC CIS deduction rates are 0.20 (verified), "
            f"0.30 (unverified) or 0.00 (gross payment status)."
        )
    if gross <= 0:
        raise ValueError("Subcontractor invoice gross amount must be positive.")

    cos_subcon_acc = get_or_create_nominal(tenant, "5100", "Cost of Sales - Direct Materials", "Cost of Sales", "Cost of Sales")
    cis_withholding_acc = get_or_create_nominal(tenant, "2230", "CIS Withholding Liability Account", "Liability", "Tax Liabilities")
    aged_creditors_acc = get_or_create_nominal(tenant, "2100", "Aged Creditors", "Liability", "Trade Payables")

    cis_amount = gross * cis_rate
    net_payable = gross - cis_amount

    with transaction.atomic():
        j = Journal.objects.create(
            tenant=tenant,
            date=date_val,
            description=f"Subcontractor CIS Invoice - {subcontractor_name}",
            source_type="SupplierInvoice",
            created_by=created_by,
            status="RequiresReview"  # Subcontractor invoices require review by default
        )

        # Debit Expense (Gross)
        JournalLine.objects.create(
            tenant=tenant,
            journal=j,
            account=cos_subcon_acc,
            debit=gross,
            credit=Decimal("0.00"),
            vat_code="OS",
            department=department
        )

        # Credit CIS withholding tax liability
        if cis_amount > 0:
            JournalLine.objects.create(
                tenant=tenant,
                journal=j,
                account=cis_withholding_acc,
                debit=Decimal("0.00"),
                credit=cis_amount,
                vat_code="OS",
                department=department
            )

        # Credit Aged Creditors (Net)
        JournalLine.objects.create(
            tenant=tenant,
            journal=j,
            account=aged_creditors_acc,
            debit=Decimal("0.00"),
            credit=net_payable,
            vat_code="OS",
            department=department
        )

    return j
