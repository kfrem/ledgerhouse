import random
from datetime import date, timedelta
from typing import Dict, List, Any

# Chart of accounts mapping to a canonical taxonomy
CHART_OF_ACCOUNTS = {
    # ASSETS (1000 - 1999)
    "1200": {"name": "Bank Current Account", "category": "Asset", "canonical": "Cash & Cash Equivalents"},
    "1210": {"name": "Petty Cash", "category": "Asset", "canonical": "Cash & Cash Equivalents"},
    "1500": {"name": "Prepayments", "category": "Asset", "canonical": "Other Current Assets"},
    "1600": {"name": "Fixed Assets - Computer Equipment", "category": "Asset", "canonical": "Property, Plant & Equipment"},
    "1601": {"name": "Fixed Assets - Accum Depr Computer Equipment", "category": "Asset", "canonical": "Property, Plant & Equipment Contra"},
    
    # LIABILITIES (2000 - 2999)
    "2100": {"name": "Aged Creditors", "category": "Liability", "canonical": "Trade Payables"},
    "2200": {"name": "VAT Control Account", "category": "Liability", "canonical": "Tax Liabilities"},
    "2300": {"name": "Accruals", "category": "Liability", "canonical": "Other Current Liabilities"},
    "2400": {"name": "Director's Loan Account", "category": "Liability", "canonical": "Equity / Long-term Liabilities"},
    
    # EQUITY (3000 - 3999)
    "3000": {"name": "Share Capital", "category": "Equity", "canonical": "Share Capital"},
    "3200": {"name": "Retained Earnings", "category": "Equity", "canonical": "Retained Earnings"},
    
    # REVENUE (4000 - 4999)
    "4000": {"name": "Sales Revenue (Standard Rated)", "category": "Revenue", "canonical": "Operating Revenue"},
    "4010": {"name": "Sales Revenue (Zero Rated)", "category": "Revenue", "canonical": "Operating Revenue"},
    "4020": {"name": "Sales Revenue (Exempt)", "category": "Revenue", "canonical": "Operating Revenue"},
    
    # COST OF SALES (5000 - 5999)
    "5000": {"name": "Cost of Sales - Care Agency Costs", "category": "Cost of Sales", "canonical": "Cost of Sales"},
    "5100": {"name": "Cost of Sales - Direct Materials", "category": "Cost of Sales", "canonical": "Cost of Sales"},
    
    # ADMINISTRATIVE EXPENSES (6000 - 6999)
    "6000": {"name": "Rent", "category": "Expense", "canonical": "Operating Expenses"},
    "6100": {"name": "Utilities", "category": "Expense", "canonical": "Operating Expenses"},
    "6200": {"name": "Software Subscriptions", "category": "Expense", "canonical": "Operating Expenses"},
    "6300": {"name": "Staff Expenses", "category": "Expense", "canonical": "Operating Expenses"},
    "6310": {"name": "Staff Expenses - Mileage", "category": "Expense", "canonical": "Operating Expenses"},
    "6400": {"name": "Professional Fees", "category": "Expense", "canonical": "Operating Expenses"},
    "6500": {"name": "Bank Fees / Charges", "category": "Expense", "canonical": "Operating Expenses"},
    "6600": {"name": "Depreciation Expense", "category": "Expense", "canonical": "Operating Expenses"},
}

VAT_CODES = {
    "SR": {"rate": 0.20, "name": "Standard Rate (20%)"},
    "RR": {"rate": 0.05, "name": "Reduced Rate (5%)"},
    "ZR": {"rate": 0.00, "name": "Zero Rate (0%)"},
    "EX": {"rate": 0.00, "name": "Exempt (0%)"},
    "OS": {"rate": 0.00, "name": "Outside Scope (0%)"}
}


