import pytest
from django.db import connection, transaction
from django.test import TransactionTestCase

from ..models import Tenant, ImportedFile, BankTransaction
from ..middleware import tenant_context
from ..bank_import import import_bank_csv


@pytest.mark.django_db(transaction=True)
class BankImportTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        self.valid_csv = (
            "Date,Amount,Reference,FITID\n"
            "2026-06-01,-100.00,Office Supplies,FITID-A1\n"
            "2026-06-02,500.00,Client Deposit,FITID-A2\n"
        )

        self.malformed_csv = (
            "Date,Amt,Ref\n"
            "2026-06-01,-100.00,Office Supplies\n"
        )

        self.invalid_date_csv = (
            "Date,Amount,Reference,FITID\n"
            "abc,-100.00,Office Supplies,FITID-A3\n"
        )

    def test_csv_import_success(self):
        """Verify that a valid CSV file imports correctly."""
        with tenant_context(self.tenant_a.id):
            imported, skipped = import_bank_csv(self.tenant_a, "statement.csv", self.valid_csv)
            assert imported == 2
            assert skipped == 0
            
            assert ImportedFile.objects.filter(filename="statement.csv").exists()
            assert BankTransaction.objects.filter(fitid="FITID-A1").exists()
            assert BankTransaction.objects.filter(fitid="FITID-A2").exists()

    def test_csv_import_file_idempotency(self):
        """Verify that importing the exact same file twice throws a ValueError."""
        with tenant_context(self.tenant_a.id):
            imported, skipped = import_bank_csv(self.tenant_a, "statement.csv", self.valid_csv)
            assert imported == 2

            with self.assertRaisesMessage(ValueError, "File already imported"):
                import_bank_csv(self.tenant_a, "statement.csv", self.valid_csv)

    def test_csv_import_line_idempotency(self):
        """Verify that transactions with existing FITIDs are skipped instead of causing failures."""
        partially_duplicate_csv = (
            "Date,Amount,Reference,FITID\n"
            "2026-06-01,-100.00,Office Supplies,FITID-A1\n" # Duplicate FITID
            "2026-06-03,-45.50,Travel expenses,FITID-A3\n" # New FITID
        )

        with tenant_context(self.tenant_a.id):
            import_bank_csv(self.tenant_a, "statement1.csv", self.valid_csv)
            
            # Second file has one duplicate row (FITID-A1) and one new row (FITID-A3)
            # The duplicate row should be skipped, and the new row should be imported.
            imported, skipped = import_bank_csv(self.tenant_a, "statement2.csv", partially_duplicate_csv)
            assert imported == 1
            assert skipped == 1
            assert BankTransaction.objects.filter(fitid="FITID-A3").exists()

    def test_csv_import_validation_header_failure(self):
        """Verify that headers missing required columns fail safely and raise ValueError."""
        with tenant_context(self.tenant_a.id):
            with self.assertRaisesMessage(ValueError, "Required headers: Date, Amount, Reference, FITID are missing"):
                import_bank_csv(self.tenant_a, "malformed.csv", self.malformed_csv)

    def test_csv_import_validation_date_failure_rollback(self):
        """Verify that validation failure rolls back the entire file import transactionally."""
        with tenant_context(self.tenant_a.id):
            with self.assertRaisesMessage(ValueError, "Invalid date format in row 1"):
                import_bank_csv(self.tenant_a, "invalid_date.csv", self.invalid_date_csv)
                
            # Rollback check: no files or transactions should be saved
            assert not ImportedFile.objects.filter(filename="invalid_date.csv").exists()
            assert not BankTransaction.objects.filter(fitid="FITID-A3").exists()

    def test_csv_import_rls_isolation(self):
        """Verify that row-level security isolates bank transactions across tenants."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific RLS test.")

        with tenant_context(self.tenant_a.id):
            import_bank_csv(self.tenant_a, "statement_a.csv", self.valid_csv)

        # Tenant B should see nothing
        with tenant_context(self.tenant_b.id):
            assert BankTransaction.objects.count() == 0
            assert ImportedFile.objects.count() == 0

        # Tenant A should see their 2 transactions
        with tenant_context(self.tenant_a.id):
            assert BankTransaction.objects.count() == 2
            assert ImportedFile.objects.count() == 1
