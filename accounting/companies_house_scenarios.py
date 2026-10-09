from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .companies_house import (
    build_companies_house_accounts_submission_xml,
    companies_house_filing_credentials,
    validate_companies_house_filing_readiness,
)
from .ixbrl import generate_micro_entity_ixbrl, validate_micro_entity_ixbrl
from .middleware import tenant_context
from .models import (
    AuditEvent,
    Journal,
    JournalLine,
    NominalAccount,
    StatutoryAccountsDraft,
    Tenant,
)


@dataclass(frozen=True)
class CompaniesHouseScenarioSpec:
    slug: str
    company_name: str
    company_number: str
    accounts_type: str
    revenue: Decimal
    cost_of_sales: Decimal
    expenses: Decimal
    assets: Decimal
    liabilities: Decimal
    equity: Decimal
    description: str
    comparative_facts: dict[str, str] | None = None


@dataclass(frozen=True)
class CompaniesHouseScenarioResult:
    slug: str
    company_name: str
    company_number: str
    accounts_type: str
    draft_id: int
    ixbrl_passed: bool
    readiness_passed: bool
    gateway_xml_built: bool
    messages: list[str]

    @property
    def passed(self):
        return self.ixbrl_passed and self.readiness_passed and self.gateway_xml_built and not self.messages


