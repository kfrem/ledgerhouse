import json
import uuid
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models import Tenant, NominalAccount, Journal, JournalLine, BankTransaction, VatRate, VatDecisionRule, ImportedFile
from accounting.middleware import tenant_context
from accounting.bank_import import import_bank_csv
from accounting.reconciliation import reconcile_transaction_to_invoice


class Command(BaseCommand):
    help = "Seeds the database with synthetic CareCo, ConsultCo, and TradeCo companies and reconciles them."

    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding...")

        fixtures_dir = Path(__file__).parent.parent.parent / "fixtures" / "generated"
        files = {
            "care_provider.json": "CareCo Limited",
            "consultancy.json": "ConsultCo Consulting",
            "trading_company.json": "TradeCo Retail",
            "tech_co.json": "TechCo Software Ltd",
            "logistics_co.json": "LogisticsCo Transport Ltd",
            "charity_co.json": "CharityCo Foundation"
        }

        # Clear existing data to allow clean re-runs
        self.stdout.write("Clearing existing accounting tables...")
        from accounting.models import JournalLine, JournalEvidenceLink, EvidenceDocument, BankReconciliation, VatReturn
        BankReconciliation.objects.all().delete()
        JournalEvidenceLink.objects.all().delete()
        EvidenceDocument.objects.all().delete()
        BankTransaction.objects.all().delete()
        ImportedFile.objects.all().delete()
        JournalLine.objects.all().delete()
        Journal.objects.all().delete()
        VatDecisionRule.objects.all().delete()
        VatRate.objects.all().delete()
        VatReturn.objects.all().delete()
        NominalAccount.objects.all().delete()
        Tenant.objects.all().delete()

        for filename, tenant_name in files.items():
            file_path = fixtures_dir / filename
            if not file_path.exists():
                self.stdout.write(self.style.ERROR(f"Fixture {filename} not found at {file_path}. Skip."))
                continue

            self.stdout.write(f"Loading {filename}...")
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            metadata = data["metadata"]
            expected = data["expected_results"]

            # 1. Create Tenant
            # Use deterministic UUID based on filename to keep it consistent
            tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, filename)
            tenant = Tenant.objects.create(id=tenant_uuid, name=tenant_name)
            self.stdout.write(f"Created Tenant: {tenant.name} ({tenant.id})")

            # 2. Seed Nominal Accounts
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

            # 3. Seed VAT Rates & Rules (if present in fixture or defaults)
            # Create a default SR (20%) and ZR (0%) rate
            VatRate.objects.create(tenant=tenant, vat_code="SR", rate=Decimal("0.2000"), effective_from="2020-01-01")
            VatRate.objects.create(tenant=tenant, vat_code="ZR", rate=Decimal("0.0000"), effective_from="2020-01-01")
            VatRate.objects.create(tenant=tenant, vat_code="EX", rate=Decimal("0.0000"), effective_from="2020-01-01")
            VatRate.objects.create(tenant=tenant, vat_code="OS", rate=Decimal("0.0000"), effective_from="2020-01-01")

            with tenant_context(tenant.id):
                # 4. Seed Journals
                for jp in expected["journal_postings"]:
                    # Seed only non-reconciled items (invoices, expenses, manual adjustments).
                    # Dynamic payment journals are created by the reconciliation engine below.
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
                        from accounting.models import EvidenceDocument, JournalEvidenceLink
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

                # 5. Import Bank Statement
                csv_lines = ["Date,Amount,Reference,FITID"]
                for tx in data["fixtures"]["bank_statement"]:
                    if tx.get("is_duplicate_import"):
                        continue
                    csv_lines.append(f"{tx['date']},{tx['amount']},{tx['reference']},{tx['fitid']}")
                csv_content = "\n".join(csv_lines)

                import_bank_csv(tenant, "bank_statement.csv", csv_content)

                # 6. Reconcile Bank Statement
                reconciled_count = 0
                for tx in data["fixtures"]["bank_statement"]:
                    if tx.get("is_duplicate_import"):
                        continue
                    bank_tx = BankTransaction.objects.get(tenant=tenant, fitid=tx["fitid"])
                    
                    try:
                        invoice_j = Journal.objects.get(tenant=tenant, source_id=tx["matched_to"])
                        reconcile_transaction_to_invoice(tenant, bank_tx, invoice_j, "System Reconciler")
                        reconciled_count += 1
                    except Journal.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"Matched journal {tx['matched_to']} not found for statement line {tx['fitid']}."))

                self.stdout.write(self.style.SUCCESS(f"Tenant {tenant.name} seeded successfully. Reconciled {reconciled_count} bank statement lines."))

        self.stdout.write(self.style.SUCCESS("Database seeding completed!"))
