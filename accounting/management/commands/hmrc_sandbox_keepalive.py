from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounting.mtd import HmrcApiError, call_hmrc_sandbox_keepalive


class Command(BaseCommand):
    help = "Call LedgerHouse's harmless HMRC sandbox Hello World application endpoint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="docs/testing/hmrc_sandbox_keepalive_latest.md",
            help="Redacted evidence report path.",
        )

    def handle(self, *args, **options):
        try:
            evidence = call_hmrc_sandbox_keepalive()
        except (HmrcApiError, ValueError) as exc:
            raise CommandError(f"HMRC sandbox keep-alive failed: {exc}") from exc

        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "\n".join(
                [
                    "# LedgerHouse HMRC Sandbox Keep-Alive",
                    "",
                    "This record deliberately excludes client IDs, client secrets, tokens, OTPs and payloads.",
                    "",
                    "- Application: LedgerHouse",
                    f"- Endpoint: {evidence['endpoint']}",
                    f"- HTTP status: {evidence['http_status']}",
                    f"- Timestamp: {evidence['timestamp']}",
                    "- Result: successful sandbox application activity",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"HMRC sandbox keep-alive succeeded ({evidence['http_status']}); report written to {output_path}."
            )
        )