class SyntheticCompanyFactory:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_all(self) -> Dict[str, Any]:
        """Generates all 3 companies and the unified expected results."""
        care_provider = self.generate_care_provider()
        consultancy = self.generate_consultancy()
        trading_company = self.generate_trading_company()

        # Build expected results / balances validation cross-check
        expected_results = {
            "care_provider": self.build_expected_outcomes(care_provider),
            "consultancy": self.build_expected_outcomes(consultancy),
            "trading_company": self.build_expected_outcomes(trading_company)
        }

        return {
            "companies": {
                "care_provider": care_provider["metadata"],
                "consultancy": consultancy["metadata"],
                "trading_company": trading_company["metadata"],
            },
            "fixtures": {
                "care_provider": {
                    "transactions": care_provider["transactions"],
                    "bank_statement": care_provider["bank_statement"],
                },
                "consultancy": {
                    "transactions": consultancy["transactions"],
                    "bank_statement": consultancy["bank_statement"],
                },
                "trading_company": {
                    "transactions": trading_company["transactions"],
                    "bank_statement": trading_company["bank_statement"],
                }
            },
            "expected_results": expected_results,
            "rejection_scenarios": self.generate_rejection_scenarios()
        }

    def generate_care_provider(self) -> Dict[str, Any]:
        """
        Care provider is CareCo Limited.
        VAT Exempt services mostly. Departments: Residential, Domiciliary, Head Office.
        Contains: staff expenses, agency costs, rent, utilities, regular suppliers,
        sales invoices, credit notes, customer receipts, bank charges, refunds, partial/over-payments,
        approval limit examples.
        """
        metadata = {
            "id": "tenant-careco",
            "name": "CareCo Limited",
            "vat_registered": True,
            "departments": ["Residential", "Domiciliary", "Head Office"],
            "currency": "GBP"
        }

        # Seed specific local generator
        rng = random.Random(self.seed + 1)

        transactions = []
        
        # 1. Opening Trial Balance (balanced manual journal)
        # Date: 2026-06-01
        transactions.append({
            "type": "ManualJournal",
            "id": "CP-MJ-001",
            "date": "2026-06-01",
            "description": "Opening balances post migration",
            "lines": [
                {"account": "1200", "debit": 50000.00, "credit": 0.00, "vat_code": "OS"},
                {"account": "3000", "debit": 0.00, "credit": 1000.00, "vat_code": "OS"},
                {"account": "3200", "debit": 0.00, "credit": 49000.00, "vat_code": "OS"}
            ],
            "approved_by": "Godfred (Accountant)",
            "status": "Posted"
        })

        # 2. Rent (Standard Rated VAT - Commercial landlord has opted to tax)
        # Rent: £5,000 net, £1,000 VAT. Head Office department.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CP-SI-001",
            "invoice_number": "RENT-JUNE",
            "supplier": "Lumina Properties Ltd",
            "date": "2026-06-01",
            "department": "Head Office",
            "lines": [
                {"account": "6000", "description": "June 2026 Office Rent", "net": 5000.00, "vat_code": "SR", "vat": 1000.00}
            ],
            "evidence_link": "/evidence/lumina_rent_june_2026.pdf",
            "approved_by": "Director Jane",
            "status": "Posted"
        })

        # 3. Cost of Sales - Care Agency Costs (Exempt VAT - welfare agency service)
        # Care agency cost: £12,000 net, £0.00 VAT. Residential department.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CP-SI-002",
            "invoice_number": "AG-10023",
            "supplier": "CareStaff Specialists",
            "date": "2026-06-05",
            "department": "Residential",
            "lines": [
                {"account": "5000", "description": "Agency nurse cover w/e June 5", "net": 12000.00, "vat_code": "EX", "vat": 0.00}
            ],
            "evidence_link": "/evidence/carestaff_ag_10023.pdf",
            "approved_by": "Manager Dave",  # Within £500 limit for Manager? No, £12,000 would need Director or CEO approval
            "approved_by": "Director Jane", # Correctly escalated
            "status": "Posted"
        })

        # 4. Utilities (Reduced Rate VAT - 5%)
        # Electricity bill: £400 net, £20 VAT. Domiciliary department.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CP-SI-003",
            "invoice_number": "POW-9921",
            "supplier": "British Gas Business",
            "date": "2026-06-10",
            "department": "Domiciliary",
            "lines": [
                {"account": "6100", "description": "Power usage June", "net": 400.00, "vat_code": "RR", "vat": 20.00}
            ],
            "evidence_link": "/evidence/gas_pow_9921.pdf",
            "approved_by": "Manager Dave",  # Dave has limit £500, can approve this.
            "status": "Posted"
        })

        # 5. Sales Invoice - Local Authority Care Care Packages (Exempt from VAT under UK law)
        # Care services sold: £25,000 net, £0 VAT. Domiciliary.
        transactions.append({
            "type": "SalesInvoice",
            "id": "CP-VI-001",
            "invoice_number": "CP-2026-001",
            "customer": "Kent County Council",
            "date": "2026-06-15",
            "department": "Domiciliary",
            "lines": [
                {"account": "4020", "description": "Domiciliary Care Packages June", "net": 25000.00, "vat_code": "EX", "vat": 0.00}
            ],
            "evidence_link": "/evidence/kcc_invoice_june.pdf",
            "status": "Posted"
        })

        # 6. Sales Invoice - Private Client Care (Exempt VAT)
        # Care services sold: £8,000 net, £0 VAT. Residential.
        transactions.append({
            "type": "SalesInvoice",
            "id": "CP-VI-002",
            "invoice_number": "CP-2026-002",
            "customer": "Family of Arthur Dent",
            "date": "2026-06-16",
            "department": "Residential",
            "lines": [
                {"account": "4020", "description": "Residential Care Fees June", "net": 8000.00, "vat_code": "EX", "vat": 0.00}
            ],
            "evidence_link": "/evidence/dent_fees_june.pdf",
            "status": "Posted"
        })

        # 7. Credit Note issued to Kent County Council (Exempt VAT)
        # Overbilling credit: £1,500 net, £0 VAT. Domiciliary.
        transactions.append({
            "type": "SalesCreditNote",
            "id": "CP-CN-001",
            "credit_note_number": "CP-2026-CN01",
            "original_invoice": "CP-2026-001",
            "customer": "Kent County Council",
            "date": "2026-06-18",
            "department": "Domiciliary",
            "lines": [
                {"account": "4020", "description": "Rebate for cancelled care hours", "net": 1500.00, "vat_code": "EX", "vat": 0.00}
            ],
            "evidence_link": "/evidence/kcc_credit_note.pdf",
            "approved_by": "Director Jane",
            "status": "Posted"
        })

        # 8. Employee Expenses - Travel mileage (Zero Rated for public transport / Mileage is Outside Scope reimb)
        # Mileage reimbursement: £120.00. Claimant: Staff Member John. Approved by Manager Dave (limit £500).
        transactions.append({
            "type": "EmployeeExpense",
            "id": "CP-EE-001",
            "claimant": "Staff John",
            "date": "2026-06-20",
            "department": "Domiciliary",
            "lines": [
                {"account": "6310", "description": "Mileage reimbursement for home visits", "net": 120.00, "vat_code": "OS", "vat": 0.00}
            ],
            "evidence_link": "/evidence/john_mileage_june.pdf",
            "approved_by": "Manager Dave",
            "status": "Posted"
        })

        # Bank Statement Rows (CSV bank import simulation)
        # Opening bank balance: £50,000.00
        bank_statement = [
            # Rent payment (Full payment of Lumina invoice £6,000)
            {"date": "2026-06-02", "amount": -6000.00, "reference": "LUMINA RENT JUNE", "fitid": "FITID-CP-001", "matched_to": "CP-SI-001"},
            # KCC customer receipt (Partial payment: billed £25,000 - CN £1,500 = £23,500. Paid £20,000 as partial payment)
            {"date": "2026-06-20", "amount": 20000.00, "reference": "KENT COUNTY COUNCIL REC", "fitid": "FITID-CP-002", "matched_to": "CP-VI-001"},
            # Arthur Dent family receipt (Overpayment: billed £8,000. Paid £8,500 by mistake)
            {"date": "2026-06-22", "amount": 8500.00, "reference": "DENT RES CARE FEES", "fitid": "FITID-CP-003", "matched_to": "CP-VI-002"},
            # CareStaff specialist payment (Full payment: billed £12,000)
            {"date": "2026-06-25", "amount": -12000.00, "reference": "CARESTAFF SPEC", "fitid": "FITID-CP-004", "matched_to": "CP-SI-002"},
            # Reimburse Staff John mileage (£120)
            {"date": "2026-06-26", "amount": -120.00, "reference": "EXPENSE REIMB JOHN", "fitid": "FITID-CP-005", "matched_to": "CP-EE-001"},
            # Bank charge (Exempt)
            {"date": "2026-06-30", "amount": -25.00, "reference": "MONTHLY ACCOUNT FEE", "fitid": "FITID-CP-006", "matched_to": "CP-BC-001"},
        ]

        # Let's add the bank charge transaction to the transaction list so we can map it
        transactions.append({
            "type": "BankCharge",
            "id": "CP-BC-001",
            "date": "2026-06-30",
            "department": "Head Office",
            "lines": [
                {"account": "6500", "description": "Monthly Bank Fee", "net": 25.00, "vat_code": "EX", "vat": 0.00}
            ],
            "status": "Posted"
        })

        return {
            "metadata": metadata,
            "transactions": transactions,
            "bank_statement": bank_statement
        }

    def generate_consultancy(self) -> Dict[str, Any]:
        """
        Consultancy is ConsultCo Limited.
        VAT Registered, standard rated sales and software purchases, professional fees.
        Contains: Software subscriptions, Client invoices, Expenses, Director loan transactions,
        Prepayments, Accruals, Fixed asset purchases.
        """
        metadata = {
            "id": "tenant-consultco",
            "name": "ConsultCo Limited",
            "vat_registered": True,
            "departments": ["Tech Consulting", "Strategy", "Operations"],
            "currency": "GBP"
        }

        transactions = []
        
        # 1. Opening Trial Balance (balanced manual journal)
        transactions.append({
            "type": "ManualJournal",
            "id": "CC-MJ-001",
            "date": "2026-06-01",
            "description": "Opening balances post migration",
            "lines": [
                {"account": "1200", "debit": 30000.00, "credit": 0.00, "vat_code": "OS"},
                {"account": "3000", "debit": 0.00, "credit": 100.00, "vat_code": "OS"},
                {"account": "3200", "debit": 0.00, "credit": 29900.00, "vat_code": "OS"}
            ],
            "approved_by": "Godfred (Accountant)",
            "status": "Posted"
        })

        # 2. Software Subscription (Standard Rate VAT 20%)
        # Software invoice: £1,200 net, £240 VAT. Strategy department.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CC-SI-001",
            "invoice_number": "AWS-JUNE-99",
            "supplier": "Amazon Web Services",
            "date": "2026-06-02",
            "department": "Tech Consulting",
            "lines": [
                {"account": "6200", "description": "Cloud hosting June", "net": 1200.00, "vat_code": "SR", "vat": 240.00}
            ],
            "evidence_link": "/evidence/aws_june_99.pdf",
            "approved_by": "Manager Strategy Bob",
            "status": "Posted"
        })

        # 3. Client Sales Invoice (Standard Rate VAT 20%)
        # Strategy consulting: £10,000 net, £2,000 VAT.
        transactions.append({
            "type": "SalesInvoice",
            "id": "CC-VI-001",
            "invoice_number": "CC-2026-01",
            "customer": "Vogosphere Corp",
            "date": "2026-06-10",
            "department": "Strategy",
            "lines": [
                {"account": "4000", "description": "Strategy consulting retainer June", "net": 10000.00, "vat_code": "SR", "vat": 2000.00}
            ],
            "evidence_link": "/evidence/vogo_retainer_june.pdf",
            "status": "Posted"
        })

        # 4. Director Transaction Requiring Review (Director Loan Account adjustment)
        # Director pays personal gym membership using company card: £80.00. Outside scope.
        transactions.append({
            "type": "DirectorTransaction",
            "id": "CC-DT-001",
            "director": "Director Sarah",
            "date": "2026-06-15",
            "department": "Operations",
            "lines": [
                {"account": "2400", "description": "Gym membership paid by company (Sarah DLA)", "net": 80.00, "vat_code": "OS", "vat": 0.00}
            ],
            "evidence_link": "/evidence/gym_receipt.pdf",
            "status": "RequiresReview"  # Flagged for review since it's a director personal item on corporate card
        })

        # 5. Fixed Asset Purchase (Standard Rate VAT 20%)
        # Laptop purchase: £2,000 net, £400 VAT. Tech Consulting.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CC-SI-002",
            "invoice_number": "APL-33421",
            "supplier": "Apple Store Business",
            "date": "2026-06-18",
            "department": "Tech Consulting",
            "lines": [
                {"account": "1600", "description": "MacBook Pro 16 inch (Asset)", "net": 2000.00, "vat_code": "SR", "vat": 400.00}
            ],
            "evidence_link": "/evidence/apple_fa_laptop.pdf",
            "approved_by": "Director Sarah",
            "status": "Posted"
        })

        # 6. Prepayment Scenario (Annual Software license paid in advance)
        # Software purchase: £2,400 net, £480 VAT. Tech Consulting.
        # Annual fee covering July 2026 to June 2027. We record it as asset 1500 (Prepayments) first.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "CC-SI-003",
            "invoice_number": "JIRA-ANNUAL-2026",
            "supplier": "Atlassian Corp",
            "date": "2026-06-20",
            "department": "Tech Consulting",
            "lines": [
                {"account": "1500", "description": "Jira Annual License July 26 - June 27", "net": 2400.00, "vat_code": "SR", "vat": 480.00}
            ],
            "evidence_link": "/evidence/atlassian_jira_annual.pdf",
            "approved_by": "Director Sarah",
            "status": "Posted"
        })

        # 7. Accrual Scenario (Accrued accounting fees for the year-end accounts)
        # We accrue £500 of accounting costs at month-end (no VAT on accrual lines - recorded outside scope)
        transactions.append({
            "type": "ManualJournal",
            "id": "CC-MJ-002",
            "date": "2026-06-30",
            "description": "Accrued accounting fees for June 2026",
            "lines": [
                {"account": "6400", "debit": 500.00, "credit": 0.00, "vat_code": "OS"},
                {"account": "2300", "debit": 0.00, "credit": 500.00, "vat_code": "OS"}
            ],
            "approved_by": "Godfred (Accountant)",
            "status": "Posted"
        })

        # Bank Statement
        bank_statement = [
            # AWS payment
            {"date": "2026-06-05", "amount": -1440.00, "reference": "AWS SUBSCRIPTION", "fitid": "FITID-CC-001", "matched_to": "CC-SI-001"},
            # Vogosphere receipt (Billed £12,000, paid in full)
            {"date": "2026-06-15", "amount": 12000.00, "reference": "VOGOSPHERE INVOICE CC-2026-01", "fitid": "FITID-CC-002", "matched_to": "CC-VI-001"},
            # Director Sarah gym gym payment on company card (£80.00)
            {"date": "2026-06-16", "amount": -80.00, "reference": " Sarah Gym card payment", "fitid": "FITID-CC-003", "matched_to": "CC-DT-001"},
            # Apple invoice payment (£2,400)
            {"date": "2026-06-22", "amount": -2400.00, "reference": "APPLE ONLINE STORE", "fitid": "FITID-CC-004", "matched_to": "CC-SI-002"},
            # Atlassian payment (£2,880)
            {"date": "2026-06-25", "amount": -2880.00, "reference": "ATLASSIAN JIRA", "fitid": "FITID-CC-005", "matched_to": "CC-SI-003"},
        ]

        return {
            "metadata": metadata,
            "transactions": transactions,
            "bank_statement": bank_statement
        }

    def generate_trading_company(self) -> Dict[str, Any]:
        """
        Trading company is TradeCo Limited.
        VAT Registered. Purchases and sales, returns, bank fees.
        Contains: standard, zero-rated, exempt, reduced-rated, mixed VAT, and duplicate scenarios.
        No stock accounting, simple purchase flow.
        """
        metadata = {
            "id": "tenant-tradeco",
            "name": "TradeCo Limited",
            "vat_registered": True,
            "departments": ["Sales", "Logistics", "Operations"],
            "currency": "GBP"
        }

        transactions = []
        
        # 1. Opening Trial Balance (balanced manual journal)
        transactions.append({
            "type": "ManualJournal",
            "id": "TC-MJ-001",
            "date": "2026-06-01",
            "description": "Opening balances post migration",
            "lines": [
                {"account": "1200", "debit": 20000.00, "credit": 0.00, "vat_code": "OS"},
                {"account": "3000", "debit": 0.00, "credit": 1000.00, "vat_code": "OS"},
                {"account": "3200", "debit": 0.00, "credit": 19000.00, "vat_code": "OS"}
            ],
            "approved_by": "Godfred (Accountant)",
            "status": "Posted"
        })

        # 2. Mixed VAT Invoice (Purchase of stationery and books - some 20% VAT, some 0% VAT)
        # Office items: £100 net @ 20% VAT (£20 VAT). Books: £50 net @ 0% VAT (Zero Rated).
        # Total invoice: £170.00. Operations department.
        transactions.append({
            "type": "SupplierInvoice",
            "id": "TC-SI-001",
            "invoice_number": "ST-99120",
            "supplier": "Stationery & Book Palace",
            "date": "2026-06-04",
            "department": "Operations",
            "lines": [
                {"account": "5100", "description": "Stationery supplies", "net": 100.00, "vat_code": "SR", "vat": 20.00},
                {"account": "5100", "description": "Reference textbooks", "net": 50.00, "vat_code": "ZR", "vat": 0.00}
            ],
            "evidence_link": "/evidence/stationery_book_palace_99120.pdf",
            "approved_by": "Manager Sales Tim",
            "status": "Posted"
        })

        # 3. Duplicate Invoice Number Attempt (Same invoice number, same supplier, but different date/amount)
        # To test duplicate prevention control, this is flagged as "BlockedDuplicate".
        transactions.append({
            "type": "SupplierInvoice",
            "id": "TC-SI-001-DUP",
            "invoice_number": "ST-99120",  # Same invoice number!
            "supplier": "Stationery & Book Palace",
            "date": "2026-06-06",
            "department": "Operations",
            "lines": [
                {"account": "5100", "description": "Stationery supplies duplicate", "net": 100.00, "vat_code": "SR", "vat": 20.00}
            ],
            "evidence_link": "/evidence/stationery_book_palace_99120.pdf",
            "approved_by": "Manager Sales Tim",
            "status": "BlockedDuplicate"
        })

        # 4. Standard Rate Sales Invoice
        # Sales: £5,000 net, £1,000 VAT. Sales department.
        transactions.append({
            "type": "SalesInvoice",
            "id": "TC-VI-001",
            "invoice_number": "TC-2026-101",
            "customer": "Megacorp UK",
            "date": "2026-06-10",
            "department": "Sales",
            "lines": [
                {"account": "4000", "description": "Sale of widgets type A", "net": 5000.00, "vat_code": "SR", "vat": 1000.00}
            ],
            "evidence_link": "/evidence/megacorp_widgets.pdf",
            "status": "Posted"
        })

        # 5. Customer Return / Sales Credit Note (Standard Rated)
        # Returned widgets: £500 net, £100 VAT. Sales department.
        transactions.append({
            "type": "SalesCreditNote",
            "id": "TC-CN-001",
            "credit_note_number": "TC-2026-CN101",
            "original_invoice": "TC-2026-101",
            "customer": "Megacorp UK",
            "date": "2026-06-14",
            "department": "Sales",
            "lines": [
                {"account": "4000", "description": "Returned widgets rebate", "net": 500.00, "vat_code": "SR", "vat": 100.00}
            ],
            "evidence_link": "/evidence/megacorp_credit_return.pdf",
            "approved_by": "Manager Sales Tim",
            "status": "Posted"
        })

        # Bank Statement
        # Simulate:
        # - Payment to Stationery Palace (£170.00)
        # - Receipt from Megacorp (£6,000.00 billed. Returns credit note of £600 applied. Net is £5,400. Megacorp pays £5,400)
        # - Bank fees (£10.00)
        # - A duplicate bank row scenario: two imports of the same transaction. The second one should be detected and filtered.
        bank_statement = [
            # Stationery payment
            {"date": "2026-06-08", "amount": -170.00, "reference": "STATIONERY PALACE", "fitid": "FITID-TC-001", "matched_to": "TC-SI-001"},
            # Megacorp payment (£5,400)
            {"date": "2026-06-20", "amount": 5400.00, "reference": "MEGACORP UK INVOICE TC-2026-101", "fitid": "FITID-TC-002", "matched_to": "TC-VI-001"},
            # Bank fee (Exempt)
            {"date": "2026-06-30", "amount": -10.00, "reference": "BANK CHARGE", "fitid": "FITID-TC-003", "matched_to": "TC-BC-001"},
            
            # Re-import test rows (to prove CSV idempotency)
            # The system must reject the duplicate bank transaction with FITID-TC-002 if imported again.
            {"date": "2026-06-20", "amount": 5400.00, "reference": "MEGACORP UK INVOICE TC-2026-101", "fitid": "FITID-TC-002-DUP", "matched_to": "TC-VI-001", "is_duplicate_import": True}
        ]

        transactions.append({
            "type": "BankCharge",
            "id": "TC-BC-001",
            "date": "2026-06-30",
            "department": "Operations",
            "lines": [
                {"account": "6500", "description": "Monthly Account Maintenance", "net": 10.00, "vat_code": "EX", "vat": 0.00}
            ],
            "status": "Posted"
        })

        return {
            "metadata": metadata,
            "transactions": transactions,
            "bank_statement": bank_statement
        }

    def build_expected_outcomes(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates expected accounting outcomes from transactions to form the golden results."""
        transactions = company_data["transactions"]
        bank_statement = company_data["bank_statement"]
        tenant_id = company_data["metadata"]["id"]

        # 1. Generate double entry journal lines
        # Rule: Every transaction has corresponding double entry.
        # Purchases (SupplierInvoice):
        #   Dr Expense/Asset Account (with net amount)
        #   Dr VAT Control Account 2200 (with VAT amount)
        #   Cr Aged Creditors 2100 (with total net + VAT)
        # Sales (SalesInvoice):
        #   Dr Aged Debtors (or bank directly, but we route through debtors to be standard) -> Dr 1200 or Dr Accounts Receivable (let's say 1200 is used for cash sales, but standard invoices Dr Aged Debtors / Accounts Receivable)
        #   Wait, we need an Aged Debtors account! Let's check if we defined one.
        #   In our chart, we didn't explicitly name an accounts receivable code. Let's add code "1100" as "Aged Debtors" (Accounts Receivable) in Assets!
        #   Let's check:
        #   1100: Aged Debtors
        #   Let's assume "1100" is Aged Debtors.
        #   So:
        #   Sales Invoices:
        #     Dr 1100 Aged Debtors (total net + VAT)
        #     Cr 4000/4010/4020 Revenue (net)
        #     Cr 2200 VAT Control (VAT)
        #   Sales Credit Note:
        #     Dr 4000/4010/4020 Revenue (net)
        #     Dr 2200 VAT Control (VAT)
        #     Cr 1100 Aged Debtors (total net + VAT)
        #   Employee Expense (reimbursed via creditors or DLA):
        #     Dr Expense Account (net)
        #     Dr 2200 VAT Control (VAT)
        #     Cr 2100 Aged Creditors (total)
        #   Bank Payments:
        #     Dr 2100 Aged Creditors (matching supplier invoice payment)
        #     Cr 1200 Bank Current Account
        #   Bank Receipts:
        #     Dr 1200 Bank Current Account
        #     Cr 1100 Aged Debtors (matching sales invoice customer payment)
        #   Director Transaction:
        #     Dr 2400 Sarah DLA (gym payment)
        #     Cr 1200 Bank Current Account (personal expense paid from bank)
        
        # Let's map account codes dynamically
        aged_debtors_code = "1100" # We will add this to the chart below
        aged_creditors_code = "2100"
        bank_code = "1200"
        vat_code = "2200"
        dla_code = "2400"
        
        journal_postings = []
        
        # Track balances to verify trial balance
        tb_balances = {}
        for code in CHART_OF_ACCOUNTS:
            tb_balances[code] = 0.0
        tb_balances[aged_debtors_code] = 0.0 # Make sure aged debtors is in balances

        # Process manual journals
        for tx in transactions:
            if tx["status"] in ("Posted", "RequiresReview"): # Director transactions also affect ledger once recorded/approved
                tx_id = tx["id"]
                tx_date = tx["date"]
                dept = tx.get("department", "Head Office")

                if tx["type"] == "ManualJournal":
                    lines = []
                    for line in tx["lines"]:
                        acc = line["account"]
                        deb = line["debit"]
                        cred = line["credit"]
                        lines.append({
                            "account_code": acc,
                            "debit": deb,
                            "credit": cred,
                            "vat_code": line.get("vat_code", "OS"),
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + deb - cred
                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "ManualJournal",
                        "description": tx["description"],
                        "lines": lines
                    })

                elif tx["type"] == "SupplierInvoice":
                    # Dr Expense / Asset (net)
                    # Dr VAT (vat)
                    # Cr Aged Creditors (total)
                    net_sum = 0.0
                    vat_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        vat_amt = line["vat"]
                        acc = line["account"]
                        net_sum += net
                        vat_sum += vat_amt
                        
                        # Dr Expense
                        lines.append({
                            "account_code": acc,
                            "debit": net,
                            "credit": 0.0,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + net
                        
                        # Dr VAT Control
                        if vat_amt > 0:
                            lines.append({
                                "account_code": vat_code,
                                "debit": vat_amt,
                                "credit": 0.0,
                                "vat_code": line["vat_code"],
                                "department": dept
                            })
                            tb_balances[vat_code] = tb_balances.get(vat_code, 0.0) + vat_amt

                    # Cr Aged Creditors
                    total = net_sum + vat_sum
                    lines.append({
                        "account_code": aged_creditors_code,
                        "debit": 0.0,
                        "credit": total,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_creditors_code] = tb_balances.get(aged_creditors_code, 0.0) - total

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "SupplierInvoice",
                        "description": f"Purchase from {tx['supplier']} - Inv {tx['invoice_number']}",
                        "lines": lines
                    })

                elif tx["type"] == "SalesInvoice":
                    # Dr Aged Debtors (total)
                    # Cr Sales Revenue (net)
                    # Cr VAT Control (vat)
                    net_sum = 0.0
                    vat_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        vat_amt = line["vat"]
                        acc = line["account"]
                        net_sum += net
                        vat_sum += vat_amt
                        
                        # Cr Sales
                        lines.append({
                            "account_code": acc,
                            "debit": 0.0,
                            "credit": net,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) - net
                        
                        # Cr VAT Control
                        if vat_amt > 0:
                            lines.append({
                                "account_code": vat_code,
                                "debit": 0.0,
                                "credit": vat_amt,
                                "vat_code": line["vat_code"],
                                "department": dept
                            })
                            tb_balances[vat_code] = tb_balances.get(vat_code, 0.0) - vat_amt

                    # Dr Aged Debtors
                    total = net_sum + vat_sum
                    lines.append({
                        "account_code": aged_debtors_code,
                        "debit": total,
                        "credit": 0.0,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_debtors_code] = tb_balances.get(aged_debtors_code, 0.0) + total

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "SalesInvoice",
                        "description": f"Sale to {tx['customer']} - Inv {tx['invoice_number']}",
                        "lines": lines
                    })

                elif tx["type"] == "SalesCreditNote":
                    # Dr Sales Revenue (net)
                    # Dr VAT Control (vat)
                    # Cr Aged Debtors (total)
                    net_sum = 0.0
                    vat_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        vat_amt = line["vat"]
                        acc = line["account"]
                        net_sum += net
                        vat_sum += vat_amt
                        
                        # Dr Sales
                        lines.append({
                            "account_code": acc,
                            "debit": net,
                            "credit": 0.0,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + net
                        
                        # Dr VAT Control
                        if vat_amt > 0:
                            lines.append({
                                "account_code": vat_code,
                                "debit": vat_amt,
                                "credit": 0.0,
                                "vat_code": line["vat_code"],
                                "department": dept
                            })
                            tb_balances[vat_code] = tb_balances.get(vat_code, 0.0) + vat_amt

                    # Cr Aged Debtors
                    total = net_sum + vat_sum
                    lines.append({
                        "account_code": aged_debtors_code,
                        "debit": 0.0,
                        "credit": total,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_debtors_code] = tb_balances.get(aged_debtors_code, 0.0) - total

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "SalesCreditNote",
                        "description": f"Credit note to {tx['customer']} - Ref {tx.get('credit_note_number', 'CN')}",
                        "lines": lines
                    })

                elif tx["type"] == "EmployeeExpense":
                    # Dr Expense (net)
                    # Dr VAT (vat)
                    # Cr Aged Creditors (total)
                    net_sum = 0.0
                    vat_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        vat_amt = line.get("vat", 0.0)
                        acc = line["account"]
                        net_sum += net
                        vat_sum += vat_amt
                        
                        # Dr Expense
                        lines.append({
                            "account_code": acc,
                            "debit": net,
                            "credit": 0.0,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + net
                        
                        # Dr VAT
                        if vat_amt > 0:
                            lines.append({
                                "account_code": vat_code,
                                "debit": vat_amt,
                                "credit": 0.0,
                                "vat_code": line["vat_code"],
                                "department": dept
                            })
                            tb_balances[vat_code] = tb_balances.get(vat_code, 0.0) + vat_amt

                    # Cr Aged Creditors
                    total = net_sum + vat_sum
                    lines.append({
                        "account_code": aged_creditors_code,
                        "debit": 0.0,
                        "credit": total,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_creditors_code] = tb_balances.get(aged_creditors_code, 0.0) - total

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "EmployeeExpense",
                        "description": f"Expense claim from {tx['claimant']}",
                        "lines": lines
                    })

                elif tx["type"] == "DirectorTransaction":
                    # Sarah DLA gym payment
                    # Dr 2400 Sarah DLA (net)
                    # Cr 1200 Bank (Wait, bank gets posted via bank reconciliations below!
                    # Wait, if we post the bank cash movement from the bank statement line, then the bank statement payment will credit Bank (1200) and debit DLA (2400) or Aged Creditors (2100).
                    # If so, the transaction document itself should just represent the accrual or DLA adjustment.
                    # For a Director Transaction that is paid directly on company card:
                    # Let's post it when bank line is matched, OR we can record it as:
                    # Dr 2400 (DLA)
                    # Cr 2100 (Aged Creditors)
                    # And then payment: Dr 2100 (Aged Creditors), Cr 1200 (Bank)
                    # Yes! Routing all card expenses/bills through Creditors/Aged Creditors ensures we have a clear creditor ledger.
                    net_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        acc = line["account"]
                        net_sum += net
                        
                        # Dr DLA
                        lines.append({
                            "account_code": acc,
                            "debit": net,
                            "credit": 0.0,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + net

                    # Cr Aged Creditors
                    lines.append({
                        "account_code": aged_creditors_code,
                        "debit": 0.0,
                        "credit": net_sum,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_creditors_code] = tb_balances.get(aged_creditors_code, 0.0) - net_sum

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "DirectorTransaction",
                        "description": f"Director transaction: {tx['director']} personal gym",
                        "lines": lines
                    })

                elif tx["type"] == "BankCharge":
                    # Dr 6500 Bank Fees
                    # Cr 2100 Aged Creditors (or bank directly? Let's Cr Aged Creditors and match)
                    net_sum = 0.0
                    lines = []
                    for line in tx["lines"]:
                        net = line["net"]
                        acc = line["account"]
                        net_sum += net
                        
                        # Dr Expense
                        lines.append({
                            "account_code": acc,
                            "debit": net,
                            "credit": 0.0,
                            "vat_code": line["vat_code"],
                            "department": dept
                        })
                        tb_balances[acc] = tb_balances.get(acc, 0.0) + net

                    # Cr Aged Creditors
                    lines.append({
                        "account_code": aged_creditors_code,
                        "debit": 0.0,
                        "credit": net_sum,
                        "vat_code": "OS",
                        "department": dept
                    })
                    tb_balances[aged_creditors_code] = tb_balances.get(aged_creditors_code, 0.0) - net_sum

                    journal_postings.append({
                        "source_id": tx_id,
                        "date": tx_date,
                        "type": "BankCharge",
                        "description": "Bank monthly charge",
                        "lines": lines
                    })

        # Process Bank Statement Payments (representing cash reconciliation journal entries)
        # For each bank statement row, we match to a transaction, which relieves Aged Creditors/Debtors.
        # Payment (-amount):
        #   Dr Aged Creditors 2100 (or DLA/Expense if direct)
        #   Cr Bank 1200
        # Receipt (+amount):
        #   Dr Bank 1200
        #   Cr Aged Debtors 1100
        for row in bank_statement:
            if row.get("is_duplicate_import"):
                continue # Skip duplicate imports in ledger postings calculations
            
            amt = row["amount"]
            ref = row["reference"]
            matched_id = row["matched_to"]
            row_date = row["date"]
            
            # Find the matched transaction to get the department
            matched_tx = next((t for t in transactions if t["id"] == matched_id), None)
            dept = matched_tx.get("department", "Head Office") if matched_tx else "Head Office"

            lines = []
            if amt < 0:
                # Cash outflow (paying a bill or reimbursing expense)
                val = abs(amt)
                
                # Dr Aged Creditors
                lines.append({
                    "account_code": aged_creditors_code,
                    "debit": val,
                    "credit": 0.0,
                    "vat_code": "OS",
                    "department": dept
                })
                tb_balances[aged_creditors_code] = tb_balances.get(aged_creditors_code, 0.0) + val
                
                # Cr Bank Account
                lines.append({
                    "account_code": bank_code,
                    "debit": 0.0,
                    "credit": val,
                    "vat_code": "OS",
                    "department": dept
                })
                tb_balances[bank_code] = tb_balances.get(bank_code, 0.0) - val
                
                journal_postings.append({
                    "source_id": f"BANK-PAY-{row['fitid']}",
                    "date": row_date,
                    "type": "BankPayment",
                    "description": f"Bank payment match: {ref}",
                    "lines": lines
                })
            else:
                # Cash inflow (customer paying invoice)
                val = amt
                
                # Dr Bank Account
                lines.append({
                    "account_code": bank_code,
                    "debit": val,
                    "credit": 0.0,
                    "vat_code": "OS",
                    "department": dept
                })
                tb_balances[bank_code] = tb_balances.get(bank_code, 0.0) + val
                
                # Cr Aged Debtors
                lines.append({
                    "account_code": aged_debtors_code,
                    "debit": 0.0,
                    "credit": val,
                    "vat_code": "OS",
                    "department": dept
                })
                tb_balances[aged_debtors_code] = tb_balances.get(aged_debtors_code, 0.0) - val
                
                journal_postings.append({
                    "source_id": f"BANK-REC-{row['fitid']}",
                    "date": row_date,
                    "type": "BankReceipt",
                    "description": f"Bank receipt match: {ref}",
                    "lines": lines
                })

        # Round all balances to 2 decimal places to prevent float errors
        tb_balances = {k: round(v, 2) for k, v in tb_balances.items()}
        
        # Calculate P&L and Balance Sheet from Trial Balance
        profit_and_loss = {}
        balance_sheet = {}
        net_profit = 0.0
        
        for code, bal in tb_balances.items():
            # Check if code is in our chart or if it's the added Aged Debtors code 1100
            chart_entry = CHART_OF_ACCOUNTS.get(code)
            if code == aged_debtors_code:
                chart_entry = {"name": "Aged Debtors", "category": "Asset", "canonical": "Trade Receivables"}
                
            if not chart_entry:
                continue
                
            category = chart_entry["category"]
            
            if category in ("Revenue", "Cost of Sales", "Expense"):
                # For P&L:
                # Revenue balances are credit (negative). We show revenue positive in reports.
                # Expenses/CoS are debit (positive).
                if category == "Revenue":
                    profit_and_loss[code] = -bal
                    net_profit += -bal
                else:
                    profit_and_loss[code] = bal
                    net_profit -= bal
            else:
                # For Balance Sheet:
                # Assets are debit (positive). Liabilities/Equity are credit (negative).
                balance_sheet[code] = bal

        # Add Retained Earnings adjustment for current period net profit
        # So that the balance sheet matches the trial balance and balances!
        retained_earnings_current = round(net_profit, 2)
        balance_sheet["3200"] = round(balance_sheet.get("3200", 0.0) + retained_earnings_current, 2)

        # Recalculate Aged Debtors and Creditors directly from invoices & payments
        # Let's build aged debtors: KCC has invoice CP-VI-001 (£25,000) and CN CP-CN-001 (£1,500), paid £20,000. Balance is £3,500.
        # Dent has invoice CP-VI-002 (£8,000), paid £8,500. Balance is -£500 (overpayment creditor / credit balance in debtors).
        # Total debtors: £3,000. Let's verify with tb_balances["1100"] which should be £3,000.
        # Aged creditors: Lumina Invoice (£6,000), paid £6,000. Balance: 0.
        # CareStaff Invoice (£12,000), paid £12,000. Balance: 0.
        # British Gas Invoice (£420), unpaid. Balance: £420.
        # Staff John mileage (£120), paid £120. Balance: 0.
        # Director Sarah DLA personal Gym (£80), paid £80. Balance: 0.
        # Bank charge invoice (£25), paid £25. Balance: 0.
        # Total Creditors: £420. Let's check tb_balances["2100"] which should be -£420 (credit balance of £420).
        
        # Calculate VAT Summary
        # Sales VAT (Output VAT): sum of VAT credits on sales.
        # Purchase VAT (Input VAT): sum of VAT debits on purchases.
        # Net VAT: Output VAT - Input VAT.
        output_vat = 0.0
        input_vat = 0.0
        for tx in transactions:
            if tx["status"] in ("Posted", "RequiresReview"):
                if tx["type"] == "SalesInvoice":
                    for line in tx["lines"]:
                        output_vat += line["vat"]
                elif tx["type"] == "SalesCreditNote":
                    for line in tx["lines"]:
                        output_vat -= line["vat"] # credit note reduces output VAT
                elif tx["type"] in ("SupplierInvoice", "EmployeeExpense"):
                    for line in tx["lines"]:
                        input_vat += line["vat"]
                        
        output_vat = round(output_vat, 2)
        input_vat = round(input_vat, 2)
        net_vat_payable = round(output_vat - input_vat, 2)

        # VAT Control Account balance should equal net VAT payable/reclaimable (Cr balance if payable)
        # Let's verify: tb_balances["2200"] should be input - output.
        # If output_vat is 2,000 and input_vat is 1,120, net_vat_payable is +880 (liability, Cr 880).
        # tb_balances["2200"] will be debits (input = 1,120) - credits (output = 2,000) = -880 (Cr 880). Correct!

        # Departmental reporting allocation
        # We group profit/loss accounts by department.
        departmental_pnl = {}
        for dept in company_data["metadata"]["departments"]:
            departmental_pnl[dept] = {"Revenue": 0.0, "Cost of Sales": 0.0, "Expense": 0.0, "Net": 0.0}

        for tx in transactions:
            if tx["status"] in ("Posted", "RequiresReview"):
                dept = tx.get("department", "Head Office")
                if dept not in departmental_pnl:
                    departmental_pnl[dept] = {"Revenue": 0.0, "Cost of Sales": 0.0, "Expense": 0.0, "Net": 0.0}
                    
                if tx["type"] == "ManualJournal":
                    for line in tx["lines"]:
                        acc = line["account"]
                        chart_entry = CHART_OF_ACCOUNTS.get(acc)
                        if chart_entry:
                            cat = chart_entry["category"]
                            val = line["debit"] - line["credit"]
                            l_dept = line.get("department", dept)
                            if l_dept not in departmental_pnl:
                                departmental_pnl[l_dept] = {"Revenue": 0.0, "Cost of Sales": 0.0, "Expense": 0.0, "Net": 0.0}
                            if cat == "Revenue":
                                departmental_pnl[l_dept]["Revenue"] += -val
                                departmental_pnl[l_dept]["Net"] += -val
                            elif cat == "Cost of Sales":
                                departmental_pnl[l_dept]["Cost of Sales"] += val
                                departmental_pnl[l_dept]["Net"] -= val
                            elif cat == "Expense":
                                departmental_pnl[l_dept]["Expense"] += val
                                departmental_pnl[l_dept]["Net"] -= val
                else:
                    for line in tx["lines"]:
                        acc = line["account"]
                        chart_entry = CHART_OF_ACCOUNTS.get(acc)
                        if chart_entry:
                            cat = chart_entry["category"]
                            net = line["net"]
                            if tx["type"] == "SalesInvoice":
                                departmental_pnl[dept]["Revenue"] += net
                                departmental_pnl[dept]["Net"] += net
                            elif tx["type"] == "SalesCreditNote":
                                departmental_pnl[dept]["Revenue"] -= net
                                departmental_pnl[dept]["Net"] -= net
                            elif tx["type"] in ("SupplierInvoice", "EmployeeExpense", "BankCharge"):
                                if cat == "Cost of Sales":
                                    departmental_pnl[dept]["Cost of Sales"] += net
                                    departmental_pnl[dept]["Net"] -= net
                                elif cat == "Expense":
                                    departmental_pnl[dept]["Expense"] += net
                                    departmental_pnl[dept]["Net"] -= net

        # Round all departmental values
        for d in departmental_pnl:
            for k in departmental_pnl[d]:
                departmental_pnl[d][k] = round(departmental_pnl[d][k], 2)

        return {
            "journal_postings": journal_postings,
            "trial_balance": tb_balances,
            "profit_and_loss": profit_and_loss,
            "balance_sheet": balance_sheet,
            "vat_summary": {
                "output_vat": output_vat,
                "input_vat": input_vat,
                "net_vat_payable": net_vat_payable
            },
            "departmental_pnl": departmental_pnl,
            "reconciled_bank_balance": sum(row["amount"] for row in bank_statement if not row.get("is_duplicate_import")),
            "expected_debtors_balance": tb_balances.get(aged_debtors_code, 0.0),
            "expected_creditors_balance": -tb_balances.get(aged_creditors_code, 0.0), # Creditors is credit (negative), aged reports show positive
        }

    def generate_rejection_scenarios(self) -> List[Dict[str, Any]]:
        """Generates rejection and validation failure scenarios."""
        return [
            {
                "id": "REJ-001",
                "scenario": "Closed period edit attempt",
                "input": {
                    "action": "edit",
                    "period": "2026-05",  # Let's say May 2026 is closed
                    "journal_id": "CP-MJ-001",
                    "payload": {"description": "Illegal post-close edit"}
                },
                "expected_result": "Rejected",
                "expected_message": "Cannot modify transactions in a closed accounting period."
            },
            {
                "id": "REJ-002",
                "scenario": "Cross-tenant access attempt",
                "input": {
                    "user_role": "tenant_staff",
                    "user_tenant": "tenant-consultco",
                    "target_tenant": "tenant-careco",
                    "action": "view_journal",
                    "target_id": "CP-MJ-001"
                },
                "expected_result": "Rejected",
                "expected_message": "Access denied. Tenant isolation boundary violated."
            },
            {
                "id": "REJ-003",
                "scenario": "Self-approval of restricted claim",
                "input": {
                    "user": "Staff John",
                    "claim_id": "CP-EE-001",
                    "action": "approve",
                    "claimant": "Staff John"
                },
                "expected_result": "Rejected",
                "expected_message": "Users are not permitted to approve their own expense claims or invoices."
            },
            {
                "id": "REJ-004",
                "scenario": "Unbalanced manual journal entry",
                "input": {
                    "type": "ManualJournal",
                    "date": "2026-06-15",
                    "lines": [
                        {"account": "1200", "debit": 100.00, "credit": 0.00},
                        {"account": "3200", "debit": 0.00, "credit": 99.00}  # Off by 1.00!
                    ]
                },
                "expected_result": "Rejected",
                "expected_message": "Journal is unbalanced. Total debits must equal total credits."
            },
            {
                "id": "REJ-005",
                "scenario": "Duplicate CSV bank statement import fitid",
                "input": {
                    "action": "import_csv",
                    "rows": [
                        {"date": "2026-06-20", "amount": 5400.00, "reference": "MEGACORP UK INVOICE TC-2026-101", "fitid": "FITID-TC-002"}
                    ]
                },
                "expected_result": "IgnoredDuplicate",
                "expected_message": "Transaction FITID-TC-002 already imported. Skipping to maintain idempotency."
            },
            {
                "id": "REJ-006",
                "scenario": "Malformed bank CSV columns",
                "input": {
                    "action": "import_csv",
                    "csv_data": "WrongHeader1,WrongHeader2\n2026-06-20,5400.00"
                },
                "expected_result": "Rejected",
                "expected_message": "Invalid CSV file format. Required headers: Date, Amount, Reference, FITID are missing."
            }
        ]


# Export helper for standard UK Chart of Accounts
CHART_OF_ACCOUNTS[ "1100"] = {"name": "Aged Debtors", "category": "Asset", "canonical": "Trade Receivables"}
