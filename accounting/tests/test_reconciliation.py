import json
import pytest
import uuid
from decimal import Decimal
from pathlib import Path
from django.db import connection, transaction
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, Journal, JournalLine, BankTransaction, BankReconciliation, ImportedFile
from ..middleware import tenant_context
from ..reconciliation import reconcile_transaction_to_invoice, verify_ledger_to_bank_balance
from ..bank_import import import_bank_csv


def load_fixture_file(filename: str):
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "generated"
    with open(fixtures_dir / filename, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.django_db(transaction=True)
class BankReconciliationTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Nominal accounts
        self.acc_bank_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1200", name="Bank", category="Asset", canonical_taxonomy="Cash"
        )
        self.acc_debtors_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1100", name="Aged Debtors", category="Asset", canonical_taxonomy="Receivable"
        )
        self.acc_creditors_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="2100", name="Aged Creditors", category="Liability", canonical_taxonomy="Payable"
        )
        self.acc_expense_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="6000", name="Expense", category="Expense", canonical_taxonomy="Operating Expense"
        )
        self.acc_revenue_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="4000", name="Sales", category="Revenue", canonical_taxonomy="Operating Revenue"
        )

    def test_reconcile_supplier_invoice(self):
        """Verify matching a negative bank transaction to a SupplierInvoice clears it against 2100."""
        with tenant_context(self.tenant_a.id):
            # 1. Create a balanced SupplierInvoice journal (debit Expense, credit Aged Creditors)
            with transaction.atomic():
                j_invoice = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Office Supplies Invoice", source_type="SupplierInvoice", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_expense_a, debit=Decimal("200.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_creditors_a, debit=Decimal("0.00"), credit=Decimal("200.00"))

            # 2. Create imported bank file and transaction (negative payment)
            imp_file = ImportedFile.objects.create(tenant=self.tenant_a, filename="stmt.csv", raw_content="raw", file_hash="hash1")
            bank_tx = BankTransaction.objects.create(
                tenant=self.tenant_a, imported_file=imp_file, date="2026-06-03", amount=Decimal("-200.00"), reference="Supplies payment", fitid="FITID-S1"
            )

            # 3. Match and clear
            link, clearing_j = reconcile_transaction_to_invoice(self.tenant_a, bank_tx, j_invoice, "Godfred")
            
            assert link.matched_journal == j_invoice
            assert clearing_j.source_type == "BankPayment"
            assert clearing_j.source_id == "FITID-S1"

            # Verify clearing double-entry (Debit 2100 Aged Creditors, Credit 1200 Bank)
            lines = list(clearing_j.lines.order_by('id'))
            assert len(lines) == 2
            assert lines[0].account == self.acc_creditors_a
            assert lines[0].debit == Decimal("200.00")
            assert lines[0].credit == Decimal("0.00")
            
            assert lines[1].account == self.acc_bank_a
            assert lines[1].debit == Decimal("0.00")
            assert lines[1].credit == Decimal("200.00")

            # Check ledger-to-bank balance check matches
            balance_check = verify_ledger_to_bank_balance(self.tenant_a)
            assert balance_check["ledger_bank_balance"] == -200.00
            assert balance_check["statement_bank_balance"] == -200.00
            assert balance_check["reconciled"] is True

    def test_reconcile_sales_invoice(self):
        """Verify matching a positive bank transaction to a SalesInvoice clears it against 1100."""
        with tenant_context(self.tenant_a.id):
            # 1. Create a balanced SalesInvoice journal (debit Aged Debtors, credit Sales Revenue)
            with transaction.atomic():
                j_invoice = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Sales Invoice #123", source_type="SalesInvoice", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_debtors_a, debit=Decimal("500.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_revenue_a, debit=Decimal("0.00"), credit=Decimal("500.00"))

            # 2. Create imported bank transaction (positive receipt)
            imp_file = ImportedFile.objects.create(tenant=self.tenant_a, filename="stmt.csv", raw_content="raw", file_hash="hash2")
            bank_tx = BankTransaction.objects.create(
                tenant=self.tenant_a, imported_file=imp_file, date="2026-06-04", amount=Decimal("500.00"), reference="Inv #123 deposit", fitid="FITID-R1"
            )

            # 3. Match and clear
            link, clearing_j = reconcile_transaction_to_invoice(self.tenant_a, bank_tx, j_invoice, "Godfred")
            
            assert link.matched_journal == j_invoice
            assert clearing_j.source_type == "BankReceipt"
            assert clearing_j.source_id == "FITID-R1"

            # Verify clearing double-entry (Debit 1200 Bank, Credit 1100 Aged Debtors)
            lines = list(clearing_j.lines.order_by('id'))
            assert len(lines) == 2
            assert lines[0].account == self.acc_bank_a
            assert lines[0].debit == Decimal("500.00")
            assert lines[0].credit == Decimal("0.00")
            
            assert lines[1].account == self.acc_debtors_a
            assert lines[1].debit == Decimal("0.00")
            assert lines[1].credit == Decimal("500.00")

    def test_reconciliation_rls_isolation(self):
        """Verify RLS isolates BankReconciliation across tenants."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific RLS test.")

        # Create doc, transaction, invoice, and reconciliation under Tenant A
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j_invoice = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Rent invoice", source_type="SupplierInvoice", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_expense_a, debit=Decimal("100.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j_invoice, account=self.acc_creditors_a, debit=Decimal("0.00"), credit=Decimal("100.00"))
            
            imp_file = ImportedFile.objects.create(tenant=self.tenant_a, filename="stmt.csv", raw_content="raw", file_hash="hash_a")
            bank_tx = BankTransaction.objects.create(
                tenant=self.tenant_a, imported_file=imp_file, date="2026-06-02", amount=Decimal("-100.00"), reference="Pay", fitid="FITID-A1"
            )
            reconcile_transaction_to_invoice(self.tenant_a, bank_tx, j_invoice, "Godfred")

        # Tenant B should see nothing
        with tenant_context(self.tenant_b.id):
            assert BankReconciliation.objects.count() == 0

        # Tenant A should see their reconciliation
        with tenant_context(self.tenant_a.id):
            assert BankReconciliation.objects.count() == 1

    def test_reconcile_fixtures_100_percent(self):
        """Seed CareCo fixtures and fully reconcile all bank transactions. Verify ledger matches bank statements 100%."""
        fixture = load_fixture_file("care_provider.json")
        expected = fixture["expected_results"]

        tenant_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        tenant = Tenant.objects.create(id=tenant_id, name="CareCo Limited")

        # Seed nominal accounts
        nominals_map = {}
        for code in expected["trial_balance"].keys():
            category = "Asset"
            if code.startswith("2"):
                category = "Liability"
            elif code.startswith("3"):
                category = "Equity"
            elif code.startswith("4"):
                category = "Revenue"
            elif code.startswith("5"):
                category = "Cost of Sales"
            elif code.startswith("6"):
                category = "Expense"

            nominals_map[code] = NominalAccount.objects.create(
                tenant=tenant, code=code, name=f"Nominal {code}", category=category, canonical_taxonomy="Taxonomy"
            )

        # Seed invoices & journals
        with tenant_context(tenant.id):
            for jp in expected["journal_postings"]:
                # Seed everything except BankPayment/BankReceipt, which we generate dynamically during reconciliation
                if jp["type"] in ["BankPayment", "BankReceipt"]:
                    continue
                    
                with transaction.atomic():
                    j = Journal.objects.create(
                        tenant=tenant,
                        date=jp["date"],
                        description=jp["description"],
                        source_type=jp["type"],
                        source_id=jp["source_id"],
                        created_by="Godfred"
                    )
                    for line in jp["lines"]:
                        acc = NominalAccount.objects.get(tenant=tenant, code=line["account_code"])
                        JournalLine.objects.create(
                            tenant=tenant,
                            journal=j,
                            account=acc,
                            debit=Decimal(str(line["debit"])),
                            credit=Decimal(str(line["credit"])),
                            vat_code=line["vat_code"],
                            department=line["department"]
                        )

            # Import the bank statement CSV
            csv_lines = ["Date,Amount,Reference,FITID"]
            for tx in fixture["fixtures"]["bank_statement"]:
                csv_lines.append(f"{tx['date']},{tx['amount']},{tx['reference']},{tx['fitid']}")
            csv_content = "\n".join(csv_lines)

            # Switch connection role context
            import_bank_csv(tenant, "bank.csv", csv_content)
            
            # Match each transaction in bank statements to its expected matched invoice
            for tx in fixture["fixtures"]["bank_statement"]:
                # Lookup transaction
                bank_tx = BankTransaction.objects.get(tenant=tenant, fitid=tx["fitid"])
                
                # Match to invoice journal
                invoice_j = Journal.objects.get(tenant=tenant, source_id=tx["matched_to"])
                
                # Reconcile!
                reconcile_transaction_to_invoice(tenant, bank_tx, invoice_j, "Godfred")

            # Check that the ledger matches bank statements 100%!
            balance_check = verify_ledger_to_bank_balance(tenant, starting_balance=Decimal("50000.00"))
            assert balance_check["reconciled"] is True
            assert balance_check["ledger_bank_balance"] == float(expected["trial_balance"]["1200"])
            assert balance_check["statement_bank_balance"] == float(expected["reconciled_bank_balance"]) + 50000.0