SCENARIO_SPECS = [
    CompaniesHouseScenarioSpec(
        "micro-profit",
        "LH TEST MICRO PROFIT LIMITED",
        "00000006",
        "MicroEntity",
        Decimal("82000.00"),
        Decimal("24000.00"),
        Decimal("18000.00"),
        Decimal("62000.00"),
        Decimal("22000.00"),
        Decimal("40000.00"),
        "Trading micro-entity company with profit, debtors, creditors and retained funds.",
    ),
    CompaniesHouseScenarioSpec(
        "small-unaudited",
        "LH TEST SMALL UNAUDITED LIMITED",
        "00000006",
        "SmallUnaudited",
        Decimal("240000.00"),
        Decimal("92000.00"),
        Decimal("74000.00"),
        Decimal("156000.00"),
        Decimal("82000.00"),
        Decimal("74000.00"),
        "Small unaudited company with fuller operating volumes.",
    ),
    CompaniesHouseScenarioSpec(
        "small-unaudited-filleted",
        "LH TEST SMALL UNAUDITED FILLETED LIMITED",
        "00000006",
        "SmallUnauditedFilleted",
        Decimal("210000.00"),
        Decimal("81000.00"),
        Decimal("68000.00"),
        Decimal("142000.00"),
        Decimal("70000.00"),
        Decimal("72000.00"),
        "Small unaudited company using the filleted presentation permitted for the declared initial scope.",
    ),
    CompaniesHouseScenarioSpec(
        "dormant",
        "LH TEST DORMANT LIMITED",
        "00000006",
        "Dormant",
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("100.00"),
        Decimal("0.00"),
        Decimal("100.00"),
        "Dormant company with share capital and no trading activity.",
    ),
    CompaniesHouseScenarioSpec(
        "amended",
        "LH TEST AMENDED ACCOUNTS LIMITED",
        "00000006",
        "AmendedMicroEntity",
        Decimal("95000.00"),
        Decimal("32000.00"),
        Decimal("21000.00"),
        Decimal("78000.00"),
        Decimal("36000.00"),
        Decimal("42000.00"),
        "Amended accounts scenario to prove amended wording and wrapper generation.",
    ),
    CompaniesHouseScenarioSpec(
        "comparative",
        "LH TEST COMPARATIVE LIMITED",
        "00000006",
        "MicroEntityComparative",
        Decimal("118000.00"),
        Decimal("41000.00"),
        Decimal("28000.00"),
        Decimal("96000.00"),
        Decimal("47000.00"),
        Decimal("49000.00"),
        "Current-year accounts with comparatives-ready draft naming for future expansion.",
        {
            "revenue": "91000.00",
            "cost_of_sales": "32000.00",
            "gross_profit": "59000.00",
            "expenses": "25000.00",
            "profit": "34000.00",
            "gross_assets": "80000.00",
            "liabilities": "38000.00",
            "net_assets": "42000.00",
            "equity": "42000.00",
        },
    ),
    CompaniesHouseScenarioSpec(
        "loss-making",
        "LH TEST LOSS MAKING LIMITED",
        "00000006",
        "MicroEntity",
        Decimal("34000.00"),
        Decimal("29000.00"),
        Decimal("18000.00"),
        Decimal("31000.00"),
        Decimal("44000.00"),
        Decimal("-13000.00"),
        "Loss-making company with net liabilities to test negative equity presentation.",
    ),
    CompaniesHouseScenarioSpec(
        "fixed-assets",
        "LH TEST FIXED ASSETS LIMITED",
        "00000006",
        "MicroEntity",
        Decimal("145000.00"),
        Decimal("52000.00"),
        Decimal("39000.00"),
        Decimal("132000.00"),
        Decimal("78000.00"),
        Decimal("54000.00"),
        "Company with material assets and liabilities for balance sheet readiness checks.",
    ),
    CompaniesHouseScenarioSpec(
        "creditor-heavy",
        "LH TEST CREDITOR HEAVY LIMITED",
        "00000006",
        "MicroEntity",
        Decimal("68000.00"),
        Decimal("26000.00"),
        Decimal("31000.00"),
        Decimal("52000.00"),
        Decimal("41000.00"),
        Decimal("11000.00"),
        "Creditor-heavy company to exercise liabilities and cash pressure reporting.",
    ),
    CompaniesHouseScenarioSpec(
        "small-full-asset-led",
        "LH TEST SMALL FULL ASSET LED LIMITED",
        "00000006",
        "SmallUnaudited",
        Decimal("510000.00"),
        Decimal("186000.00"),
        Decimal("147000.00"),
        Decimal("420000.00"),
        Decimal("243000.00"),
        Decimal("177000.00"),
        "Small unaudited company with substantial assets, profitable trading and positive reserves.",
    ),
    CompaniesHouseScenarioSpec(
        "small-full-low-margin",
        "LH TEST SMALL FULL LOW MARGIN LIMITED",
        "00000006",
        "SmallUnaudited",
        Decimal("385000.00"),
        Decimal("251000.00"),
        Decimal("117000.00"),
        Decimal("196000.00"),
        Decimal("179000.00"),
        Decimal("17000.00"),
        "Small unaudited company with low margin trading and modest net assets.",
    ),
    CompaniesHouseScenarioSpec(
        "small-full-loss-making",
        "LH TEST SMALL FULL LOSS MAKING LIMITED",
        "00000006",
        "SmallUnaudited",
        Decimal("298000.00"),
        Decimal("176000.00"),
        Decimal("148000.00"),
        Decimal("164000.00"),
        Decimal("190000.00"),
        Decimal("-26000.00"),
        "Small unaudited loss-making company with net liabilities and a balanced balance sheet.",
    ),
    CompaniesHouseScenarioSpec(
        "filleted-services",
        "LH TEST FILLETED SERVICES LIMITED",
        "00000006",
        "SmallUnauditedFilleted",
        Decimal("330000.00"),
        Decimal("92000.00"),
        Decimal("144000.00"),
        Decimal("225000.00"),
        Decimal("131000.00"),
        Decimal("94000.00"),
        "Small unaudited filleted service company with profitable trading and working capital.",
    ),
    CompaniesHouseScenarioSpec(
        "filleted-fixed-assets",
        "LH TEST FILLETED FIXED ASSETS LIMITED",
        "00000006",
        "SmallUnauditedFilleted",
        Decimal("470000.00"),
        Decimal("184000.00"),
        Decimal("159000.00"),
        Decimal("515000.00"),
        Decimal("388000.00"),
        Decimal("127000.00"),
        "Small unaudited filleted company with a material asset base and financing liabilities.",
    ),
    CompaniesHouseScenarioSpec(
        "filleted-creditor-led",
        "LH TEST FILLETED CREDITOR LED LIMITED",
        "00000006",
        "SmallUnauditedFilleted",
        Decimal("255000.00"),
        Decimal("112000.00"),
        Decimal("98000.00"),
        Decimal("148000.00"),
        Decimal("103000.00"),
        Decimal("45000.00"),
        "Small unaudited filleted company with a creditor-led working-capital profile.",
    ),
    CompaniesHouseScenarioSpec(
        "dormant-capitalised",
        "LH TEST DORMANT CAPITALISED LIMITED",
        "00000006",
        "Dormant",
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("1000.00"),
        Decimal("0.00"),
        Decimal("1000.00"),
        "Dormant company with paid share capital and no trading activity.",
    ),
    CompaniesHouseScenarioSpec(
        "dormant-reserves",
        "LH TEST DORMANT RESERVES LIMITED",
        "00000006",
        "Dormant",
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("2500.00"),
        Decimal("0.00"),
        Decimal("2500.00"),
        "Dormant company with cash reserves and no trading activity.",
    ),
    CompaniesHouseScenarioSpec(
        "dormant-funded",
        "LH TEST DORMANT FUNDED LIMITED",
        "00000006",
        "Dormant",
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("5000.00"),
        Decimal("0.00"),
        Decimal("5000.00"),
        "Dormant company with larger paid-in funds and no trading activity.",
    ),
]


