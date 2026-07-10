import json
import pytest
import uuid
from decimal import Decimal
from pathlib import Path
from django.db import connection, transaction, utils
from django.test import TransactionTestCase

from ..models import Tenant, NominalAccount, Journal, JournalLine, VatRate, VatDecisionRule
from ..middleware import tenant_context
from ..vat import resolve_vat_treatment, calculate_vat_report


def load_fixture_file(filename: str):
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "generated"
    with open(fixtures_dir / filename, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.django_db(transaction=True)
class VatModuleTests(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.is_postgres = connection.vendor == 'postgresql'
        
        # Setup basic entities
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")

        # Seed standard VAT rates for Tenant A
        VatRate.objects.create(tenant=self.tenant_a, vat_code="SR", rate=Decimal("0.2000"), effective_from="2026-01-01")
        VatRate.objects.create(tenant=self.tenant_a, vat_code="RR", rate=Decimal("0.0500"), effective_from="2026-01-01")
        VatRate.objects.create(tenant=self.tenant_a, vat_code="ZR", rate=Decimal("0.0000"), effective_from="2026-01-01")
        VatRate.objects.create(tenant=self.tenant_a, vat_code="EX", rate=Decimal("0.0000"), effective_from="2026-01-01")
        VatRate.objects.create(tenant=self.tenant_a, vat_code="OS", rate=Decimal("0.0000"), effective_from="2026-01-01")

        # Seed VAT rates for Tenant B
        VatRate.objects.create(tenant=self.tenant_b, vat_code="SR", rate=Decimal("0.2000"), effective_from="2026-01-01")

    def test_vat_code_resolution(self):
        """Verify that VAT resolution correctly applies priority and pattern matching."""
        # Create decision rules for Tenant A
        VatDecisionRule.objects.create(
            tenant=self.tenant_a, priority=5, supplier_name_pattern="Amazon", account_code_pattern="6", vat_code="SR"
        )
        VatDecisionRule.objects.create(
            tenant=self.tenant_a, priority=10, supplier_name_pattern="British Gas", account_code_pattern="61", vat_code="RR"
        )
        VatDecisionRule.objects.create(
            tenant=self.tenant_a, priority=20, supplier_name_pattern="", account_code_pattern="402", vat_code="EX"
        )

        with tenant_context(self.tenant_a.id):
            # Test rule matching
            code, rate = resolve_vat_treatment(self.tenant_a, "Amazon Web Services", "6200", "2026-06-01")
            assert code == "SR"
            assert rate == Decimal("0.2000")

            code, rate = resolve_vat_treatment(self.tenant_a, "British Gas Business", "6100", "2026-06-01")
            assert code == "RR"
            assert rate == Decimal("0.0500")

            code, rate = resolve_vat_treatment(self.tenant_a, "Kent County Council", "4020", "2026-06-01")
            assert code == "EX"
            assert rate == Decimal("0.0000")

            # Fallback test
            code, rate = resolve_vat_treatment(self.tenant_a, "Kent County Council", "4000", "2026-06-01")
            assert code == "SR"
            assert rate == Decimal("0.2000")

            # Outside Scope fallback
            code, rate = resolve_vat_treatment(self.tenant_a, "Wages", "6300", "2026-06-01")
            assert code == "OS"
            assert rate == Decimal("0.0000")

    def test_vat_rls_isolation(self):
        """Verify RLS isolates VAT rates and rules across tenants."""
        if not self.is_postgres:
            pytest.skip("PostgreSQL specific RLS test.")

        # Create a rule for Tenant A
        with tenant_context(self.tenant_a.id):
            VatDecisionRule.objects.create(
                tenant=self.tenant_a, priority=5, supplier_name_pattern="A-Only", vat_code="SR"
            )

        # Create a rule for Tenant B
        with tenant_context(self.tenant_b.id):
            VatDecisionRule.objects.create(
                tenant=self.tenant_b, priority=5, supplier_name_pattern="B-Only", vat_code="SR"
            )

        # Tenant A context query
        with tenant_context(self.tenant_a.id):
            rules = list(VatDecisionRule.objects.all())
            assert len(rules) == 1
            assert rules[0].supplier_name_pattern == "A-Only"

        # Tenant B context query
        with tenant_context(self.tenant_b.id):
            rules = list(VatDecisionRule.objects.all())
            assert len(rules) == 1
            assert rules[0].supplier_name_pattern == "B-Only"

    def _seed_company_fixture(self, filename: str, tenant_name: str, tenant_uuid_str: str) -> Tenant:
        """Helper to seed all fixtures and return tenant."""
        fixture = load_fixture_file(filename)
        expected = fixture["expected_results"]

        tenant_id = uuid.UUID(tenant_uuid_str)
        tenant = Tenant.objects.create(id=tenant_id, name=tenant_name)

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

        # Seed postings
        with tenant_context(tenant.id):
            for jp in expected["journal_postings"]:
                with transaction.atomic():
                    j = Journal.objects.create(
                        tenant=tenant,
                        date=jp["date"],
                        description=jp["description"],
                        source_type=jp["type"],
                        source_id=jp["source_id"],
                        created_by="Godfred (System)"
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
        return tenant

    def test_vat_report_care_provider(self):
        """Verify VAT reports for CareCo Limited reconcile exactly to the penny."""
        tenant = self._seed_company_fixture("care_provider.json", "CareCo Limited", "11111111-2222-3333-4444-555555555555")
        fixture = load_fixture_file("care_provider.json")
        expected_vat = fixture["expected_results"]["vat_summary"]

        with tenant_context(tenant.id):
            report = calculate_vat_report(tenant, "2026-06-01", "2026-06-30")
            assert report["output_vat"] == expected_vat["output_vat"]
            assert report["input_vat"] == expected_vat["input_vat"]
            assert report["net_vat_payable"] == expected_vat["net_vat_payable"]
            assert report["reconciled"] is True

    def test_vat_report_consultancy(self):
        """Verify VAT reports for ConsultCo Limited reconcile exactly to the penny."""
        tenant = self._seed_company_fixture("consultancy.json", "ConsultCo Limited", "22222222-3333-4444-5555-666666666666")
        fixture = load_fixture_file("consultancy.json")
        expected_vat = fixture["expected_results"]["vat_summary"]

        with tenant_context(tenant.id):
            report = calculate_vat_report(tenant, "2026-06-01", "2026-06-30")
            assert report["output_vat"] == expected_vat["output_vat"]
            assert report["input_vat"] == expected_vat["input_vat"]
            assert report["net_vat_payable"] == expected_vat["net_vat_payable"]
            assert report["reconciled"] is True

    def test_vat_report_trading_company(self):
        """Verify VAT reports for TradeCo Limited reconcile exactly to the penny."""
        tenant = self._seed_company_fixture("trading_company.json", "TradeCo Limited", "33333333-4444-5555-6666-777777777777")
        fixture = load_fixture_file("trading_company.json")
        expected_vat = fixture["expected_results"]["vat_summary"]

        with tenant_context(tenant.id):
            report = calculate_vat_report(tenant, "2026-06-01", "2026-06-30")
            assert report["output_vat"] == expected_vat["output_vat"]
            assert report["input_vat"] == expected_vat["input_vat"]
            assert report["net_vat_payable"] == expected_vat["net_vat_payable"]
            assert report["reconciled"] is True
