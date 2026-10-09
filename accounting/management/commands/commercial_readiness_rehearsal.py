"""Run a non-destructive commercial rehearsal against LedgerHouse demo data."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import zipfile

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from accounting.audit import generate_trial_balance
from accounting.models import (
    BankTransaction,
    CompaniesHouseFilingSubmission,
    EvidenceDocument,
    Journal,
    ManagementPackSection,
    StatutoryAccountsDraft,
    Tenant,
)
from accounting.production import accounts_production_snapshot
from accounting.reports import (
    client_data_export_zip,
    management_report_context,
    management_report_pack_pdf,
    management_report_pdf,
)


DEMO_CLIENTS = (
    "CareCo Limited",
    "ConsultCo Consulting",
    "TradeCo Retail",
    "TechCo Software Ltd",
    "LogisticsCo Transport Ltd",
    "CharityCo Foundation",
)


@dataclass(frozen=True)
class RehearsalCheck:
    client: str
    check: str
    passed: bool
    detail: str


class Command(BaseCommand):
    help = "Verify commercial LedgerHouse outcomes with existing synthetic data and no external filing."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero if a rehearsal check fails.")
        parser.add_argument(
            "--output",
            default="docs/testing/commercial_readiness_rehearsal_latest.md",
            help="Markdown report path, relative to the project root.",
        )

    def handle(self, *args, **options):
        clients = list(Tenant.objects.filter(name__in=DEMO_CLIENTS).order_by("name"))
        checks = []
        if len(clients) != len(DEMO_CLIENTS):
            missing = sorted(set(DEMO_CLIENTS) - {client.name for client in clients})
            checks.append(RehearsalCheck("Portfolio", "Synthetic portfolio", False, f"Missing: {', '.join(missing)}."))

        practice_client = Client()
        practice_client.force_login(self._practice_user())
        for tenant in clients:
            checks.extend(self._client_checks(tenant, practice_client))

        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._report(checks), encoding="utf-8")

        failures = [check for check in checks if not check.passed]
        for check in checks:
            marker = "PASS" if check.passed else "FAIL"
            self.stdout.write(f"[{marker}] {check.client} | {check.check} | {check.detail}")
        self.stdout.write(f"Report written to {output_path}")
        if failures and options["strict"]:
            raise CommandError(f"Commercial rehearsal failed with {len(failures)} check(s).")
        if not failures:
            self.stdout.write(self.style.SUCCESS("Commercial readiness rehearsal passed."))

    def _practice_user(self):
        model = get_user_model()
        user, _ = model.objects.get_or_create(
            username="commercial-rehearsal",
            defaults={"is_staff": True, "is_superuser": True},
        )
        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        return user

    def _client_checks(self, tenant, practice_client):
        checks = []
        evidence = EvidenceDocument.objects.filter(tenant=tenant).count()
        journals = Journal.objects.filter(tenant=tenant).count()
        bank_lines = BankTransaction.objects.filter(tenant=tenant).count()
        checks.append(RehearsalCheck(
            tenant.name,
            "Evidence-to-ledger intake",
            evidence > 0 and journals > 0,
            f"{evidence} evidence document(s), {journals} journal(s).",
        ))
        checks.append(RehearsalCheck(
            tenant.name,
            "Bank activity",
            bank_lines > 0,
            f"{bank_lines} imported bank line(s).",
        ))

        try:
            trial_balance = generate_trial_balance(tenant)
            total = round(sum(line["net"] for line in trial_balance), 2)
            checks.append(RehearsalCheck(
                tenant.name,
                "Double-entry control",
                total == 0,
                f"Trial-balance total is {total:.2f}.",
            ))
        except Exception as exc:
            checks.append(RehearsalCheck(tenant.name, "Double-entry control", False, str(exc)))

        try:
            report = management_report_context(tenant)
            pdf = management_report_pdf(tenant)
            pack = management_report_pack_pdf(tenant)
            export = client_data_export_zip(tenant)
            with zipfile.ZipFile(BytesIO(export)) as archive:
                export_ok = {"README.txt", "journals.csv", "journal_lines.csv"}.issubset(archive.namelist())
            checks.append(RehearsalCheck(
                tenant.name,
                "Client reports and exports",
                bool(report.get("action_points")) and pdf.startswith(b"%PDF") and pack.startswith(b"%PDF") and export_ok,
                f"Report action points: {len(report.get('action_points', []))}; PDF, pack and data export generated.",
            ))
        except Exception as exc:
            checks.append(RehearsalCheck(tenant.name, "Client reports and exports", False, str(exc)))

        production = accounts_production_snapshot(tenant)
        drafts = StatutoryAccountsDraft.objects.filter(tenant=tenant).count()
        packs = ManagementPackSection.objects.filter(tenant=tenant).count()
        checks.append(RehearsalCheck(
            tenant.name,
            "Accounts production register",
            len(production["annual_register"]) == drafts and len(production["management_register"]) <= packs,
            f"{len(production['annual_register'])} annual register row(s), {len(production['management_register'])} management register row(s).",
        ))

        production_response = practice_client.get(
            reverse("practice_accounts_production"), {"company": tenant.id}, HTTP_HOST="localhost"
        )
        checks.append(RehearsalCheck(
            tenant.name,
            "Practice production screen",
            production_response.status_code == 200 and b"Controlled filing register" in production_response.content,
            f"Returned {production_response.status_code}.",
        ))

        submissions = CompaniesHouseFilingSubmission.objects.filter(tenant=tenant)
        live_submissions = submissions.filter(gateway_test=0).count()
        checks.append(RehearsalCheck(
            tenant.name,
            "External filing safety",
            live_submissions == 0,
            f"{submissions.count()} recorded test/local submission(s); {live_submissions} live submission(s).",
        ))
        return checks

    def _report(self, checks):
        lines = [
            "# LedgerHouse Commercial Readiness Rehearsal",
            "",
            "## Scope",
            "",
            "This non-destructive rehearsal uses existing synthetic client records. It does not send HMRC or Companies House filings, emails, payment instructions or bank-feed requests.",
            "",
            "## Results",
            "",
            "| Client | Check | Result | Detail |",
            "| --- | --- | --- | --- |",
        ]
        for check in checks:
            result = "PASS" if check.passed else "FAIL"
            detail = check.detail.replace("|", "/")
            lines.append(f"| {check.client} | {check.check} | {result} | {detail} |")
        lines.extend([
            "",
            "## Commercial Boundary",
            "",
            "Passing this rehearsal demonstrates local accounting workflow and output integrity for the synthetic portfolio. It is not evidence of live Companies House acceptance, HMRC production approval, payment collection, email delivery, bank-feed consent or a real-client filing.",
            "",
        ])
        return "\n".join(lines)
