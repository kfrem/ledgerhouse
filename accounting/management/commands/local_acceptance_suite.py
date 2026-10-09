from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounting.local_completion import build_no_hmrc_completion_zip
from accounting.models import Tenant
from accounting.operations import accounts_department_snapshot, build_local_accounts_department_suite


class Command(BaseCommand):
    help = "Run local LedgerHouse acceptance checks that do not need HMRC or external services."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="docs/testing/local_acceptance_suite_latest.md")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **options):
        username = options["username"]
        tenant = Tenant.objects.order_by("name").first() or Tenant.objects.create(name="LedgerHouse Acceptance Ltd")
        snapshot = build_local_accounts_department_suite(tenant, username=username)
        user = self._staff_user(username)
        client = Client()
        client.force_login(user)

        checks = []
        checks.append(self._phase_check(snapshot))
        checks.extend(self._page_checks(client, tenant))
        checks.extend(self._download_checks(client, tenant))
        checks.append(self._handover_zip_check(username))

        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self._report(tenant, snapshot, checks), encoding="utf-8")

        failures = [check for check in checks if not check["passed"]]
        for check in checks:
            marker = "PASS" if check["passed"] else "FAIL"
            self.stdout.write(f"[{marker}] {check['name']} - {check['detail']}")
        self.stdout.write(f"Report written to {output_path}")
        if failures and options["strict"]:
            raise CommandError(f"{len(failures)} local acceptance check(s) failed.")
        if failures:
            self.stdout.write(self.style.ERROR(f"{len(failures)} local acceptance check(s) failed."))
        else:
            self.stdout.write(self.style.SUCCESS("All local acceptance checks passed."))

    def _staff_user(self, username):
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True, "email": "admin@example.com"},
        )
        if not user.is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        return user

    def _phase_check(self, snapshot):
        return {
            "name": "Accounts department phases",
            "passed": snapshot["passed_count"] == snapshot["total_count"] == 8,
            "detail": f"{snapshot['passed_count']} of {snapshot['total_count']} local phases passing.",
        }

    def _page_checks(self, client, tenant):
        page_specs = [
            ("Client portal", reverse("client_portal") + f"?company={tenant.id}", "Your accounts department"),
            ("Practice dashboard", reverse("practice_dashboard"), "Practice overview"),
            ("Accounts department", reverse("practice_accounts_department") + f"?company={tenant.id}", "Accounts department suite"),
            ("Accounts production", reverse("practice_accounts_production") + f"?company={tenant.id}", "Controlled filing register"),
            ("Management report", reverse("management_report", args=[tenant.id]), "What the figures mean"),
        ]
        checks = []
        for name, url, expected in page_specs:
            response = client.get(url, HTTP_HOST="localhost")
            body = response.content.decode(errors="ignore")
            checks.append(
                {
                    "name": name,
                    "passed": response.status_code == 200 and expected in body,
                    "detail": f"{url} returned {response.status_code}; expected marker '{expected}'.",
                }
            )
        return checks

    def _download_checks(self, client, tenant):
        download_specs = [
            ("Management CSV", reverse("download_management_report", args=[tenant.id, "csv"]), "text/csv", b"Plain-English summary"),
            ("Management PDF", reverse("download_management_report", args=[tenant.id, "pdf"]), "application/pdf", b"%PDF"),
            ("Management pack", reverse("download_management_report", args=[tenant.id, "pack"]), "application/pdf", b"%PDF"),
            ("Accounts department pack", reverse("download_management_report", args=[tenant.id, "accounts-department-pack"]), "application/pdf", b"%PDF"),
            ("Client data ZIP", reverse("download_management_report", args=[tenant.id, "zip"]), "application/zip", b"PK"),
        ]
        checks = []
        for name, url, content_type, marker in download_specs:
            response = client.get(url, HTTP_HOST="localhost")
            marker_ok = response.content.startswith(marker) if marker in {b"%PDF", b"PK"} else marker in response.content
            checks.append(
                {
                    "name": name,
                    "passed": response.status_code == 200 and response["Content-Type"] == content_type and marker_ok,
                    "detail": f"{url} returned {response.status_code} with {response.get('Content-Type', '')}.",
                }
            )
        return checks

    def _handover_zip_check(self, username):
        pack_bytes, results = build_no_hmrc_completion_zip("output/local_acceptance_no_hmrc", username=username)
        return {
            "name": "No-HMRC handover ZIP",
            "passed": bool(pack_bytes.startswith(b"PK") and all(result.passed for result in results)),
            "detail": f"Generated ZIP with {len(results)} tenant result(s).",
        }

    def _report(self, tenant, snapshot, checks):
        lines = [
            "# LedgerHouse Local Acceptance Suite",
            "",
            f"Generated: {timezone.now().isoformat()}",
            f"Tenant checked: {tenant.name}",
            "",
            "## Phase Coverage",
            "",
            f"{snapshot['passed_count']} of {snapshot['total_count']} local accounts department phases passed.",
            "",
            "## Checks",
            "",
        ]
        for check in checks:
            marker = "PASS" if check["passed"] else "FAIL"
            lines.append(f"- {marker} {check['name']}: {check['detail']}")
        lines.extend(
            [
                "",
                "## External Boundary",
                "",
                "This acceptance suite deliberately avoids HMRC live filing, Companies House live filing, bank-feed access, payment provider actions, DNS changes and server deployment.",
                "",
                "## Next Developer Instruction",
                "",
                "Run `python manage.py local_acceptance_suite --strict` after local changes, then run the full Django regression suite before handover.",
            ]
        )
        return "\n".join(lines) + "\n"
