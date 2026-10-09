from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO, StringIO
import zipfile

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from accounting.models import Tenant
from accounting.reports import (
    client_data_export_zip,
    management_report_context,
    management_report_csv,
    management_report_pack_pdf,
    management_report_pdf,
)


@dataclass(frozen=True)
class RehearsalItem:
    name: str
    passed: bool
    detail: str


class Command(BaseCommand):
    help = "Run locally-checkable LedgerHouse production rehearsal checks without external services."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any local rehearsal item fails.",
        )

    def handle(self, *args, **options):
        items = self._items()
        failures = [item for item in items if not item.passed]

        self.stdout.write("LedgerHouse local production rehearsal")
        self.stdout.write("=" * 42)
        for item in items:
            marker = "PASS" if item.passed else "FAIL"
            self.stdout.write(f"[{marker}] {item.name}")
            self.stdout.write(f"       {item.detail}")

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"{len(failures)} local rehearsal item(s) failed."))
            if options["strict"]:
                raise CommandError("Local production rehearsal failed.")
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("All local production rehearsal checks passed."))

    def _items(self):
        items = [
            self._django_system_check(),
            self._migration_check(),
            self._database_backend_check(),
            self._tenant_data_check(),
        ]
        items.extend(self._report_export_checks())
        return items

    def _django_system_check(self):
        output = StringIO()
        try:
            call_command("check", stdout=output)
        except Exception as exc:
            return RehearsalItem("Django system check", False, str(exc))
        return RehearsalItem("Django system check", True, "Django check completed without errors.")

    def _migration_check(self):
        try:
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:
            return RehearsalItem("Migration state", False, f"Could not inspect migrations: {exc}")
        if plan:
            return RehearsalItem("Migration state", False, f"{len(plan)} migration operation(s) are unapplied.")
        return RehearsalItem("Migration state", True, "All migrations are applied in the active database.")

    def _database_backend_check(self):
        return RehearsalItem(
            "Database backend",
            connection.vendor == "postgresql",
            f"Active database backend is {connection.vendor}.",
        )

    def _tenant_data_check(self):
        tenant_count = Tenant.objects.count()
        return RehearsalItem(
            "Tenant data",
            tenant_count > 0,
            f"{tenant_count} tenant record(s) available for local rehearsal.",
        )

    def _report_export_checks(self):
        tenant = Tenant.objects.order_by("name").first()
        if not tenant:
            return [
                RehearsalItem(
                    "Report/export generation",
                    False,
                    "No tenant exists, so report and export generation could not be rehearsed.",
                )
            ]

        checks = []
        try:
            report = management_report_context(tenant)
            checks.append(
                RehearsalItem(
                    "Management report context",
                    bool(report.get("action_points")),
                    f"Generated context for {tenant.name} with {len(report.get('action_points', []))} action point(s).",
                )
            )
        except Exception as exc:
            checks.append(RehearsalItem("Management report context", False, str(exc)))

        try:
            csv_report = management_report_csv(tenant)
            checks.append(
                RehearsalItem(
                    "CSV report export",
                    "Action point" in csv_report and tenant.name in csv_report,
                    f"CSV report generated for {tenant.name}.",
                )
            )
        except Exception as exc:
            checks.append(RehearsalItem("CSV report export", False, str(exc)))

        try:
            pdf_report = management_report_pdf(tenant)
            pack_report = management_report_pack_pdf(tenant)
            checks.append(
                RehearsalItem(
                    "PDF report exports",
                    pdf_report.startswith(b"%PDF") and pack_report.startswith(b"%PDF"),
                    f"Standard PDF and management pack generated for {tenant.name}.",
                )
            )
        except Exception as exc:
            checks.append(RehearsalItem("PDF report exports", False, str(exc)))

        try:
            export_zip = client_data_export_zip(tenant)
            with zipfile.ZipFile(BytesIO(export_zip)) as exported:
                names = set(exported.namelist())
            checks.append(
                RehearsalItem(
                    "Client data export",
                    {"README.txt", "journals.csv", "journal_lines.csv"}.issubset(names),
                    f"Data export ZIP generated for {tenant.name} with {len(names)} file(s).",
                )
            )
        except Exception as exc:
            checks.append(RehearsalItem("Client data export", False, str(exc)))

        return checks
