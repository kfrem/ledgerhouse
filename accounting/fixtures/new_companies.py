import json
from pathlib import Path

def generate_tech_co():
    """Generates TechCo Software Ltd (SaaS subscription model) fixtures."""
    metadata = {
        "id": "tenant-techco",
        "name": "TechCo Software Ltd",
        "vat_registered": True,
        "departments": ["Engineering", "Sales", "Support"],
        "currency": "GBP"
    }

    # Journal postings (seeded except BankReceipt/BankPayment)
    journal_postings = [
        # Opening balances
        {
            "source_id": "TECH-MJ-001",
            "date": "2026-06-01",
            "type": "ManualJournal",
            "description": "Opening balances post migration",
            "lines": [
                {"account_code": "1200", "debit": 10000.00, "credit": 0.00, "vat_code": "OS", "department": "Engineering"},
                {"account_code": "3200", "debit": 0.00, "credit": 10000.00, "vat_code": "OS", "department": "Engineering"}
            ]
        },
        # Sales Invoice (SaaS Subscription) - Standard Rated
        {
            "source_id": "TECH-SI-101",
            "date": "2026-06-10",
            "type": "SalesInvoice",
            "description": "Monthly SaaS subscription billing",
            "lines": [
                {"account_code": "1100", "debit": 1200.00, "credit": 0.00, "vat_code": "SR", "department": "Sales"},
                {"account_code": "4000", "debit": 0.00, "credit": 1000.00, "vat_code": "SR", "department": "Sales"},
                {"account_code": "2200", "debit": 0.00, "credit": 200.00, "vat_code": "SR", "department": "Sales"}
            ]
        },
        # Supplier Invoice (Hosting costs) - Standard Rated
        {
            "source_id": "TECH-PI-101",
            "date": "2026-06-12",
            "type": "SupplierInvoice",
            "description": "Cloud hosting services",
            "lines": [
                {"account_code": "6200", "debit": 500.00, "credit": 0.00, "vat_code": "SR", "department": "Engineering"},
                {"account_code": "2200", "debit": 100.00, "credit": 0.00, "vat_code": "SR", "department": "Engineering"},
                {"account_code": "2100", "debit": 0.00, "credit": 600.00, "vat_code": "SR", "department": "Engineering"}
            ]
        },
        # Employee Expense (Mileage) - Exempt
        {
            "source_id": "TECH-EE-101",
            "date": "2026-06-15",
            "type": "EmployeeExpense",
            "description": "Travel expenses customer visit",
            "lines": [
                {"account_code": "6310", "debit": 150.00, "credit": 0.00, "vat_code": "EX", "department": "Support"},
                {"account_code": "2100", "debit": 0.00, "credit": 150.00, "vat_code": "EX", "department": "Support"}
            ]
        },
        # Bank Fee - Outside Scope
        {
            "source_id": "TECH-BC-001",
            "date": "2026-06-30",
            "type": "BankCharge",
            "description": "Monthly Account Charge",
            "lines": [
                {"account_code": "6500", "debit": 15.00, "credit": 0.00, "vat_code": "OS", "department": "Support"},
                {"account_code": "2100", "debit": 0.00, "credit": 15.00, "vat_code": "OS", "department": "Support"}
            ]
        }
    ]

    # Bank statement transactions
    bank_statement = [
        {"date": "2026-06-12", "amount": 1200.00, "reference": "TECH-SI-101 DEPOSIT", "fitid": "FITID-TECH-001", "matched_to": "TECH-SI-101"},
        {"date": "2026-06-15", "amount": -600.00, "reference": "HOSTING SERVICES PAY", "fitid": "FITID-TECH-002", "matched_to": "TECH-PI-101"},
        {"date": "2026-06-30", "amount": -15.00, "reference": "MONTHLY ACCOUNT FEE", "fitid": "FITID-TECH-003", "matched_to": "TECH-BC-001"}
    ]

    # Reconciled bank balance = 10000 (opening) + 1200 (receipt) - 600 (payment) - 15 (bank charge) = 10585
    # Unpaid employee expense of 150 remains on 2100 (Aged Creditors)
    expected_results = {
        "journal_postings": journal_postings,
        "trial_balance": {
            "1200": 10585.00,
            "1100": 0.00,
            "2100": -150.00,
            "2200": -100.00,
            "3200": -10000.00,
            "4000": -1000.00,
            "6200": 500.00,
            "6310": 150.00,
            "6500": 15.00
        },
        "reconciled_bank_balance": 10585.00,
        "expected_debtors_balance": 0.00,
        "expected_creditors_balance": 150.00,
        "vat_summary": {
            "output_vat": 200.00,
            "input_vat": 100.00,
            "net_vat_payable": 100.00
        }
    }

    return {
        "metadata": metadata,
        "fixtures": {
            "transactions": journal_postings,
            "bank_statement": bank_statement
        },
        "expected_results": expected_results
    }

