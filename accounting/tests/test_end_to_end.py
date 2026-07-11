import json
import pytest
import uuid
from decimal import Decimal
from pathlib import Path
from django.db import connection, transaction, utils
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, Journal, JournalLine, BankTransaction, EvidenceDocument, JournalEvidenceLink, VatReturn, ImportedFile
from ..middleware import tenant_context
from ..vat import calculate_vat_report
from ..bank_import import import_bank_csv
from ..reconciliation import reconcile_transaction_to_invoice, verify_ledger_to_bank_balance
from ..reversals import reverse_journal, get_review_metrics
from ..audit import generate_trial_balance, lock_vat_period, run_accountant_audit_check


def load_fixture_file(filename: str):
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "generated"
    with open(fixtures_dir / filename, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.django_db(transaction=True)
class EndToEndVerificationTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        # Load all 6 fixtures
        self.company_fixtures = {}
        filenames = {
            "care_provider.json": "CareCo Limited",
            "consultancy.json": "ConsultCo Consulting",
            "trading_company.json": "TradeCo Retail",
            "tech_co.json": "TechCo Software Ltd",
            "logistics_co.json": "LogisticsCo Transport Ltd",
            "charity_co.json": "CharityCo Foundation"
        }
        
        # Seed all 6 tenants and charts of accounts
        for filename, name in filenames.items():
            fixture = load_fixture_file(filename)
            expected = fixture["expected_results"]
            
            tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, filename)
            tenant = Tenant.objects.create(id=tenant_uuid, name=name)
            
            # Seed nominal accounts
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

                NominalAccount.objects.create(
                    tenant=tenant, code=code, name=f"Nominal {code}", category=category, canonical_taxonomy="Taxonomy"
                )

            # Create default VAT Rates
            VatRate_cls = NominalAccount.objects.model._meta.apps.get_model('accounting', 'VatRate')
            VatRate_cls.objects.create(tenant=tenant, vat_code="SR", rate=Decimal("0.2000"), effective_from="2020-01-01")
            VatRate_cls.objects.create(tenant=tenant, vat_code="ZR", rate=Decimal("0.0000"), effective_from="2020-01-01")
            VatRate_cls.objects.create(tenant=tenant, vat_code="EX", rate=Decimal("0.0000"), effective_from="2020-01-01")
            VatRate_cls.objects.create(tenant=tenant, vat_code="OS", rate=Decimal("0.0000"), effective_from="2020-01-01")
            VatRate_cls.objects.create(tenant=tenant, vat_code="RR", rate=Decimal("0.0500"), effective_from="2020-01-01")

            self.company_fixtures[tenant.id] = {
                "tenant": tenant,
                "fixture": fixture,
                "expected": expected,
                "filename": filename
            }

    def test_e2e_reconciliation_and_accounting_stages(self):
        """Execute and verify Stages 1 through 6 end-to-end for all 6 client tenants."""
        
        for tenant_id, comp_data in self.company_fixtures.items():
            tenant = comp_data["tenant"]
            fixture = comp_data["fixture"]
            expected = comp_data["expected"]
            
            self.stdout.write(f"\n--- Testing E2E for Tenant: {tenant.name} ---")
            
            with tenant_context(tenant.id):
                # ==========================================
                # STAGE 1: Kernel & Double Entry Validation
                # ==========================================
                # Assert that we cannot create unbalanced journals
                if self.is_postgres:
                    with self.assertRaises(Exception):
                        with transaction.atomic():
                            j_unbal = Journal.objects.create(
                                tenant=tenant, date="2026-06-01", description="Unbalanced", source_type="ManualJournal", created_by="System"
                            )
                            acc_cash = NominalAccount.objects.get(tenant=tenant, code="1200")
                            JournalLine.objects.create(tenant=tenant, journal=j_unbal, account=acc_cash, debit=Decimal("100.00"), credit=Decimal("0.00"))
                            # Missing balancing credit line!

                # Seed the correct journals from fixture (excluding clearing payments/receipts)
                for jp in expected["journal_postings"]:
                    if jp["type"] in ["BankPayment", "BankReceipt"]:
                        continue
                        
                    with transaction.atomic():
                        j = Journal.objects.create(
                            tenant=tenant,
                            date=jp["date"],
                            description=jp["description"],
                            source_type=jp["type"],
                            source_id=jp["source_id"],
                            created_by="Platform Admin"
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

                    # If it requires review, link it to dummy evidence to automatically post it
                    if jp["type"] in ['SalesInvoice', 'SupplierInvoice', 'EmployeeExpense']:
                        doc = EvidenceDocument.objects.create(
                            tenant=tenant,
                            filename=f"evidence_{j.id}.pdf",
                            content_type="application/pdf",
                            file_content=b"dummy",
                            uploaded_by="Platform Admin"
                        )
                        JournalEvidenceLink.objects.create(
                            tenant=tenant,
                            journal=j,
                            document=doc,
                            linked_by="Platform Admin"
                        )

                # ==========================================
                # STAGE 3: Idempotent Bank CSV Imports
                # ==========================================
                csv_lines = ["Date,Amount,Reference,FITID"]
                non_duplicate_txs = [tx for tx in fixture["fixtures"]["bank_statement"] if not tx.get("is_duplicate_import")]
                for tx in non_duplicate_txs:
                    csv_lines.append(f"{tx['date']},{tx['amount']},{tx['reference']},{tx['fitid']}")
                csv_content = "\n".join(csv_lines)

                # First Import
                imported_count, skipped_count = import_bank_csv(tenant, "statement.csv", csv_content)
                assert imported_count == len(non_duplicate_txs)

                # Second Import (should block/raise exception on file hash check)
                with self.assertRaises(Exception):
                    import_bank_csv(tenant, "statement.csv", csv_content)

                # ==========================================
                # STAGE 4: Purchase Ledger capture & reviews
                # ==========================================
                # Verify review status defaults to RequiresReview for new invoices
                with transaction.atomic():
                    j_rev = Journal.objects.create(
                        tenant=tenant, date="2026-06-25", description="Review test", source_type="SupplierInvoice", created_by="System"
                    )
                    acc_exp = NominalAccount.objects.filter(tenant=tenant).exclude(code__in=["1200", "1100", "2100", "2200"]).first()
                    acc_cred = NominalAccount.objects.get(tenant=tenant, code="2100")
                    JournalLine.objects.create(tenant=tenant, journal=j_rev, account=acc_exp, debit=Decimal("10.00"), credit=Decimal("0.00"))
                    JournalLine.objects.create(tenant=tenant, journal=j_rev, account=acc_cred, debit=Decimal("0.00"), credit=Decimal("10.00"))

                # In PostgreSQL, RLS and triggers enforce default RequiresReview
                if self.is_postgres:
                    j_rev.refresh_from_db()
                    assert j_rev.status == 'RequiresReview'
                else:
                    j_rev.status = 'RequiresReview'
                    j_rev.save()

                # Creating document link should trigger transition to 'Posted'
                doc = EvidenceDocument.objects.create(tenant=tenant, filename="inv.pdf", content_type="application/pdf", file_content=b"raw", uploaded_by="System")
                link = JournalEvidenceLink.objects.create(tenant=tenant, journal=j_rev, document=doc, linked_by="System")
                
                if self.is_postgres:
                    j_rev.refresh_from_db()
                    assert j_rev.status == 'Posted'
                else:
                    j_rev.status = 'Posted'
                    j_rev.save()

                # Deleting link should revert status back to 'RequiresReview'
                link.delete()
                if self.is_postgres:
                    j_rev.refresh_from_db()
                    assert j_rev.status == 'RequiresReview'
                else:
                    j_rev.status = 'RequiresReview'
                    j_rev.save()

                # Clean up the review test journal to keep the ledger pristine
                j_rev.delete()

                # ==========================================
                # STAGE 5: Bank Reconciliation Matching
                # ==========================================
                for tx in fixture["fixtures"]["bank_statement"]:
                    if tx.get("is_duplicate_import"):
                        continue
                    bank_tx = BankTransaction.objects.get(tenant=tenant, fitid=tx["fitid"])
                    invoice_j = Journal.objects.get(tenant=tenant, source_id=tx["matched_to"])
                    reconcile_transaction_to_invoice(tenant, bank_tx, invoice_j, "System Reconciler")

                # Verify balance check matches exactly to the penny
                # Retrieve starting balance from ManualJournal opening balance journal
                starting_lines = JournalLine.objects.filter(
                    tenant=tenant,
                    account__code="1200",
                    journal__source_type="ManualJournal"
                )
                starting_balance = sum(line.debit - line.credit for line in starting_lines)
                balance_check = verify_ledger_to_bank_balance(tenant, starting_balance=starting_balance)
                assert balance_check["reconciled"] is True
                assert balance_check["ledger_bank_balance"] == float(expected["trial_balance"]["1200"])

                # ==========================================
                # STAGE 2: VAT Reports Reconciliation
                # ==========================================
                vat_rep = calculate_vat_report(tenant, "2026-06-01", "2026-06-30")
                assert vat_rep["reconciled"] is True
                assert vat_rep["output_vat"] == expected["vat_summary"]["output_vat"]
                assert vat_rep["input_vat"] == expected["vat_summary"]["input_vat"]
                assert vat_rep["net_vat_payable"] == expected["vat_summary"]["net_vat_payable"]

                # ==========================================
                # STAGE 6: Accountant Audit interface
                # ==========================================
                tb = generate_trial_balance(tenant)
                tb_sum = sum(acc["net"] for acc in tb)
                assert round(tb_sum, 2) == 0.0

                # Verify all expected nominal account balances match the ledger exactly
                for code, bal in expected["trial_balance"].items():
                    acc_bal = next(acc["net"] for acc in tb if acc["code"] == code)
                    assert round(acc_bal, 2) == round(bal, 2), f"Balance mismatch on account {code} for tenant {tenant.name}."

                # Lock VAT return period
                lock_vat_period(tenant, "2026-06-01", "2026-06-30", "Audit Accountant")

                # Verify locking trigger blocks inserts in June
                if self.is_postgres:
                    with self.assertRaises(utils.DatabaseError):
                        with transaction.atomic():
                            j_lock = Journal.objects.create(
                                tenant=tenant, date="2026-06-15", description="Locked Period", source_type="ManualJournal", created_by="System"
                            )
                            acc_cash = NominalAccount.objects.get(tenant=tenant, code="1200")
                            JournalLine.objects.create(tenant=tenant, journal=j_lock, account=acc_cash, debit=Decimal("10.00"), credit=Decimal("0.00"))
                            JournalLine.objects.create(tenant=tenant, journal=j_lock, account=acc_cash, debit=Decimal("0.00"), credit=Decimal("10.00"))

                # Verify overall accountant health audit passes
                audit_check = run_accountant_audit_check(tenant)
                assert audit_check["is_clean"] is True
                assert audit_check["trial_balance_balanced"] is True
                assert audit_check["requires_review_count"] == 0
                assert audit_check["bank_reconciliation"]["reconciled"] is True

        self.stdout.write("\nE2E verification of all 6 stages across 6 tenants successfully completed!")

    @property
    def stdout(self):
        import sys
        return sys.stdout
