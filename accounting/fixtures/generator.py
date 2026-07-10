import json
import os
import sys
from pathlib import Path

# Add current file directory to python path for simple script execution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from factory import SyntheticCompanyFactory

def main():
    # Setup directories
    current_dir = Path(__file__).parent
    output_dir = current_dir / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Instantiate the factory with a fixed seed
    factory = SyntheticCompanyFactory(seed=42)
    data = factory.generate_all()

    # Save care provider fixtures
    care_provider_data = {
        "metadata": data["companies"]["care_provider"],
        "fixtures": data["fixtures"]["care_provider"],
        "expected_results": data["expected_results"]["care_provider"]
    }
    with open(output_dir / "care_provider.json", "w", encoding="utf-8") as f:
        json.dump(care_provider_data, f, indent=4)
    print(f"Saved care provider fixtures to {output_dir / 'care_provider.json'}")

    # Save consultancy fixtures
    consultancy_data = {
        "metadata": data["companies"]["consultancy"],
        "fixtures": data["fixtures"]["consultancy"],
        "expected_results": data["expected_results"]["consultancy"]
    }
    with open(output_dir / "consultancy.json", "w", encoding="utf-8") as f:
        json.dump(consultancy_data, f, indent=4)
    print(f"Saved consultancy fixtures to {output_dir / 'consultancy.json'}")

    # Save trading company fixtures
    trading_company_data = {
        "metadata": data["companies"]["trading_company"],
        "fixtures": data["fixtures"]["trading_company"],
        "expected_results": data["expected_results"]["trading_company"]
    }
    with open(output_dir / "trading_company.json", "w", encoding="utf-8") as f:
        json.dump(trading_company_data, f, indent=4)
    print(f"Saved trading company fixtures to {output_dir / 'trading_company.json'}")

    # Save expected results & rejection scenarios
    meta_expected = {
        "rejection_scenarios": data["rejection_scenarios"],
        "companies_metadata": data["companies"]
    }
    with open(output_dir / "expected_results.json", "w", encoding="utf-8") as f:
        json.dump(meta_expected, f, indent=4)
    print(f"Saved global expected results metadata to {output_dir / 'expected_results.json'}")

if __name__ == "__main__":
    main()