def generate_logistics_co():
    """Generates LogisticsCo Transport Ltd (hauling and fuel mixed model)."""
    metadata = {
        "id": "tenant-logisticsco",
        "name": "LogisticsCo Transport Ltd",
        "vat_registered": True,
        "departments": ["Domestic", "International", "Fleet Management"],
        "currency": "GBP"
    }

    journal_postings = [
        # Opening balances
        {
            "source_id": "LOG-MJ-001",
            "date": "2026-06-01",
            "type": "ManualJournal",
            "description": "Opening balances post migration",
            "lines": [
                {"account_code": "1200", "debit": 25000.00, "credit": 0.00, "vat_code": "OS", "department": "Fleet Management"},
                {"account_code": "3200", "debit": 0.00, "credit": 25000.00, "vat_code": "OS", "department": "Fleet Management"}
            ]
        },
        # Sales Invoice (Domestic Haulage) - Standard Rated
        {
            "source_id": "LOG-SI-101",
            "date": "2026-06-10",
            "type": "SalesInvoice",
            "description": "Domestic cargo delivery",
            "lines": [
                {"account_code": "1100", "debit": 6000.00, "credit": 0.00, "vat_code": "SR", "department": "Domestic"},
                {"account_code": "4000", "debit": 0.00, "credit": 5000.00, "vat_code": "SR", "department": "Domestic"},
                {"account_code": "2200", "debit": 0.00, "credit": 1000.00, "vat_code": "SR", "department": "Domestic"}
            ]
        },
        # Sales Invoice (International Haulage) - Zero Rated
        {
            "source_id": "LOG-SI-102",
            "date": "2026-06-12",
            "type": "SalesInvoice",
            "description": "Cross-border cargo delivery",
            "lines": [
                {"account_code": "1100", "debit": 8000.00, "credit": 0.00, "vat_code": "ZR", "department": "International"},
                {"account_code": "4010", "debit": 0.00, "credit": 8000.00, "vat_code": "ZR", "department": "International"}
            ]
        },
        # Supplier Invoice (Fuel expense) - Reduced Rated (5% for business heating/fuel sometimes, or Standard 20%. Let's use 5% RR to test RR resolution!)
        {
            "source_id": "LOG-PI-101",
            "date": "2026-06-14",
            "type": "SupplierInvoice",
            "description": "Bulk diesel purchase",
            "lines": [
                {"account_code": "5100", "debit": 4000.00, "credit": 0.00, "vat_code": "RR", "department": "Fleet Management"},
                {"account_code": "2200", "debit": 200.00, "credit": 0.00, "vat_code": "RR", "department": "Fleet Management"},
                {"account_code": "2100", "debit": 0.00, "credit": 4200.00, "vat_code": "RR", "department": "Fleet Management"}
            ]
        }
    ]

    bank_statement = [
        {"date": "2026-06-15", "amount": 6000.00, "reference": "DOMESTIC DELIV RECEIPT", "fitid": "FITID-LOG-001", "matched_to": "LOG-SI-101"},
        {"date": "2026-06-18", "amount": -4200.00, "reference": "BULK DIESEL FUEL PMT", "fitid": "FITID-LOG-002", "matched_to": "LOG-PI-101"}
    ]

    # Reconciled bank balance = 25000 (opening) + 6000 (receipt) - 4200 (payment) = 26800.00
    # Unpaid international sales invoice of 8000 remains on 1100 (Aged Debtors)
    expected_results = {
        "journal_postings": journal_postings,
        "trial_balance": {
            "1200": 26800.00,
            "1100": 8000.00,
            "2100": 0.00,
            "2200": -800.00,
            "3200": -25000.00,
            "4000": -5000.00,
            "4010": -8000.00,
            "5100": 4000.00
        },
        "reconciled_bank_balance": 26800.00,
        "expected_debtors_balance": 8000.00,
        "expected_creditors_balance": 0.00,
        "vat_summary": {
            "output_vat": 1000.00,
            "input_vat": 200.00,
            "net_vat_payable": 800.00
        }
    }

    return {
        "metadata": metadata,
        "fixtures": {
            "transactions": journal_postings,
            "bank_statement": bank_statement
        },
        "expected_results": expected_results
    }

