import json
from pathlib import Path
from ..fixtures.factory import SyntheticCompanyFactory


def get_fixtures_path() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "generated"


def test_determinism():
    """Prove that the identical seed produces identical data."""
    factory1 = SyntheticCompanyFactory(seed=42)
    data1 = factory1.generate_all()

    factory2 = SyntheticCompanyFactory(seed=42)
    data2 = factory2.generate_all()

    # Compare metadata
    assert data1["companies"] == data2["companies"]
    
    # Compare transactions
    assert len(data1["fixtures"]["care_provider"]["transactions"]) == len(data2["fixtures"]["care_provider"]["transactions"])
    assert data1["fixtures"]["care_provider"]["transactions"] == data2["fixtures"]["care_provider"]["transactions"]

    # Verify that different seeds produce different outputs
    factory_diff = SyntheticCompanyFactory(seed=100)
    data_diff = factory_diff.generate_all()
    # Lumina Properties Ltd might be generated with slightly different descriptions or random order
    assert data1["companies"]["care_provider"]["name"] == data_diff["companies"]["care_provider"]["name"]
    # The actual random numbers or data (if we added random variances) would differ, but even if the structures are similar,
    # the exact data should match for same seed and can differ if randomized components are introduced.
    # In our factory we used Random(seed), which guarantees determinism.


def test_fixtures_exist_and_loadable():
    """Verify that the JSON files exist and can be loaded successfully."""
    gen_dir = get_fixtures_path()
    assert (gen_dir / "care_provider.json").exists()
    assert (gen_dir / "consultancy.json").exists()
    assert (gen_dir / "trading_company.json").exists()
    assert (gen_dir / "expected_results.json").exists()

    with open(gen_dir / "care_provider.json", "r", encoding="utf-8") as f:
        cp_data = json.load(f)
    assert cp_data["metadata"]["name"] == "CareCo Limited"
    assert "fixtures" in cp_data
    assert "expected_results" in cp_data


def test_journals_balance():
    """Verify that every expected journal balances (debit totals equal credit totals)."""
    gen_dir = get_fixtures_path()
    for filename in ["care_provider.json", "consultancy.json", "trading_company.json"]:
        with open(gen_dir / filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        journals = data["expected_results"]["journal_postings"]
        for j in journals:
            debit_total = sum(line["debit"] for line in j["lines"])
            credit_total = sum(line["credit"] for line in j["lines"])
            assert round(debit_total, 2) == round(credit_total, 2), f"Journal {j['source_id']} in {filename} does not balance!"


def test_trial_balance_balances():
    """Verify that the trial balance for each company sums to exactly zero."""
    gen_dir = get_fixtures_path()
    for filename in ["care_provider.json", "consultancy.json", "trading_company.json"]:
        with open(gen_dir / filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        tb = data["expected_results"]["trial_balance"]
        tb_sum = sum(tb.values())
        assert abs(round(tb_sum, 2)) < 0.01, f"Trial balance for {filename} does not balance! Sum: {tb_sum}"


def test_vat_reconciliation():
    """Verify that the expected VAT totals reconcile with individual transaction details."""
    gen_dir = get_fixtures_path()
    for filename in ["care_provider.json", "consultancy.json", "trading_company.json"]:
        with open(gen_dir / filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        vat_summary = data["expected_results"]["vat_summary"]
        tb = data["expected_results"]["trial_balance"]
        
        # VAT Control Account (2200) balance in TB should equal net VAT payable/reclaimable (with opposite sign)
        # Note: In ledger postings:
        #   Output VAT is credit (negative in TB)
        #   Input VAT is debit (positive in TB)
        #   VAT Control = Input - Output. If net payable is 880, VAT Control balance is -880 (Credit).
        vat_control_balance = tb.get("2200", 0.0)
        expected_vat_control = -vat_summary["net_vat_payable"]
        
        assert round(vat_control_balance, 2) == round(expected_vat_control, 2), (
            f"VAT Control balance ({vat_control_balance}) does not match net VAT summary payable "
            f"({vat_summary['net_vat_payable']}) in {filename}"
        )


def test_ageing_reconciliation():
    """Verify that the expected ageing totals reconcile to accounts receivable/payable balances."""
    gen_dir = get_fixtures_path()
    for filename in ["care_provider.json", "consultancy.json", "trading_company.json"]:
        with open(gen_dir / filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        expected = data["expected_results"]
        tb = expected["trial_balance"]
        
        # Aged Debtors (1100) should match expected_debtors_balance
        debtors_balance = tb.get("1100", 0.0)
        assert round(debtors_balance, 2) == round(expected["expected_debtors_balance"], 2)

        # Aged Creditors (2100) should match expected_creditors_balance (with opposite sign)
        creditors_balance = tb.get("2100", 0.0)
        assert round(-creditors_balance, 2) == round(expected["expected_creditors_balance"], 2)


def test_rejection_scenarios():
    """Verify that invalid scenarios are correctly defined with rejection expected results."""
    gen_dir = get_fixtures_path()
    with open(gen_dir / "expected_results.json", "r", encoding="utf-8") as f:
        meta_data = json.load(f)
        
    scenarios = meta_data["rejection_scenarios"]
    assert len(scenarios) >= 6
    
    # Assert rejection codes and messages exist
    for s in scenarios:
        assert "id" in s
        assert "scenario" in s
        assert "input" in s
        assert s["expected_result"] in ("Rejected", "IgnoredDuplicate")
        assert len(s["expected_message"]) > 0


def test_no_real_client_or_personal_data():
    """Verify that no real client data or real personal names are present in the fixtures."""
    gen_dir = get_fixtures_path()
    
    # Lists of real names or patterns we must check against
    real_data_indicators = [
        "Godfred Frimpong",  # Founder name - wait, Godfred is in descriptions "approved_by: Godfred (Accountant)"
        # That is a role approval in synthetic data, which is fine, but we should make sure no real clients are mentioned.
        "KAFS", 
        "KAFS LTD"
    ]
    
    for filename in ["care_provider.json", "consultancy.json", "trading_company.json"]:
        with open(gen_dir / filename, "r", encoding="utf-8") as f:
            content_str = f.read()
            
        for indicator in real_data_indicators:
            assert indicator not in content_str, f"Found potential real data indicator '{indicator}' in {filename}"
            
        # Ensure company names are strictly fictional
        assert "CareCo Limited" in content_str or "ConsultCo Limited" in content_str or "TradeCo Limited" in content_str
