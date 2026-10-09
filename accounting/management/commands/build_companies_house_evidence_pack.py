from pathlib import Path

from django.core.management.base import BaseCommand

from accounting.companies_house_evidence import build_companies_house_evidence_pack


class Command(BaseCommand):
    help = "Build a local Companies House evidence ZIP with iXBRL samples, sanitized XML and control reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="output/companies_house/ledgerhouse_companies_house_evidence_pack.zip",
            help="Path for the generated evidence ZIP.",
        )
        parser.add_argument("--username", default="loop-engineering")

    def handle(self, *args, **options):
        output_path = build_companies_house_evidence_pack(
            Path(options["output"]),
            username=options["username"],
        )
        self.stdout.write(self.style.SUCCESS(f"Companies House evidence pack written to {output_path}"))