def generate_charity_co():
    """Generates CharityCo Foundation (grants, donations, non-profit outside scope model)."""
    metadata = {
        "id": "tenant-charityco",
        "name": "CharityCo Foundation",
        "vat_registered": True, # Still registered to reclaim input VAT on charitable goods
        "departments": ["Grant Projects", "Community Relief", "Management"],
        "currency": "GBP"
    }

    journal_postings = [
        # Opening balances
        {
            "source_id": "CHA-MJ-001",
            "date": "2026-06-01",
            "type": "ManualJournal",
            "description": "Opening balances post migration",
            "lines": [
                {"account_code": "1200", "debit": 5000.00, "credit": 0.00, "vat_code": "OS", "department": "Management"},
                {"account_code": "3200", "debit": 0.00, "credit": 5000.00, "vat_code": "OS", "department": "Management"}
            ]
        },
        # Public Grant Received (Outside Scope income)
        {
            "source_id": "CHA-SI-101",
            "date": "2026-06-05",
            "type": "SalesInvoice",
            "description": "Government Project Funding Grant",
            "lines": [
                {"account_code": "1100", "debit": 15000.00, "credit": 0.00, "vat_code": "OS", "department": "Grant Projects"},
                {"account_code": "4020", "debit": 0.00, "credit": 15000.00, "vat_code": "OS", "department": "Grant Projects"}
            ]
        },
        # Supplier Purchase (Community food supplies) - Zero Rated (charitable distribution)
        {
            "source_id": "CHA-PI-101",
            "date": "2026-06-08",
            "type": "SupplierInvoice",
            "description": "Food supplies for community kitchen",
            "lines": [
                {"account_code": "6000", "debit": 2000.00, "credit": 0.00, "vat_code": "ZR", "department": "Community Relief"},
                {"account_code": "2100", "debit": 0.00, "credit": 2000.00, "vat_code": "ZR", "department": "Community Relief"}
            ]
        }
    ]

    bank_statement = [
        {"date": "2026-06-10", "amount": 15000.00, "reference": "GOVT GRANT FUNDING", "fitid": "FITID-CHA-001", "matched_to": "CHA-SI-101"},
        {"date": "2026-06-12", "amount": -2000.00, "reference": "FOOD SUPPLIES CLEAR", "fitid": "FITID-CHA-002", "matched_to": "CHA-PI-101"}
    ]

    # Reconciled bank balance = 5000 (opening) + 15000 (receipt) - 2000 (payment) = 18000.00
    # All invoice matches clear Aged Debtors/Creditors to 0
    expected_results = {
        "journal_postings": journal_postings,
        "trial_balance": {
            "1200": 18000.00,
            "1100": 0.00,
            "2100": 0.00,
            "2200": 0.00,
            "3200": -5000.00,
            "4020": -15000.00,
            "6000": 2000.00
        },
        "reconciled_bank_balance": 18000.00,
        "expected_debtors_balance": 0.00,
        "expected_creditors_balance": 0.00,
        "vat_summary": {
            "output_vat": 0.00,
            "input_vat": 0.00,
            "net_vat_payable": 0.00
        }
    }

    return {
        "metadata": metadata,
        "fixtures": {
            "transactions": journal_postings,
            "bank_statement": bank_statement
        },
        "expected_results": expected_results
    }


def main():
    output_dir = Path(__file__).parent / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate and save TechCo
    tech_co = generate_tech_co()
    with open(output_dir / "tech_co.json", "w", encoding="utf-8") as f:
        json.dump(tech_co, f, indent=4)
    print("Saved tech_co.json")

    # Generate and save LogisticsCo
    logistics_co = generate_logistics_co()
    with open(output_dir / "logistics_co.json", "w", encoding="utf-8") as f:
        json.dump(logistics_co, f, indent=4)
    print("Saved logistics_co.json")

    # Generate and save CharityCo
    charity_co = generate_charity_co()
    with open(output_dir / "charity_co.json", "w", encoding="utf-8") as f:
        json.dump(charity_co, f, indent=4)
    print("Saved charity_co.json")


if __name__ == "__main__":
    main()
