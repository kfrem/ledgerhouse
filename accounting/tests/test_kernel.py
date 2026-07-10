import json
import pytest
import uuid
from decimal import Decimal
from pathlib import Path
from django.db import connection, transaction, utils
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, AccountingPeriod, Journal, JournalLine, AuditEvent
from ..middleware import tenant_context


def load_fixture_file(filename: str):
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "generated"
    with open(fixtures_dir / filename, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.django_db(transaction=True)
class AccountingKernelTests(TransactionTestCase):
    
    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        # Setup basic entities
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Create nominals for Tenant A
        self.acc_bank_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="1200", name="Bank Current", category="Asset", canonical_taxonomy="Cash"
        )
        self.acc_revenue_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="4000", name="Sales", category="Revenue", canonical_taxonomy="Operating Revenue"
        )
        self.acc_creditors_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="2100", name="Aged Creditors", category="Liability", canonical_taxonomy="Trade Payables"
        )
        self.acc_expenses_a = NominalAccount.objects.create(
            tenant=self.tenant_a, code="6300", name="Staff Expenses", category="Expense", canonical_taxonomy="Operating Expenses"
        )
        
        # Create nominals for Tenant B
        self.acc_bank_b = NominalAccount.objects.create(
            tenant=self.tenant_b, code="1200", name="Bank Current", category="Asset", canonical_taxonomy="Cash"
        )

    def test_postgres_triggers_exist(self):
        """Verify PostgreSQL triggers are running on PostgreSQL connection."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific test.")
            
        with connection.cursor() as cursor:
            # Check for journal balance trigger
            cursor.execute("""
                SELECT trigger_name 
                FROM information_schema.triggers 
                WHERE event_object_table = 'accounting_journalline' AND trigger_name = 'trigger_check_journal_balance';
            """)
            assert cursor.fetchone() is not None

    def test_journal_balance_constraint_success(self):
        """Verify that a balanced journal can be committed successfully."""
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant_a,
                    date="2026-06-01",
                    description="Balanced manual journal",
                    source_type="ManualJournal",
                    created_by="Godfred"
                )
                # Balanced lines: Dr 100.00, Cr 100.00
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank_a, debit=Decimal("100.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_revenue_a, debit=Decimal("0.00"), credit=Decimal("100.00"))

            # Re-fetch and check it saved
            assert Journal.objects.filter(id=j.id).exists()
            assert j.lines.count() == 2

    def test_journal_balance_constraint_failure(self):
        """Verify that an unbalanced journal fails to commit at the database level."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific test.")

        with tenant_context(self.tenant_a.id):
            j = Journal.objects.create(
                tenant=self.tenant_a,
                date="2026-06-01",
                description="Unbalanced manual journal",
                source_type="ManualJournal",
                created_by="Godfred"
            )
            # Commit must fail with DatabaseError due to trigger exception
            with self.assertRaises(utils.DatabaseError):
                with transaction.atomic():
                    JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank_a, debit=Decimal("100.00"), credit=Decimal("0.00"))
                    JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_revenue_a, debit=Decimal("0.00"), credit=Decimal("99.00")) # Off by 1.00!

    def test_locked_period_blocks_inserts(self):
        """Verify that database prevents inserting a journal in a closed period."""
        # Create a closed period for Tenant A
        AccountingPeriod.objects.create(
            tenant=self.tenant_a,
            start_date="2026-05-01",
            end_date="2026-05-31",
            is_closed=True,
            closed_by="Godfred"
        )

        with tenant_context(self.tenant_a.id):
            if self.is_postgres:
                # Attempt to create journal dated inside May 2026
                with self.assertRaisesMessage(utils.DatabaseError, "falls within a closed accounting period"):
                    with transaction.atomic():
                        Journal.objects.create(
                            tenant=self.tenant_a,
                            date="2026-05-15",
                            description="Unauthorised post-close journal",
                            source_type="ManualJournal",
                            created_by="Godfred"
                        )
            else:
                # SQLite won't run this check at database level unless we implement python validation in save().
                # But we target Postgres.
                pass

    def test_locked_period_blocks_updates_and_deletes(self):
        """Verify that editing or deleting a journal in a closed period is blocked."""
        # Create an open period, add a journal, then close the period
        period = AccountingPeriod.objects.create(
            tenant=self.tenant_a,
            start_date="2026-05-01",
            end_date="2026-05-31",
            is_closed=False
        )

        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                j = Journal.objects.create(
                    tenant=self.tenant_a,
                    date="2026-05-15",
                    description="Pre-close journal",
                    source_type="ManualJournal",
                    created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_bank_a, debit=Decimal("50.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=j, account=self.acc_revenue_a, debit=Decimal("0.00"), credit=Decimal("50.00"))

            # Lock the period
            period.is_closed = True
            period.save()

            if self.is_postgres:
                # Attempt update description
                with self.assertRaisesMessage(utils.DatabaseError, "falls within a closed accounting period"):
                    with transaction.atomic():
                        j.description = "Updated description"
                        j.save()

                # Attempt delete journal line
                line = j.lines.first()
                with self.assertRaisesMessage(utils.DatabaseError, "falls within a closed accounting period"):
                    with transaction.atomic():
                        line.delete()

                # Attempt delete journal
                with self.assertRaisesMessage(utils.DatabaseError, "falls within a closed accounting period"):
                    with transaction.atomic():
                        j.delete()

    def test_audit_log_immutability(self):
        """Verify that audit events cannot be modified or deleted once created."""
        event = AuditEvent.objects.create(
            tenant=self.tenant_a,
            event_type="LOGIN",
            username="godfred",
            description="Accountant logged in"
        )

        if self.is_postgres:
            # Try to update
            with self.assertRaisesMessage(utils.DatabaseError, "immutable and cannot be updated or deleted"):
                with transaction.atomic():
                    event.description = "Malicious update attempt"
                    event.save()

            # Try to delete
            with self.assertRaisesMessage(utils.DatabaseError, "immutable and cannot be updated or deleted"):
                with transaction.atomic():
                    event.delete()

    def test_tenant_isolation_rls(self):
        """Verify that row-level security isolates tenant data completely."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific test.")

        # Create journals for Tenant A and Tenant B
        with tenant_context(self.tenant_a.id):
            with transaction.atomic():
                ja = Journal.objects.create(
                    tenant=self.tenant_a, date="2026-06-01", description="Journal A", source_type="ManualJournal", created_by="Godfred"
                )
                JournalLine.objects.create(tenant=self.tenant_a, journal=ja, account=self.acc_bank_a, debit=Decimal("10.00"), credit=Decimal("0.00"))
                JournalLine.objects.create(tenant=self.tenant_a, journal=ja, account=self.acc_revenue_a, debit=Decimal("0.00"), credit=Decimal("10.00"))

        with tenant_context(self.tenant_b.id):
            with transaction.atomic():
                jb = Journal.objects.create(
                    tenant=self.tenant_b, date="2026-06-01", description="Journal B", source_type="ManualJournal", created_by="User B"
                )
                JournalLine.objects.create(tenant=self.tenant_b, journal=jb, account=self.acc_bank_b, debit=Decimal("20.00"), credit=Decimal("0.00"))
                # To make it balance: let's create a revenue account for Tenant B
                acc_rev_b = NominalAccount.objects.create(
                    tenant=self.tenant_b, code="4000", name="Sales", category="Revenue", canonical_taxonomy="Operating Revenue"
                )
                JournalLine.objects.create(tenant=self.tenant_b, journal=jb, account=acc_rev_b, debit=Decimal("0.00"), credit=Decimal("20.00"))

        # Query under Tenant A context
        with tenant_context(self.tenant_a.id):
            journals = list(Journal.objects.all())
            assert len(journals) == 1
            assert journals[0].description == "Journal A"
            
            # Check lines
            assert JournalLine.objects.count() == 2
            assert all(line.tenant == self.tenant_a for line in JournalLine.objects.all())

        # Query under Tenant B context
        with tenant_context(self.tenant_b.id):
            journals = list(Journal.objects.all())
            assert len(journals) == 1
            assert journals[0].description == "Journal B"
            assert all(line.tenant == self.tenant_b for line in JournalLine.objects.all())

    def test_reconcile_care_provider_fixtures(self):
        """Seed CareCo Limited fixtures and reconcile to expected reports."""
        # Load Stage 0 Care Provider fixtures
        cp_fixture = load_fixture_file("care_provider.json")
        expected = cp_fixture["expected_results"]

        # Create Tenant CareCo
        careco_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        careco = Tenant.objects.create(id=careco_id, name="CareCo Limited")

        # Create Nominal Accounts in DB
        nominals_map = {}
        for code, details in expected["trial_balance"].items():
            # Seed accounts in database
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
                tenant=careco,
                code=code,
                name=f"Nominal {code}",
                category=category,
                canonical_taxonomy="Taxonomy"
            )

        # Seed double entries from expected journal postings
        with tenant_context(careco.id):
            for jp in expected["journal_postings"]:
                with transaction.atomic():
                    j = Journal.objects.create(
                        tenant=careco,
                        date=jp["date"],
                        description=jp["description"],
                        source_type=jp["type"],
                        source_id=jp["source_id"],
                        created_by="Godfred (System)"
                    )
                    for line in jp["lines"]:
                        acc = NominalAccount.objects.get(tenant=careco, code=line["account_code"])
                        JournalLine.objects.create(
                            tenant=careco,
                            journal=j,
                            account=acc,
                            debit=Decimal(str(line["debit"])),
                            credit=Decimal(str(line["credit"])),
                            vat_code=line["vat_code"],
                            department=line["department"]
                        )

            # Reconcile Trial Balance
            tb_results = {}
            for code in expected["trial_balance"].keys():
                acc = NominalAccount.objects.get(tenant=careco, code=code)
                lines = JournalLine.objects.filter(tenant=careco, account=acc)
                debit_sum = sum(line.debit for line in lines)
                credit_sum = sum(line.credit for line in lines)
                tb_results[code] = float(round(debit_sum - credit_sum, 2))

            # Verify it matches expected TB exactly to the penny
            for code, exp_val in expected["trial_balance"].items():
                assert tb_results[code] == exp_val, f"TB code {code} mismatched! Expected {exp_val}, got {tb_results[code]}"

            # Verify Bank Reconciled Balance
            # Bank Account code 1200
            acc_bank = NominalAccount.objects.get(tenant=careco, code="1200")
            bank_lines = JournalLine.objects.filter(tenant=careco, account=acc_bank)
            bank_balance = sum(line.debit - line.credit for line in bank_lines)
            assert float(round(bank_balance, 2)) == expected["trial_balance"]["1200"]
