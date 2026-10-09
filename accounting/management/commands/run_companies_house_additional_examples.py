from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounting.companies_house import poll_companies_house_submission_status, submit_companies_house_test_submission
from accounting.companies_house_scenarios import SCENARIO_SPECS, build_companies_house_local_scenarios
from accounting.models import CompaniesHouseFilingSubmission, StatutoryAccountsDraft, Tenant


RUN_LABEL = "xml-team-additional-examples-2026-07-30"
ADDITIONAL_SCENARIO_SLUGS = (
    "loss-making",
    "fixed-assets",
    "creditor-heavy",
    "small-full-asset-led",
    "small-full-low-margin",
    "small-full-loss-making",
    "filleted-services",
    "filleted-fixed-assets",
    "filleted-creditor-led",
    "dormant-capitalised",
    "dormant-reserves",
    "dormant-funded",
)


class Command(BaseCommand):
    help = "Run three additional, distinct Companies House test examples for each declared LedgerHouse filing type."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Send the authorised test batch to the XML Gateway.")
        parser.add_argument("--poll", action="store_true", help="Poll each submitted or previously-run batch item after sending.")
        parser.add_argument("--username", default="xml-team-additional-review", help="Audit username for this controlled run.")
        parser.add_argument(
            "--output",
            default="docs/testing/companies_house_additional_examples_2026_07_30.md",
            help="Sanitized Markdown run record.",
        )

    def handle(self, *args, **options):
        if options["send"] and not settings.COMPANIES_HOUSE_FILING_SEND_ENABLED:
            raise CommandError("Gateway sending is locked. Enable COMPANIES_HOUSE_FILING_SEND_ENABLED only for this controlled test run.")

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        build_companies_house_local_scenarios(username=options["username"])
        scenario_by_slug = {spec.slug: spec for spec in SCENARIO_SPECS}
        rows = []

        for slug in ADDITIONAL_SCENARIO_SLUGS:
            spec = scenario_by_slug[slug]
            tenant = Tenant.objects.get(name=spec.company_name)
            draft = (
                StatutoryAccountsDraft.objects.filter(tenant=tenant, accounts_type=spec.accounts_type)
                .order_by("-period_end", "-id")
                .first()
            )
            if not draft:
                raise CommandError(f"No statutory accounts draft is available for scenario '{slug}'.")

            submission = CompaniesHouseFilingSubmission.objects.filter(
                statutory_accounts=draft,
                created_by=RUN_LABEL,
            ).order_by("submission_number").first()
            action = "Already recorded; not resent"
            if not submission and options["send"]:
                submission = submit_companies_house_test_submission(
                    draft,
                    spec.company_number,
                    spec.company_name,
                    "TEST12",
                    created_by=RUN_LABEL,
                )
                action = "Sent to XML Gateway"
            elif not submission:
                action = "Ready; dry run only"

            if submission and options["poll"]:
                submission = poll_companies_house_submission_status(submission, username=options["username"])
                action += "; status polled"

            rows.append((slug, spec.accounts_type, submission, action))

        lines = [
            "# LedgerHouse Additional Companies House Test Examples",
            "",
            "Three distinct additional examples are included for each declared filing type. Amended accounts remain variants and are excluded from this separate-count batch.",
            "",
            "| Scenario | Filing type | Submission number | Recorded status | Gateway message | Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for slug, filing_type, submission, action in rows:
            number = f"{submission.submission_number:06d}" if submission else "Not allocated"
            status = submission.status if submission else "Not sent"
            messages = "; ".join(submission.validation_messages) if submission and submission.validation_messages else "None"
            lines.append(f"| {slug} | {filing_type} | {number} | {status} | {messages} | {action} |")
        lines.extend([
            "",
            "No authentication value, presenter ID or company authentication code is included in this record.",
            "Pending or Submitted is not an accepted filing result; XML Team review remains required.",
        ])
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for slug, filing_type, submission, action in rows:
            number = f"{submission.submission_number:06d}" if submission else "Not allocated"
            status = submission.status if submission else "Not sent"
            self.stdout.write(f"{slug} ({filing_type}): {number} | {status} | {action}")
        self.stdout.write(self.style.SUCCESS(f"Run record written to {output}"))
