from pathlib import Path

from django.core.management.base import BaseCommand

from accounting.hmrc_services import build_hmrc_application_evidence


class Command(BaseCommand):
    help = "Build a redacted HMRC service approval and local-preflight evidence register."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="output/hmrc/ledgerhouse_hmrc_application_evidence.md",
            help="Path for the redacted evidence report.",
        )

    def handle(self, *args, **options):
        output_path = build_hmrc_application_evidence(Path(options["output"]))
        self.stdout.write(self.style.SUCCESS(f"HMRC application evidence written to {output_path}"))
