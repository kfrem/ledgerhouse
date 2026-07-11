from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.db import connection, transaction, utils
from accounting.models import Tenant, NominalAccount, BankFeedConnection, VatReturn, Journal, JournalLine, BankTransaction
from accounting.middleware import tenant_context
from accounting.open_banking import sync_bank_feed
from accounting.mtd import serialize_vat_return_9_box, submit_vat_return_to_hmrc
from accounting.payroll_cis import import_payroll_journal, post_subcontractor_invoice
from accounting.console import get_firm_dashboard


class Phase2And3Tests(TestCase):
    def setUp(self):
        # Create Tenants
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Set up chart of accounts for Tenant A
        with tenant_context(self.tenant_a.id):
            NominalAccount.objects.create(tenant=self.tenant_a, code="1100", name="Aged Debtors", category="Asset", canonical_taxonomy="Trade Receivables")
            NominalAccount.objects.create(tenant=self.tenant_a, code="1200", name="Bank Account", category="Asset", canonical_taxonomy="Cash and Cash Equivalents")
            NominalAccount.objects.create(tenant=self.tenant_a, code="2100", name="Aged Creditors", category="Liability", canonical_taxonomy="Trade Payables")
            NominalAccount.objects.create(tenant=self.tenant_a, code="2200", name="VAT Control", category="Liability", canonical_taxonomy="Tax Liabilities")
            NominalAccount.objects.create(tenant=self.tenant_a, code="4000", name="Sales Standard", category="Revenue", canonical_taxonomy="Operating Revenue")
            NominalAccount.objects.create(tenant=self.tenant_a, code="5100", name="COS Materials", category="Cost of Sales", canonical_taxonomy="Cost of Sales")
            NominalAccount.objects.create(tenant=self.tenant_a, code="6000", name="Rent", category="Expense", canonical_taxonomy="Operating Expenses")

        # Set up chart of accounts for Tenant B
        with tenant_context(self.tenant_b.id):
            NominalAccount.objects.create(tenant=self.tenant_b, code="1100", name="Aged Debtors", category="Asset", canonical_taxonomy="Trade Receivables")
            NominalAccount.objects.create(tenant=self.tenant_b, code="1200", name="Bank Account", category="Asset", canonical_taxonomy="Cash and Cash Equivalents")
            NominalAccount.objects.create(tenant=self.tenant_b, code="2100", name="Aged Creditors", category="Liability", canonical_taxonomy="Trade Payables")
            NominalAccount.objects.create(tenant=self.tenant_b, code="2200", name="VAT Control", category="Liability", canonical_taxonomy="Tax Liabilities")

        self.is_postgres = (connection.vendor == 'postgresql')

    def test_open_banking_sync(self):
        """Verify Open Banking feed syncing imports and reconciles idempotently."""
        with tenant_context(self.tenant_a.id):
            # Create a mock invoice for matching
            invoice = Journal.objects.create(
                tenant=self.tenant_a,
                date=date(2026, 6, 25),
                description="Mock Customer Invoice",
                source_type="SalesInvoice",
                source_id="TC-VI-991",
                created_by="Test",
                status="Posted"
            )
            debtor_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="1100")
            sales_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="4000")
            JournalLine.objects.create(tenant=self.tenant_a, journal=invoice, account=debtor_acc, debit=Decimal("1200.00"), credit=Decimal("0.00"))
            JournalLine.objects.create(tenant=self.tenant_a, journal=invoice, account=sales_acc, debit=Decimal("0.00"), credit=Decimal("1200.00"))

            # Create BankFeedConnection
            connection_a = BankFeedConnection.objects.create(
                tenant=self.tenant_a,
                bank_name="Barclays Business",
                account_identifier="BARC-991-A",
                status="Connected",
                expires_at=timezone.now() + timedelta(days=90),
                consent_token="token_abc_123"
            )

            # Sync feed for Tenant A
            imported, reconciled = sync_bank_feed(self.tenant_a, connection_a)
            self.assertEqual(imported, 2)
            self.assertEqual(reconciled, 1)

            # Second sync (idempotency check)
            imported_retry, reconciled_retry = sync_bank_feed(self.tenant_a, connection_a)
            self.assertEqual(imported_retry, 0)
            self.assertEqual(reconciled_retry, 0)

            # Confirm bank transactions created
            self.assertEqual(BankTransaction.objects.filter(tenant=self.tenant_a).count(), 2)

    def test_open_banking_tenant_isolation_rls(self):
        """Verify cross-tenant Open Banking operations fail under RLS constraints."""
        if not self.is_postgres:
            self.skipTest("RLS requires PostgreSQL environment.")

        # Create connection for Tenant A
        with tenant_context(self.tenant_a.id):
            connection_a = BankFeedConnection.objects.create(
                tenant=self.tenant_a,
                bank_name="Barclays",
                account_identifier="12345",
                expires_at=timezone.now() + timedelta(days=90)
            )

        # Tenant B tries to query Tenant A's connection (should return empty queryset under RLS)
        with tenant_context(self.tenant_b.id):
            tenant_b_connections = BankFeedConnection.objects.all()
            self.assertEqual(tenant_b_connections.count(), 0)

    def test_hmrc_mtd_vat_filing(self):
        """Verify 9-box serialization and submission updates VatReturn status."""
        with tenant_context(self.tenant_a.id):
            # Seed Sales Standard Invoice with Output VAT
            j_sales = Journal.objects.create(
                tenant=self.tenant_a, date=date(2026, 6, 10), description="Sales Invoice", source_type="SalesInvoice", created_by="Test", status="Posted"
            )
            debtor_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="1100")
            sales_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="4000")
            vat_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="2200")
            
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_sales, account=debtor_acc, debit=Decimal("120.00"), credit=Decimal("0.00"))
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_sales, account=sales_acc, debit=Decimal("0.00"), credit=Decimal("100.00"))
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_sales, account=vat_acc, debit=Decimal("0.00"), credit=Decimal("20.00"))

            # Seed Purchase Supplier Invoice with Input VAT
            j_purch = Journal.objects.create(
                tenant=self.tenant_a, date=date(2026, 6, 12), description="Purchase Invoice", source_type="SupplierInvoice", created_by="Test", status="Posted"
            )
            creditor_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="2100")
            expense_acc = NominalAccount.objects.get(tenant=self.tenant_a, code="6000")
            
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_purch, account=expense_acc, debit=Decimal("50.00"), credit=Decimal("0.00"))
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_purch, account=vat_acc, debit=Decimal("10.00"), credit=Decimal("0.00"))
            JournalLine.objects.create(tenant=self.tenant_a, journal=j_purch, account=creditor_acc, debit=Decimal("0.00"), credit=Decimal("60.00"))

            # Test 9-box serialization
            boxes = serialize_vat_return_9_box(self.tenant_a, date(2026, 6, 1), date(2026, 6, 30))
            self.assertEqual(boxes["vatDueOnOutputs"], 20.00)
            self.assertEqual(boxes["vatReclaimedCurrPeriod"], 10.00)
            self.assertEqual(boxes["netVatDue"], 10.00)
            self.assertEqual(boxes["totalValueSalesExVAT"], 100.00)
            self.assertEqual(boxes["totalValuePurchasesExVAT"], 50.00)

            # Create VatReturn record
            vat_return = VatReturn.objects.create(
                tenant=self.tenant_a,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 30),
                locked_by="Test Auditor",
                total_output_vat=Decimal("20.00"),
                total_input_vat=Decimal("10.00"),
                net_vat_payable=Decimal("10.00")
            )

            # Submit to HMRC
            response = submit_vat_return_to_hmrc(self.tenant_a, vat_return, period_key="26A1")
            self.assertEqual(response["status"], "success")
            self.assertTrue(response["receipt_id"].startswith("HMRC-REC-"))

            # Check status promoted
            vat_return.refresh_from_db()
            self.assertEqual(vat_return.status, "Submitted")
            self.assertEqual(vat_return.period_key, "26A1")
            self.assertIsNotNone(vat_return.hmrc_receipt_id)

    def test_payroll_journal_importer(self):
        """Verify payroll CSV parses and generates a balanced double-entry manual journal."""
        csv_content = """Department,GrossPay,EmployerNI,EmployeeNI,PAYETax,NetWages
Engineering,5000.00,600.00,500.00,1000.00,3500.00
Sales,3000.00,360.00,300.00,600.00,2100.00
"""
        with tenant_context(self.tenant_a.id):
            j = import_payroll_journal(self.tenant_a, csv_content, date(2026, 6, 30), "Payroll Clerk")
            
            # Confirm balanced
            lines = JournalLine.objects.filter(journal=j)
            total_debits = sum(line.debit for line in lines)
            total_credits = sum(line.credit for line in lines)
            self.assertEqual(total_debits, Decimal("8960.00"))  # Gross (5000+3000) + Employer NI (600+360)
            self.assertEqual(total_credits, Decimal("8960.00")) # PAYE/NI + Net Wages
            
            # Salaries account debits
            salaries_debit = sum(line.debit for line in lines if line.account.code == "6305")
            self.assertEqual(salaries_debit, Decimal("8000.00"))

            # Net wages credit
            net_wages_credit = sum(line.credit for line in lines if line.account.code == "2220")
            self.assertEqual(net_wages_credit, Decimal("5600.00"))

    def test_subcontractor_cis_invoice(self):
        """Verify CIS invoices post correctly, deducting tax withheld from aged creditors payable."""
        with tenant_context(self.tenant_a.id):
            # Subcontractor invoice: 2000 gross, 20% CIS rate
            j = post_subcontractor_invoice(
                tenant=self.tenant_a,
                subcontractor_name="Brickwork Ltd",
                gross_amount=Decimal("2000.00"),
                cis_rate=Decimal("0.20"),
                date_val=date(2026, 6, 18),
                department="Construction"
            )

            # Assert double-entry integrity
            lines = JournalLine.objects.filter(journal=j)
            total_debits = sum(line.debit for line in lines)
            total_credits = sum(line.credit for line in lines)
            self.assertEqual(total_debits, Decimal("2000.00"))
            self.assertEqual(total_credits, Decimal("2000.00"))

            # Aged creditors accounts payable should be 1600.00 (net)
            aged_creditors_credit = sum(line.credit for line in lines if line.account.code == "2100")
            self.assertEqual(aged_creditors_credit, Decimal("1600.00"))

            # CIS withholding tax liability should be 400.00 (tax)
            cis_tax_credit = sum(line.credit for line in lines if line.account.code == "2230")
            self.assertEqual(cis_tax_credit, Decimal("400.00"))

    def test_white_label_accountant_console(self):
        """Verify aggregated cross-tenant partner console dashboard metrics."""
        dashboard = get_firm_dashboard()
        # Dashboard lists both Tenant A and Tenant B
        tenant_ids = [item["tenant_id"] for item in dashboard]
        self.assertIn(str(self.tenant_a.id), tenant_ids)
        self.assertIn(str(self.tenant_b.id), tenant_ids)
