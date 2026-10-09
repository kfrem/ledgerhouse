from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounting.local_completion import build_no_hmrc_completion_pack


class Command(BaseCommand):
    help = "Build local LedgerHouse completion evidence that does not need HMRC live approval."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="output/no_hmrc_completion",
            help="Directory where the local completion pack will be written.",
        )
        parser.add_argument("--username", default="loop-engineering")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if any tenant has fewer than 8 of 8 local phases passing.",
        )

    def handle(self, *args, **options):
        results = build_no_hmrc_completion_pack(
            Path(options["output_dir"]),
            username=options["username"],
        )
        failed = [result for result in results if not result.passed]
        for result in results:
            self.stdout.write(
                f"{result.tenant_name}: {result.passed_count}/{result.total_count} local phases "
                f"-> {result.output_dir}"
            )
        if failed and options["strict"]:
            raise CommandError(f"{len(failed)} tenant(s) did not pass all local no-HMRC phases.")
        self.stdout.write(self.style.SUCCESS(f"No-HMRC completion pack written to {Path(options['output_dir'])}"))