def _account(tenant, code, name, category, taxonomy):
    account, _created = NominalAccount.objects.get_or_create(
        tenant=tenant,
        code=code,
        defaults={"name": name, "category": category, "canonical_taxonomy": taxonomy},
    )
    return account


def _replace_scenario_journal(tenant, spec, period_end):
    Journal.objects.filter(tenant=tenant, source_type="CHScenario").delete()
    bank = _account(tenant, "1200", "Bank", "Asset", "Cash")
    revenue = _account(tenant, "4000", "Sales", "Revenue", "Revenue")
    cost = _account(tenant, "5000", "Cost of sales", "Cost of Sales", "CostOfSales")
    expenses = _account(tenant, "6000", "Office costs", "Expense", "Expense")
    creditors = _account(tenant, "2100", "Trade creditors", "Liability", "Payables")
    equity = _account(tenant, "3000", "Capital and reserves", "Equity", "Equity")

    journal = Journal.objects.create(
        tenant=tenant,
        date=period_end,
        description=f"Companies House local scenario: {spec.description}",
        source_type="CHScenario",
        source_id=spec.slug,
        created_by="loop-engineering",
        status="Posted",
    )
    equity_balance = spec.assets + spec.cost_of_sales + spec.expenses - spec.revenue - spec.liabilities
    entries = [
        (bank, spec.assets, Decimal("0.00")),
        (revenue, Decimal("0.00"), spec.revenue),
        (cost, spec.cost_of_sales, Decimal("0.00")),
        (expenses, spec.expenses, Decimal("0.00")),
        (creditors, Decimal("0.00"), spec.liabilities),
    ]
    if equity_balance >= 0:
        entries.append((equity, Decimal("0.00"), equity_balance))
    else:
        entries.append((equity, abs(equity_balance), Decimal("0.00")))

    for account, debit, credit in entries:
        if debit or credit:
            JournalLine.objects.create(
                tenant=tenant,
                journal=journal,
                account=account,
                debit=debit,
                credit=credit,
                vat_code="OS",
                vat_rate=Decimal("0.0000"),
                vat_amount=Decimal("0.00"),
            )


