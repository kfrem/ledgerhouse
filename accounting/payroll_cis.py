import csv
from io import StringIO
from decimal import Decimal, InvalidOperation
from django.db import transaction
from accounting.models import Journal, JournalLine, NominalAccount, PayrollSummary

# HMRC CIS deduction rates: verified (20%), unverified (30%), gross payment status (0%)
ALLOWED_CIS_RATES = (Decimal("0.00"), Decimal("0.20"), Decimal("0.30"))
PAYROLL_COLUMNS = ("Department", "GrossPay", "EmployerNI", "EmployeeNI", "PAYETax", "NetWages")


def parse_payroll_csv(csv_content):
    """Validate a payroll export and return journal rows plus period totals."""
    reader = csv.DictReader(StringIO(csv_content.strip()))
    if not reader.fieldnames or any(column not in reader.fieldnames for column in PAYROLL_COLUMNS):
        raise ValueError("Payroll CSV must include Department, GrossPay, EmployerNI, EmployeeNI, PAYETax and NetWages columns.")

    totals = {"gross_pay": Decimal("0.00"), "employer_ni": Decimal("0.00"), "employee_ni": Decimal("0.00"), "paye": Decimal("0.00"), "net_wages": Decimal("0.00")}
    rows_data = []
    # Report data-row numbers, matching the existing payroll import contract
    # and keeping messages actionable for a user who is looking at records
    # below the CSV header.
    for idx, row in enumerate(reader, start=1):
        if not any((value or "").strip() for value in row.values()):
            continue
        department = (row.get("Department") or "General").strip() or "General"
        try:
            gross = Decimal(row["GrossPay"])
            employer_ni = Decimal(row["EmployerNI"])
            employee_ni = Decimal(row["EmployeeNI"])
            paye = Decimal(row["PAYETax"])
            net = Decimal(row["NetWages"])
        except (InvalidOperation, TypeError) as exc:
            raise ValueError(f"Payroll CSV row {idx} contains a non-numeric amount.") from exc
        if min(gross, employer_ni, employee_ni, paye, net) < 0:
            raise ValueError(f"Payroll CSV row {idx} contains a negative amount.")
        if gross != paye + employee_ni + net:
            raise ValueError(f"Payroll CSV row {idx} is inconsistent: GrossPay must equal PAYETax + EmployeeNI + NetWages.")
        rows_data.append((department, gross, employer_ni, employee_ni, paye, net))
        totals["gross_pay"] += gross
        totals["employer_ni"] += employer_ni
        totals["employee_ni"] += employee_ni
        totals["paye"] += paye
        totals["net_wages"] += net
    if not rows_data:
        raise ValueError("Payroll CSV does not contain any payroll rows.")
    return rows_data, totals


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

    rows_data, totals = parse_payroll_csv(csv_content)
    total_paye_nic = totals["employer_ni"] + totals["employee_ni"] + totals["paye"]
    total_net_wages = totals["net_wages"]

    with transaction.atomic():
        j = Journal.objects.create(
            tenant=tenant,
            date=date_val,
            description=f"Payroll Journal - {date_val.strftime('%B %Y')}",
            source_type="ManualJournal",
            created_by=created_by,
            status="Posted"
        )
        
        for dept, gross, emp_ni, _ee_ni, _paye, _net in rows_data:
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


def post_payroll_period(tenant, csv_content, period_start, period_end, created_by="System"):
    """Post one validated payroll export once per accounting period."""
    if period_start > period_end:
        raise ValueError("Payroll period start must be on or before the period end.")
    _rows, totals = parse_payroll_csv(csv_content)
    with transaction.atomic():
        summary, created = PayrollSummary.objects.select_for_update().get_or_create(
            tenant=tenant,
            period_start=period_start,
            period_end=period_end,
            defaults={
                "gross_pay": totals["gross_pay"], "paye": totals["paye"],
                "employee_ni": totals["employee_ni"], "employer_ni": totals["employer_ni"],
            },
        )
        if not created and summary.journal_posted:
            raise ValueError("Payroll for this period has already been posted. Reverse it through the ledger review process before replacing it.")
        journal = import_payroll_journal(tenant, csv_content, period_end, created_by)
        summary.gross_pay = totals["gross_pay"]
        summary.paye = totals["paye"]
        summary.employee_ni = totals["employee_ni"]
        summary.employer_ni = totals["employer_ni"]
        summary.journal_posted = True
        summary.status = "Posted"
        summary.save()
    return summary, journal


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
