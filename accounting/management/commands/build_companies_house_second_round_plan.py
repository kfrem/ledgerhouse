from pathlib import Path

from django.core.management.base import BaseCommand

from accounting.companies_house import companies_house_initial_filing_scope
from accounting.models import CompaniesHouseFilingSubmission


class Command(BaseCommand):
    help = "Write the unsent second-round Companies House test plan without allocating submission numbers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="docs/testing/companies_house_second_round_test_plan.md",
            help="Markdown output path.",
        )

    def handle(self, *args, **options):
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# LedgerHouse Companies House Second-round Test Plan",
            "",
            "This plan is local preparation only. It does not allocate a submission number or send a Gateway request.",
            "",
            "| Declared filing type | First-round submissions | Last recorded status | Second-round action |",
            "| --- | --- | --- | --- |",
        ]
        for scope in companies_house_initial_filing_scope():
            submissions = CompaniesHouseFilingSubmission.objects.filter(
                statutory_accounts__accounts_type=scope["accounts_type"],
            ).order_by("submission_number")
            references = ", ".join(f"{item.submission_number:06d}" for item in submissions) or "Not yet submitted"
            status = submissions.last().status if submissions.exists() else "Not yet submitted"
            action = (
                "Await XML Team review; do not resend an existing recorded submission"
                if submissions.exists()
                else "Initial test requires explicit XML Team-authorised sending"
            )
            lines.append(f"| {scope['label']} | {references} | {status} | {action} |")
        lines.extend([
            "",
            "Unsupported types are deliberately excluded: audited, medium, large, group, interim, initial, LLP, CIC and other package accounts.",
            "",
            "The XML Team confirmed on 29 July 2026 that amended accounts are variants of the supported filing types, not a separate product filing type. LedgerHouse retains amended micro-entity scenarios as test evidence.",
        ])
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Second-round plan written to {output}"))
