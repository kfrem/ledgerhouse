from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounting.companies_house import poll_companies_house_submission_status, submit_companies_house_test_submission
from accounting.companies_house_scenarios import SCENARIO_SPECS, build_companies_house_local_scenarios
from accounting.models import CompaniesHouseFilingSubmission, StatutoryAccountsDraft, Tenant


RUN_LABEL = "xml-team-round-2026-07-29"
REVIEW_SCENARIO_SLUGS = (
    "small-unaudited-filleted",
    "micro-profit",
    "small-unaudited",
    "dormant",
)


class Command(BaseCommand):
    help = "Run the controlled Companies House XML Team review batch after explicit scope confirmation."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Send the authorised test batch to the XML Gateway.")
        parser.add_argument("--poll", action="store_true", help="Poll each submitted or previously-run batch item after sending.")
        parser.add_argument("--username", default="xml-team-review", help="Audit username for this controlled run.")
        parser.add_argument(
            "--output",
            default="docs/testing/companies_house_xml_team_round_2026_07_29.md",
            help="Sanitized Markdown run record.",
        )

    def handle(self, *args, **options):
        if options["send"] and not settings.COMPANIES_HOUSE_FILING_SEND_ENABLED:
            raise CommandError("Gateway sending is locked. Enable COMPANIES_HOUSE_FILING_SEND_ENABLED only for this controlled test run.")

        username = options["username"]
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        build_companies_house_local_scenarios(username=username)
        scenario_by_slug = {spec.slug: spec for spec in SCENARIO_SPECS}
        rows = []

        for slug in REVIEW_SCENARIO_SLUGS:
            spec = scenario_by_slug[slug]
            tenant = Tenant.objects.get(name=spec.company_name)
            draft = (
                StatutoryAccountsDraft.objects.filter(
                    tenant=tenant,
                    accounts_type=spec.accounts_type,
                )
                .order_by("-period_end", "-id")
                .first()
            )
            if not draft:
                raise CommandError(f"No statutory accounts draft is available for scenario '{slug}'.")
            existing = CompaniesHouseFilingSubmission.objects.filter(
                statutory_accounts=draft,
                created_by=RUN_LABEL,
            ).order_by("submission_number").first()
            submission = existing
            action = "Already recorded; not resent"

            if not existing and options["send"]:
                submission = submit_companies_house_test_submission(
                    draft,
                    spec.company_number,
                    spec.company_name,
                    "TEST12",
                    created_by=RUN_LABEL,
                )
                action = "Sent to XML Gateway"
            elif not existing:
                action = "Ready; dry run only"

            if submission and options["poll"]:
                submission = poll_companies_house_submission_status(submission, username=username)
                action += "; status polled"

            rows.append(
                {
                    "slug": slug,
                    "filing_type": spec.accounts_type,
                    "submission_number": f"{submission.submission_number:06d}" if submission else "Not allocated",
                    "status": submission.status if submission else "Not sent",
                    "messages": "; ".join(submission.validation_messages) if submission and submission.validation_messages else "None",
                    "action": action,
                }
            )

        lines = [
            "# LedgerHouse Companies House XML Team Review Round",
            "",
            "Scope confirmed by the XML Team on 29 July 2026: Micro-entity, small unaudited full, small unaudited filleted and dormant accounts. Amended accounts are tested as variants, not a separate product filing type.",
            "",
            "| Scenario | Filing type | Submission number | Recorded status | Gateway message | Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            lines.append(
                f"| {row['slug']} | {row['filing_type']} | {row['submission_number']} | {row['status']} | {row['messages']} | {row['action']} |"
            )
        lines.extend([
            "",
            "No authentication value, presenter ID or company authentication code is included in this record.",
            "A Pending or Submitted gateway status is not an accepted filing result; XML Team review remains required.",
        ])
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for row in rows:
            self.stdout.write(
                f"{row['slug']}: {row['submission_number']} | {row['status']} | {row['action']}"
            )
        self.stdout.write(self.style.SUCCESS(f"Run record written to {output}"))
