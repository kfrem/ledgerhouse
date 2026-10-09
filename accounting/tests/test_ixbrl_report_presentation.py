from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from accounting.ixbrl import generate_micro_entity_ixbrl, statutory_accounts_facts, validate_micro_entity_ixbrl


class IxbrlReportPresentationTests(SimpleTestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(name="LEDGERHOUSE TEST LIMITED")
        self.draft = SimpleNamespace(
            tenant=self.tenant,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            accounts_type="MicroEntity",
            approval_date=date(2026, 1, 31),
            approving_director_name="LedgerHouse Test Director",
        )
        self.report = {
            "revenue": "125000.00",
            "cost_of_sales": "40000.00",
            "gross_profit": "85000.00",
            "expenses": "72000.00",
            "profit": "13000.00",
            "gross_assets": "50000.00",
            "liabilities": "19000.00",
            "net_assets": "31000.00",
            "equity": "31000.00",
        }

    def render(self, draft=None):
        draft = draft or self.draft
        with patch("accounting.ixbrl.management_report_context", return_value=self.report):
            return generate_micro_entity_ixbrl(draft, "00000006", self.tenant.name)

    def validate(self, document, draft=None):
        with patch("accounting.ixbrl.management_report_context", return_value=self.report):
            return validate_micro_entity_ixbrl(document, draft or self.draft, "00000006")

    def test_micro_entity_report_is_a_paginated_statutory_table_document(self):
        document = self.render()
        validation = self.validate(document)

        self.assertTrue(validation.passed, validation.messages)
        self.assertIn('class="cover"', document)
        self.assertGreaterEqual(document.count('class="financial-statement"'), 2)
        self.assertIn('class="amount">2025<br />GBP', document)
        self.assertIn('class="total"', document)
        self.assertIn('page-break-before: always', document)
        self.assertIn('format="ixt:numdotdecimal"', document)
        self.assertIn('scale="0"', document)

    def test_negative_monetary_fact_uses_brackets_and_ixbrl_sign(self):
        self.report["profit"] = "-13000.00"
        document = self.render()

        self.assertIn('sign="-"', document)
        self.assertIn('>13,000.00</ix:nonFraction>)', document)
        self.assertTrue(self.validate(document).passed)

    def test_open_period_profit_is_included_in_statutory_capital_and_reserves(self):
        self.report.update(
            revenue="82000.00", cost_of_sales="24000.00", gross_profit="58000.00",
            expenses="18000.00", profit="40000.00", gross_assets="62000.00",
            liabilities="22000.00", net_assets="40000.00", equity="0.00",
        )
        with patch("accounting.ixbrl.management_report_context", return_value=self.report):
            facts = statutory_accounts_facts(self.draft, "00000006", self.tenant.name)
            document = generate_micro_entity_ixbrl(self.draft, "00000006", self.tenant.name)

        self.assertEqual(facts["equity"], 40000)
        self.assertEqual(facts["equity_difference"], 0)
        self.assertIn('name="uk-core:Equity"', document)
        self.assertIn('>40,000.00</ix:nonFraction>', document)

    def test_report_hides_inline_xbrl_header_facts_from_the_visible_cover(self):
        document = self.render()

        self.assertIn(r"ix\:hidden { display: none; }", document)
        self.assertIn('<ix:hidden>', document)
        self.assertIn('<div style="display: none;">\n  <ix:header>', document)

    def test_report_includes_companies_house_mandatory_balance_sheet_and_employee_facts(self):
        self.draft.average_number_employees = 3
        document = self.render()

        self.assertIn('name="uk-bus:BalanceSheetDate" contextRef="instant_current">2025-12-31', document)
        self.assertIn(
            'name="uk-core:AverageNumberEmployeesDuringPeriod" contextRef="current_period" unitRef="pure" decimals="0">3',
            document,
        )
        self.assertIn('<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>', document)
        self.assertIn('uk-bus:Micro-entities', document)
        self.assertIn("micro-entities regime", document)
        self.assertTrue(self.validate(document).passed)

    def test_filleted_accounts_omit_profit_and_loss_but_keep_balance_sheet(self):
        attributes = vars(self.draft).copy()
        attributes["accounts_type"] = "SmallUnauditedFilleted"
        draft = SimpleNamespace(**attributes)
        document = self.render(draft)

        self.assertNotIn("Profit and Loss Account", document)
        self.assertIn("Balance Sheet", document)
        self.assertTrue(self.validate(document, draft).passed)

    def test_dormant_accounts_do_not_require_trading_facts(self):
        attributes = vars(self.draft).copy()
        attributes["accounts_type"] = "Dormant"
        draft = SimpleNamespace(**attributes)
        document = self.render(draft)

        self.assertIn("The company was dormant throughout the accounting period.", document)
        self.assertIn("StatementThatCompanyEntitledToExemptionFromAuditUnderSection480CompaniesAct2006RelatingToDormantCompanies", document)
        self.assertNotIn("Profit and Loss Account", document)
        self.assertTrue(self.validate(document, draft).passed)

    def test_amended_accounts_have_a_clear_amendment_notice(self):
        attributes = vars(self.draft).copy()
        attributes["accounts_type"] = "AmendedMicroEntity"
        draft = SimpleNamespace(**attributes)
        document = self.render(draft)

        self.assertIn("These are amended accounts", document)
        self.assertTrue(self.validate(document, draft).passed)

    def test_explicit_comparatives_add_prior_contexts_and_a_second_year_column(self):
        attributes = vars(self.draft).copy()
        attributes["comparative_facts"] = {
            "revenue": "91000.00", "cost_of_sales": "32000.00", "gross_profit": "59000.00",
            "expenses": "25000.00", "profit": "34000.00", "gross_assets": "80000.00",
            "liabilities": "38000.00", "net_assets": "42000.00", "equity": "42000.00",
        }
        draft = SimpleNamespace(**attributes)
        document = self.render(draft)

        self.assertIn('id="previous_period"', document)
        self.assertIn('id="instant_previous"', document)
        self.assertIn('contextRef="previous_period"', document)
        self.assertIn('contextRef="instant_previous"', document)
        self.assertIn('class="amount">2024<br />GBP', document)
        self.assertTrue(self.validate(document, draft).passed)

    def test_validator_requires_real_approval_information_and_complete_comparatives(self):
        attributes = vars(self.draft).copy()
        attributes["approval_date"] = None
        attributes["approving_director_name"] = ""
        attributes["comparative_facts"] = {"revenue": "1.00"}
        draft = SimpleNamespace(**attributes)
        document = self.render(draft)
        validation = self.validate(document, draft)

        self.assertFalse(validation.passed)
        self.assertIn("Approval date must be recorded before generating filing iXBRL.", validation.messages)
        self.assertIn("Approving director name must be recorded before generating filing iXBRL.", validation.messages)
        self.assertTrue(any(message.startswith("Comparative facts are incomplete:") for message in validation.messages))

    def test_validator_rejects_continuous_flow_or_scripted_presentation(self):
        document = self.render()
        continuous_flow = document.replace('class="financial-statement"', 'class="ledger-lines"')
        scripted = document.replace("</body>", "<script>alert('x')</script></body>")

        self.assertFalse(self.validate(continuous_flow).passed)
        self.assertFalse(self.validate(scripted).passed)
