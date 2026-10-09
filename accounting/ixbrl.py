"""Local iXBRL accounts production and structural validation.

This module deliberately produces a readable XHTML report as well as inline
XBRL facts.  Companies House reviewers inspect the rendered XHTML, so a
well-formed facts-only document is not sufficient for a filing test.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import html
import re
import xml.etree.ElementTree as ET

from .reports import management_report_context


# The supplied approved reference used the 2025 taxonomy suite.  This is kept
# in one place so it can be changed after Companies House confirms the version
# accepted for the final gateway run.
TAXONOMY_VERSION = "2025-01-01"
IXBRL_NAMESPACES = {
    "xhtml": "http://www.w3.org/1999/xhtml",
    "ix": "http://www.xbrl.org/2013/inlineXBRL",
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
    "link": "http://www.xbrl.org/2003/linkbase",
    "xlink": "http://www.w3.org/1999/xlink",
    "iso4217": "http://www.xbrl.org/2003/iso4217",
    "ixt": "http://www.xbrl.org/inlineXBRL/transformation/2011-07-31",
    "uk-bus": f"http://xbrl.frc.org.uk/cd/{TAXONOMY_VERSION}/business",
    "uk-core": f"http://xbrl.frc.org.uk/fr/{TAXONOMY_VERSION}/core",
    "direp": f"http://xbrl.frc.org.uk/reports/{TAXONOMY_VERSION}/direp",
}


@dataclass(frozen=True)
class IxbrlValidationResult:
    passed: bool
    messages: list[str]
    facts: dict[str, str]


@dataclass(frozen=True)
class AccountsProfile:
    key: str
    framework: str
    title: str
    include_profit_and_loss: bool
    dormant: bool = False
    amended: bool = False


def _decimal(value):
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _iso_date(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _profile(accounts_type):
    value = (accounts_type or "MicroEntity").replace("_", "").lower()
    if "dormant" in value:
        return AccountsProfile("Dormant", "FRS 105", "Dormant Company Financial Statements", False, dormant=True)
    if "amended" in value:
        return AccountsProfile("AmendedMicroEntity", "FRS 105", "Amended Unaudited Micro-Entity Financial Statements", True, amended=True)
    if "filleted" in value:
        return AccountsProfile("SmallUnauditedFilleted", "FRS 102 Section 1A", "Filleted Unaudited Financial Statements", False)
    if "small" in value:
        return AccountsProfile("SmallUnaudited", "FRS 102 Section 1A", "Unaudited Financial Statements", True)
    return AccountsProfile("MicroEntity", "FRS 105", "Unaudited Micro-Entity Financial Statements", True)


def _money_fact(name, value, context_ref, decimals="2"):
    """Return a visible, signed and formatted monetary iXBRL fact."""
    amount = _decimal(value)
    attributes = [
        f'name="{name}"',
        f'contextRef="{context_ref}"',
        'unitRef="GBP"',
        f'decimals="{decimals}"',
        'scale="0"',
        'format="ixt:numdotdecimal"',
    ]
    if amount < 0:
        attributes.append('sign="-"')
    display = f"{abs(amount):,.2f}"
    fact = f"<ix:nonFraction {' '.join(attributes)}>{display}</ix:nonFraction>"
    return f"({fact})" if amount < 0 else fact


def _whole_number_fact(name, value, context_ref):
    """Return a non-negative whole-number iXBRL fact using xbrli:pure."""
    number = int(value or 0)
    if number < 0:
        raise ValueError(f"{name} cannot be negative.")
    return (
        f'<ix:nonFraction name="{name}" contextRef="{context_ref}" '
        f'unitRef="pure" decimals="0">{number}</ix:nonFraction>'
    )


def _non_numeric(name, value, context_ref):
    return f'<ix:nonNumeric name="{name}" contextRef="{context_ref}">{html.escape(str(value))}</ix:nonNumeric>'


def _statement_row(
    label,
    current,
    previous,
    tag,
    context="current_period",
    previous_context="previous_period",
    total=False,
    include_comparatives=False,
):
    row_class = ' class="total"' if total else ""
    previous_cell = (
        f'<td class="amount">{_money_fact(tag, previous, previous_context)}</td>'
        if include_comparatives else ""
    )
    return (
        f'<tr{row_class}><th scope="row">{html.escape(label)}</th>'
        '<td class="notes"></td>'
        f'<td class="amount">{_money_fact(tag, current, context)}</td>{previous_cell}</tr>'
    )


def _statement_table(title, period_end, current_year, previous_year, rows, include_comparatives=False):
    comparative_header = (
        f'<th scope="col" class="amount">{previous_year}<br />GBP</th>'
        if include_comparatives else ""
    )
    return (
        '<div class="statement page-break">'
        f"<h1>{html.escape(title)}</h1>"
        f"<p class=\"as-at\">For the year ended {html.escape(period_end)}</p>"
        '<table class="financial-statement"><thead><tr><th scope="col">Description</th>'
        '<th scope="col" class="notes">Notes</th>'
        f'<th scope="col" class="amount">{current_year}<br />GBP</th>{comparative_header}'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def statutory_accounts_facts(statutory_accounts, company_number, company_name):
    report = management_report_context(statutory_accounts.tenant)
    gross_assets = _decimal(report["gross_assets"])
    liabilities = _decimal(report["liabilities"])
    net_assets = _decimal(report["net_assets"])
    reported_equity = _decimal(report["equity"])
    current_profit = _decimal(report["profit"])
    # An open accounting period holds the year's result in income-statement
    # nominals. A statutory balance sheet must show it in retained reserves.
    equity = reported_equity
    if equity != net_assets:
        equity = (reported_equity + current_profit).quantize(Decimal("0.01"))
    return {
        "company_name": company_name,
        "company_number": company_number,
        "period_start": _iso_date(statutory_accounts.period_start),
        "period_end": _iso_date(statutory_accounts.period_end),
        "revenue": _decimal(report["revenue"]),
        "cost_of_sales": _decimal(report["cost_of_sales"]),
        "gross_profit": _decimal(report["gross_profit"]),
        "expenses": _decimal(report["expenses"]),
        "profit": _decimal(report["profit"]),
        "gross_assets": gross_assets,
        "liabilities": liabilities,
        "net_assets": net_assets,
        "equity": equity,
        "balance_difference": (gross_assets - liabilities - net_assets).quantize(Decimal("0.01")),
        "equity_difference": (net_assets - equity).quantize(Decimal("0.01")),
    }


def _previous_facts(statutory_accounts):
    """Return explicit comparatives only; never invent a previous period."""
    values = getattr(statutory_accounts, "comparative_facts", None) or {}
    return {key: _decimal(value) for key, value in values.items()}


def _comparative_period_dates(period_start, period_end):
    """Return the matching prior period dates for explicit comparative facts."""
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    try:
        return start.replace(year=start.year - 1).isoformat(), end.replace(year=end.year - 1).isoformat()
    except ValueError:
        # Only 29 February needs special treatment when shifting a year.
        return start.replace(year=start.year - 1, day=28).isoformat(), end.replace(year=end.year - 1, day=28).isoformat()


def generate_micro_entity_ixbrl(statutory_accounts, company_number, company_name):
    """Build a complete report-style XHTML/iXBRL document for local review.

    The retained function name avoids breaking the existing gateway flow while
    supporting all locally modelled account-type profiles.
    """
    facts = statutory_accounts_facts(statutory_accounts, company_number, company_name)
    previous = _previous_facts(statutory_accounts)
    include_comparatives = bool(previous)
    profile = _profile(statutory_accounts.accounts_type)
    period_start = facts["period_start"]
    period_end = facts["period_end"]
    current_year = period_end[:4]
    previous_year = str(int(current_year) - 1)
    approval_date = _iso_date(getattr(statutory_accounts, "approval_date", None) or "")
    approving_director = (getattr(statutory_accounts, "approving_director_name", "") or "").strip()
    escaped_company = html.escape(company_name)
    namespaces = "\n".join(
        f'xmlns:{prefix}="{uri}"' for prefix, uri in IXBRL_NAMESPACES.items() if prefix != "xhtml"
    )
    framework_member = "Micro-entities" if profile.framework == "FRS 105" else "FRS102"
    schema_framework = "FRS-102"
    comparative_contexts = ""
    if include_comparatives:
        previous_start, previous_end = _comparative_period_dates(period_start, period_end)
        comparative_contexts = f'''\n      <xbrli:context id="previous_period"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>{previous_start}</xbrli:startDate><xbrli:endDate>{previous_end}</xbrli:endDate></xbrli:period></xbrli:context>\n      <xbrli:context id="instant_previous"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>{previous_end}</xbrli:instant></xbrli:period></xbrli:context>'''
    visible_metadata = (
        f'<p>Company number: {_non_numeric("uk-bus:UKCompaniesHouseRegisteredNumber", company_number, "current_period")}</p>'
        f'<p>Period: {_non_numeric("uk-bus:StartDateForPeriodCoveredByReport", period_start, "instant_current")} '
        f'to {_non_numeric("uk-bus:EndDateForPeriodCoveredByReport", period_end, "instant_current")}</p>'
    )
    profit_rows = [
        _statement_row("Turnover", facts["revenue"], previous.get("revenue"), "uk-core:TurnoverRevenue", include_comparatives=include_comparatives),
        _statement_row("Cost of sales", facts["cost_of_sales"], previous.get("cost_of_sales"), "uk-core:CostSales", include_comparatives=include_comparatives),
        _statement_row("Gross profit", facts["gross_profit"], previous.get("gross_profit"), "uk-core:GrossProfitLoss", total=True, include_comparatives=include_comparatives),
        _statement_row("Administrative expenses", facts["expenses"], previous.get("expenses"), "uk-core:AdministrativeExpenses", include_comparatives=include_comparatives),
        _statement_row("Profit for the financial year", facts["profit"], previous.get("profit"), "uk-core:ProfitLoss", total=True, include_comparatives=include_comparatives),
    ]
    balance_rows = [
        _statement_row("Total assets", facts["gross_assets"], previous.get("gross_assets"), "uk-core:TotalAssets", "instant_current", "instant_previous", include_comparatives=include_comparatives),
        _statement_row("Creditors", facts["liabilities"], previous.get("liabilities"), "uk-core:Creditors", "instant_current", "instant_previous", include_comparatives=include_comparatives),
        _statement_row("Net assets", facts["net_assets"], previous.get("net_assets"), "uk-core:NetAssetsLiabilities", "instant_current", "instant_previous", total=True, include_comparatives=include_comparatives),
        _statement_row("Capital and reserves", facts["equity"], previous.get("equity"), "uk-core:Equity", "instant_current", "instant_previous", total=True, include_comparatives=include_comparatives),
    ]
    accounts_title = profile.title
    amended_notice = (
        '<p class="notice">These are amended accounts and replace a previously delivered set of accounts.</p>'
        if profile.amended else ""
    )
    dormant_notice = (
        '<p>The company was dormant throughout the accounting period.</p>' if profile.dormant else ""
    )
    dormant_audit_exemption_statement = (
        f'<p>{_non_numeric("direp:StatementThatCompanyEntitledToExemptionFromAuditUnderSection480CompaniesAct2006RelatingToDormantCompanies", "For the year ended " + period_end + " the company was entitled to exemption from audit under section 480 of the Companies Act 2006 relating to dormant companies.", "current_period")}</p>'
        if profile.dormant else ""
    )
    regime_statement = (
        "These financial statements have been prepared in accordance with the provisions applicable to companies subject to the micro-entities regime."
        if profile.framework == "FRS 105"
        else "These financial statements have been prepared in accordance with the provisions applicable to companies subject to the small companies regime."
    )
    profit_statement = _statement_table("Profit and Loss Account", period_end, current_year, previous_year, profit_rows, include_comparatives) if profile.include_profit_and_loss else ""
    notes_section = (
        '<div class="statement page-break"><h1>Notes to the Financial Statements</h1>'
        f'<h2>Accounting framework</h2><p>{html.escape(profile.framework)}</p>'
        '<h2>General information</h2>'
        f'<p>{_non_numeric("uk-bus:EntityCurrentLegalOrRegisteredName", company_name, "current_period")} '
        'is a private company registered in England and Wales.</p></div>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="{IXBRL_NAMESPACES["xhtml"]}" {namespaces}>
<head>
  <title>{escaped_company} - {html.escape(accounts_title)}</title>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=UTF-8" />
  <style type="text/css">
    @page {{ size: A4; margin: 18mm; }}
    body {{ color: #111; font-family: Arial, Helvetica, sans-serif; font-size: 10pt; line-height: 1.35; margin: 0 auto; max-width: 180mm; }}
    .cover {{ min-height: 235mm; display: flex; flex-direction: column; justify-content: center; text-align: center; }}
    .cover h1 {{ font-size: 20pt; margin: 0 0 18pt; }} .cover h2 {{ font-size: 15pt; font-weight: normal; margin: 0 0 24pt; }}
    .statement {{ break-before: page; page-break-before: always; }} .statement h1 {{ font-size: 15pt; text-align: center; margin: 0 0 3pt; }}
    .statement h2 {{ font-size: 11pt; margin-top: 18pt; }} .as-at {{ text-align: center; margin: 0 0 18pt; }}
    .financial-statement {{ border-collapse: collapse; margin: 12pt 0; width: 100%; }}
    .financial-statement th, .financial-statement td {{ padding: 5pt 3pt; vertical-align: top; }}
    .financial-statement thead th {{ border-bottom: 1px solid #111; font-weight: bold; text-align: left; }}
    .financial-statement .notes {{ text-align: center; width: 8%; }} .financial-statement .amount {{ text-align: right; width: 18%; white-space: nowrap; }}
    .financial-statement tbody th {{ font-weight: normal; text-align: left; }}
    .financial-statement .total th, .financial-statement .total td {{ border-top: 1px solid #111; font-weight: bold; }}
    .financial-statement .total:last-child th, .financial-statement .total:last-child td {{ border-bottom: 3px double #111; }}
    ix\\:hidden {{ display: none; }}
    .statements {{ margin-top: 22pt; }} .notice {{ border: 1px solid #111; padding: 8pt; font-weight: bold; }}
    .approval {{ margin-top: 24pt; page-break-inside: avoid; }}
    @media print {{ .page-break {{ break-before: page; page-break-before: always; }} }}
  </style>
</head>
<body>
  <div style="display: none;">
  <ix:header>
    <ix:hidden>
      <ix:nonNumeric name="uk-bus:AccountsType" contextRef="accounts_type" />
      <ix:nonNumeric name="uk-bus:AccountsStatusAuditedOrUnaudited" contextRef="accounts_status" />
      {_non_numeric("uk-bus:BalanceSheetDate", period_end, "instant_current")}
      {_non_numeric("uk-bus:EntityDormantTruefalse", str(profile.dormant).lower(), "current_period")}
      <ix:nonNumeric name="uk-bus:EntityTradingStatus" contextRef="current_period" />
      <ix:nonNumeric name="uk-bus:AccountingStandardsApplied" contextRef="accounting_standard" />
      <ix:nonNumeric name="uk-core:DirectorSigningFinancialStatements" contextRef="director_1" />
      {_whole_number_fact("uk-core:AverageNumberEmployeesDuringPeriod", getattr(statutory_accounts, "average_number_employees", 0), "current_period")}
    </ix:hidden>
    <ix:references>
      <link:schemaRef xlink:type="simple" xlink:href="https://xbrl.frc.org.uk/{schema_framework}/{TAXONOMY_VERSION}/{schema_framework}-{TAXONOMY_VERSION}.xsd" />
    </ix:references>
    <ix:resources>
      <xbrli:context id="current_period"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period></xbrli:context>
      {comparative_contexts}
      <xbrli:context id="instant_current"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>{period_end}</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:context id="accounts_type"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="uk-bus:AccountsTypeDimension">uk-bus:FullAccounts</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="accounts_status"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="uk-bus:AccountsStatusDimension">uk-bus:AuditExempt-NoAccountantsReport</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="accounting_standard"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="uk-bus:AccountingStandardsDimension">uk-bus:{framework_member}</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="director_1"><xbrli:entity><xbrli:identifier scheme="http://www.companieshouse.gov.uk/">{html.escape(company_number)}</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="uk-bus:EntityOfficersDimension">uk-bus:Director1</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{period_start}</xbrli:startDate><xbrli:endDate>{period_end}</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:unit id="GBP"><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
      <xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
    </ix:resources>
  </ix:header>
  </div>
  <div class="cover"><h1>{_non_numeric("uk-bus:EntityCurrentLegalOrRegisteredName", company_name, "current_period")}</h1><h2>{html.escape(accounts_title)}</h2>{visible_metadata}<p>Unaudited financial statements for the year ended {html.escape(period_end)}</p>{amended_notice}</div>
  {profit_statement}
  {_statement_table("Balance Sheet", period_end, current_year, previous_year, balance_rows, include_comparatives)}
  <div class="statement page-break"><h1>Approval and Statutory Statements</h1>{dormant_notice}
    {dormant_audit_exemption_statement}
    <p>{_non_numeric("direp:StatementThatCompanyEntitledToExemptionFromAuditUnderSection477CompaniesAct2006RelatingToSmallCompanies", "For the year ended " + period_end + " the company was entitled to exemption from audit under section 477 of the Companies Act 2006 relating to small companies.", "current_period")}</p>
    <p>{_non_numeric("direp:StatementThatMembersHaveNotRequiredCompanyToObtainAnAudit", "The members have not required the company to obtain an audit of its accounts for the year in question in accordance with section 476 of the Companies Act 2006.", "current_period")}</p>
    <p>{_non_numeric("direp:StatementThatDirectorsAcknowledgeTheirResponsibilitiesUnderCompaniesAct", "The directors acknowledge their responsibilities for complying with the requirements of the Companies Act 2006 with respect to accounting records and the preparation of accounts.", "current_period")}</p>
    <p>{_non_numeric("direp:StatementThatAccountsHaveBeenPreparedInAccordanceWithProvisionsSmallCompaniesRegime", regime_statement, "current_period")}</p>
    <div class="approval"><p>The financial statements were approved by the director on {_non_numeric("uk-core:DateAuthorisationFinancialStatementsForIssue", approval_date or "Approval date required before filing", "instant_current")}.</p><p>Signed: {html.escape(approving_director or "Director approval required before filing")}</p></div>
  </div>
  {notes_section}
</body></html>'''


def validate_micro_entity_ixbrl(ixbrl_text, statutory_accounts, company_number):
    """Perform strict local structural and report-presentation checks.

    This does not replace the Companies House standalone validator.  It stops a
    document reaching that external stage when its structure, arithmetic or
    presentation is already known to be unsuitable.
    """
    messages = []
    facts = {}
    if not ixbrl_text.startswith('<?xml version="1.0" encoding="UTF-8"?>'):
        messages.append("iXBRL must start with the UTF-8 XML declaration.")
    presentation_resource = re.search(
        r'<(?:img|script)\b[^>]*src=["\']https?://|<link\s[^>]*href=["\']https?://',
        ixbrl_text,
        flags=re.IGNORECASE,
    )
    if "<script" in ixbrl_text.lower() or presentation_resource:
        messages.append("The report must not contain scripts or external presentation resources.")
    try:
        root = ET.fromstring(ixbrl_text.encode("utf-8"))
    except ET.ParseError as exc:
        return IxbrlValidationResult(False, [f"iXBRL is not well-formed XML: {exc}"], facts)

    ns = IXBRL_NAMESPACES
    if root.tag != f"{{{IXBRL_NAMESPACES['xhtml']}}}html":
        messages.append("Root element must be XHTML html.")
    if root.find(".//ix:header", ns) is None:
        messages.append("Inline XBRL header is missing.")
    if root.find(".//link:schemaRef", ns) is None:
        messages.append("At least one taxonomy schemaRef is required.")
    if root.find(".//xhtml:style", ns) is None:
        messages.append("Accounts XHTML must embed its report stylesheet.")
    tables = root.findall(".//xhtml:table", ns)
    profile = _profile(statutory_accounts.accounts_type)
    minimum_tables = 2 if profile.include_profit_and_loss else 1
    if len(tables) < minimum_tables:
        messages.append("Accounts report must contain structured financial-statement tables.")
    statement_tables = [
        table
        for table in tables
        if "financial-statement" in table.attrib.get("class", "").split()
    ]
    page_sections = [
        container
        for container in root.findall(".//xhtml:div", ns)
        if "page-break" in container.attrib.get("class", "").split()
    ]
    if len(statement_tables) < minimum_tables or not page_sections:
        messages.append("Accounts report must use statement tables and page-break presentation classes.")

    contexts = {item.attrib.get("id") for item in root.findall(".//xbrli:context", ns)}
    comparative_facts = _previous_facts(statutory_accounts)
    required_contexts = {"current_period", "instant_current"}
    if comparative_facts:
        required_contexts.update({"previous_period", "instant_previous"})
    if not required_contexts.issubset(contexts):
        messages.append("Required current and instant contexts are missing, including comparative contexts where comparative facts were supplied.")
    expected_comparative_keys = {
        "revenue", "cost_of_sales", "gross_profit", "expenses", "profit",
        "gross_assets", "liabilities", "net_assets", "equity",
    }
    missing_comparatives = sorted(expected_comparative_keys - set(comparative_facts)) if comparative_facts else []
    if missing_comparatives:
        messages.append("Comparative facts are incomplete: " + ", ".join(missing_comparatives))
    identifiers = root.findall(".//xbrli:identifier", ns)
    if not identifiers or any((item.text or "").strip() != company_number for item in identifiers):
        messages.append("Every iXBRL context must use the filing company number.")
    units = {item.attrib.get("id") for item in root.findall(".//xbrli:unit", ns)}
    if not {"GBP", "pure"}.issubset(units):
        messages.append("GBP and pure units are required for filing facts.")

    for item in root.findall(".//ix:nonFraction", ns):
        name = item.attrib.get("name", "")
        facts[name] = (item.text or "").strip()
        if not item.attrib.get("contextRef") or not item.attrib.get("unitRef"):
            messages.append(f"Fact {name} has no contextRef or unitRef.")
        expected_unit = "pure" if name == "uk-core:AverageNumberEmployeesDuringPeriod" else "GBP"
        if item.attrib.get("unitRef") != expected_unit:
            messages.append(f"Fact {name} must use {expected_unit}.")
        if not item.attrib.get("decimals"):
            messages.append(f"Fact {name} must declare decimals.")
        if expected_unit == "GBP" and not item.attrib.get("scale"):
            messages.append(f"Monetary fact {name} must declare scale.")
        numeric_value = (item.text or "").replace(",", "").strip()
        if not re.fullmatch(r"\d+(\.\d{1,2})?", numeric_value):
            messages.append(f"Fact {name} is not a valid displayed decimal number.")

    required = {
        "uk-bus:EntityCurrentLegalOrRegisteredName",
        "uk-bus:UKCompaniesHouseRegisteredNumber",
        "uk-bus:BalanceSheetDate",
        "uk-bus:StartDateForPeriodCoveredByReport",
        "uk-bus:EndDateForPeriodCoveredByReport",
        "uk-bus:AccountingStandardsApplied",
        "uk-bus:AccountsType",
        "uk-core:DateAuthorisationFinancialStatementsForIssue",
        "uk-core:DirectorSigningFinancialStatements",
        "uk-core:AverageNumberEmployeesDuringPeriod",
        "uk-core:TotalAssets",
        "uk-core:Creditors",
        "uk-core:NetAssetsLiabilities",
        "uk-core:Equity",
    }
    if profile.include_profit_and_loss:
        required.update({"uk-core:TurnoverRevenue", "uk-core:ProfitLoss"})
    present = {item.attrib.get("name", "") for item in root.findall(".//ix:nonFraction", ns)}
    present.update(item.attrib.get("name", "") for item in root.findall(".//ix:nonNumeric", ns))
    missing = sorted(required - present)
    if missing:
        messages.append("Required iXBRL facts are missing: " + ", ".join(missing))

    approval_date = getattr(statutory_accounts, "approval_date", None)
    approving_director = (getattr(statutory_accounts, "approving_director_name", "") or "").strip()
    if not approval_date:
        messages.append("Approval date must be recorded before generating filing iXBRL.")
    if not approving_director:
        messages.append("Approving director name must be recorded before generating filing iXBRL.")
    if "required before filing" in ixbrl_text:
        messages.append("Generated iXBRL contains approval placeholder text.")

    account_facts = statutory_accounts_facts(statutory_accounts, company_number, statutory_accounts.tenant.name)
    if account_facts["balance_difference"] != Decimal("0.00"):
        messages.append("Balance sheet does not balance: assets less liabilities must equal net assets.")
    if account_facts["equity_difference"] != Decimal("0.00"):
        messages.append("Balance sheet does not balance: net assets must equal capital and reserves.")
    return IxbrlValidationResult(not messages, messages, facts)