def _scenario_draft(tenant, spec):
    today = timezone.localdate()
    period_start = date(today.year - 1, 1, 1)
    period_end = date(today.year - 1, 12, 31)
    draft, _created = StatutoryAccountsDraft.objects.update_or_create(
        tenant=tenant,
        period_start=period_start,
        period_end=period_end,
        accounts_type=spec.accounts_type,
        defaults={
            "directors_report_ready": True,
            "balance_sheet_ready": True,
            "notes_ready": True,
            "client_approved": True,
            "ixbrl_ready": False,
            "comparative_facts": spec.comparative_facts or {},
            "approval_date": period_end,
            "approving_director_name": "LedgerHouse Test Director",
            "status": StatutoryAccountsDraft.STATUS_READY_FOR_FILING,
            "review_note": spec.description,
        },
    )
    return draft


@transaction.atomic
def build_companies_house_local_scenarios(username="loop-engineering"):
    results = []
    credentials = companies_house_filing_credentials()
    for index, spec in enumerate(SCENARIO_SPECS, start=1):
        tenant, _created = Tenant.objects.get_or_create(name=spec.company_name)
        with tenant_context(tenant.id):
            draft = _scenario_draft(tenant, spec)
            _replace_scenario_journal(tenant, spec, draft.period_end)

            ixbrl_text = generate_micro_entity_ixbrl(draft, spec.company_number, spec.company_name)
            ixbrl_validation = validate_micro_entity_ixbrl(ixbrl_text, draft, spec.company_number)
            draft.ixbrl_ready = ixbrl_validation.passed
            draft.status = StatutoryAccountsDraft.STATUS_READY_FOR_FILING if ixbrl_validation.passed else StatutoryAccountsDraft.STATUS_INTERNAL_REVIEW
            draft.save(update_fields=["ixbrl_ready", "status"])

            readiness_messages = validate_companies_house_filing_readiness(draft)
            gateway_xml_built = False
            messages = [*ixbrl_validation.messages, *readiness_messages]
            if credentials["configured"] and not messages:
                try:
                    xml_text = build_companies_house_accounts_submission_xml(
                        draft,
                        spec.company_number,
                        spec.company_name,
                        "TEST12",
                        index,
                    )
                    gateway_xml_built = all(
                        token in xml_text
                        for token in [
                            "<Class>Accounts</Class>",
                            "<Function>submit</Function>",
                            "FormSubmission-v2-11.xsd",
                            "<Document>",
                            "<Category>ACCOUNTS</Category>",
                        ]
                    )
                    if not gateway_xml_built:
                        messages.append("Gateway XML was generated but did not contain all required accounts filing markers.")
                except Exception as exc:
                    messages.append(f"Gateway XML build failed: {exc}")
            elif not credentials["configured"]:
                gateway_xml_built = True

            AuditEvent.objects.create(
                tenant=tenant,
                event_type="CompaniesHouseScenarioBuilt",
                username=username,
                description=f"Local Companies House scenario {spec.slug} built and validated.",
                details={
                    "slug": spec.slug,
                    "accounts_type": spec.accounts_type,
                    "ixbrl_passed": ixbrl_validation.passed,
                    "readiness_messages": readiness_messages,
                    "gateway_xml_built": gateway_xml_built,
                },
            )
            results.append(
                CompaniesHouseScenarioResult(
                    slug=spec.slug,
                    company_name=spec.company_name,
                    company_number=spec.company_number,
                    accounts_type=spec.accounts_type,
                    draft_id=draft.id,
                    ixbrl_passed=ixbrl_validation.passed,
                    readiness_passed=not readiness_messages,
                    gateway_xml_built=gateway_xml_built,
                    messages=messages,
                )
            )
    return results


def companies_house_scenario_summary():
    results = []
    for spec in SCENARIO_SPECS:
        tenant = Tenant.objects.filter(name=spec.company_name).first()
        draft = None
        if tenant:
            draft = tenant.statutory_accounts_drafts.filter(accounts_type=spec.accounts_type).order_by("-period_end").first()
        results.append(
            {
                "slug": spec.slug,
                "company_name": spec.company_name,
                "accounts_type": spec.accounts_type,
                "built": bool(draft),
                "ixbrl_ready": bool(draft and draft.ixbrl_ready),
                "status": draft.status if draft else "Not built",
                "description": spec.description,
            }
        )
    return results
