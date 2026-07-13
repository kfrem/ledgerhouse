from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from accounting.companies_house import companies_house_status
from accounting.mtd import hmrc_sandbox_status


@dataclass
class ReadinessItem:
    name: str
    passed: bool
    detail: str
    required_for_launch: bool = True


class Command(BaseCommand):
    help = "Check LedgerHouse production-readiness gates that can be verified locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when any launch-required item fails.",
        )

    def handle(self, *args, **options):
        items = self._items()
        failed_required = [item for item in items if item.required_for_launch and not item.passed]

        self.stdout.write("LedgerHouse production readiness")
        self.stdout.write("=" * 36)
        for item in items:
            marker = "PASS" if item.passed else "WAIT"
            requirement = "required" if item.required_for_launch else "advisory"
            self.stdout.write(f"[{marker}] {item.name} ({requirement})")
            self.stdout.write(f"       {item.detail}")

        if failed_required:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{len(failed_required)} launch-required item(s) still need action."))
            if options["strict"]:
                raise SystemExit(1)
        else:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("All locally-checkable launch-required items passed."))

    def _items(self):
        hmrc_status = hmrc_sandbox_status()
        ch_status = companies_house_status()
        return [
            ReadinessItem(
                "DEBUG disabled",
                not settings.DEBUG,
                "Set DEBUG=False for production. Local development usually keeps DEBUG=True.",
            ),
            ReadinessItem(
                "Production SECRET_KEY",
                bool(settings.SECRET_KEY) and "dev-only" not in settings.SECRET_KEY and "dummy" not in settings.SECRET_KEY,
                "SECRET_KEY must be a long private value supplied outside Git.",
            ),
            ReadinessItem(
                "FIELD_ENCRYPTION_KEY",
                bool(getattr(settings, "FIELD_ENCRYPTION_KEY", "")),
                "Use a Fernet key outside Git so HMRC/bank tokens are encrypted independently of SECRET_KEY.",
            ),
            ReadinessItem(
                "TLS security toggle",
                bool(getattr(settings, "SECURE_SSL_REDIRECT", False) or getattr(settings, "SECURE_TLS", False)),
                "Production should force HTTPS at Django/reverse-proxy level.",
            ),
            ReadinessItem(
                "HMRC credentials configured",
                bool(hmrc_status.get("configured")),
                "Set HMRC client ID and secret after HMRC approval before live OAuth testing.",
                required_for_launch=False,
            ),
            ReadinessItem(
                "HMRC vendor public IP",
                getattr(settings, "HMRC_VENDOR_PUBLIC_IP", "127.0.0.1") not in {"", "127.0.0.1", "0.0.0.0"},
                "Set this to the real public egress/ingress IP used for HMRC-bound requests.",
                required_for_launch=False,
            ),
            ReadinessItem(
                "HMRC vendor version",
                getattr(settings, "HMRC_VENDOR_VERSION", "LedgerHouse=local") != "LedgerHouse=local",
                "Set a release version such as LedgerHouse=2026.07.1 before live HMRC calls.",
                required_for_launch=False,
            ),
            ReadinessItem(
                "Companies House key configured",
                bool(ch_status.get("configured")),
                "Set COMPANIES_HOUSE_API_KEY or a local key file before Companies House API use.",
                required_for_launch=False,
            ),
            ReadinessItem(
                "PostgreSQL backend",
                connection.vendor == "postgresql",
                "LedgerHouse relies on PostgreSQL constraints, triggers and RLS tests.",
            ),
            self._database_role_item(),
        ]

    def _database_role_item(self):
        if connection.vendor != "postgresql":
            return ReadinessItem(
                "Restricted database role",
                False,
                "Cannot verify restricted role because the active backend is not PostgreSQL.",
            )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
                row = cursor.fetchone()
        except Exception as exc:
            return ReadinessItem(
                "Restricted database role",
                False,
                f"Could not inspect database role: {exc}",
            )
        if not row:
            return ReadinessItem("Restricted database role", False, "Current database role was not found in pg_roles.")
        username, is_superuser, bypasses_rls = row
        return ReadinessItem(
            "Restricted database role",
            not is_superuser and not bypasses_rls,
            f"Current role: {username}. Production should use deploy/create_app_role.sql and must not bypass RLS.",
        )
