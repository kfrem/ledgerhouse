from django.core.management.base import BaseCommand, CommandError

from accounting.companies_house_scenarios import build_companies_house_local_scenarios


class Command(BaseCommand):
    help = "Build and validate local Companies House accounts filing scenarios without sending to the gateway."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Exit non-zero if any scenario fails.")

    def handle(self, *args, **options):
        results = build_companies_house_local_scenarios(username="management-command")
        failures = [result for result in results if not result.passed]

        self.stdout.write("LedgerHouse Companies House local scenario build")
        self.stdout.write("=" * 52)
        for result in results:
            marker = "PASS" if result.passed else "FAIL"
            self.stdout.write(
                f"[{marker}] {result.slug} | {result.accounts_type} | draft {result.draft_id}"
            )
            self.stdout.write(
                "       "
                f"iXBRL={result.ixbrl_passed} "
                f"readiness={result.readiness_passed} "
                f"gateway_xml={result.gateway_xml_built}"
            )
            if result.messages:
                self.stdout.write("       " + " | ".join(result.messages))

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"{len(failures)} scenario(s) failed."))
            if options["strict"]:
                raise CommandError("Companies House scenario build failed.")
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"All {len(results)} Companies House local scenarios passed."))
