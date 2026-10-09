from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand

from accounting.local_backup import create_local_backup, verify_local_backup


class Command(BaseCommand):
    help = "Create a local LedgerHouse data backup and optionally rehearse a rollback-only restore."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Destination ZIP. Defaults to backups/ledgerhouse-local-<timestamp>.zip")
        parser.add_argument("--restore-rehearsal", action="store_true", help="Deserialize inside a transaction then roll it back.")

    def handle(self, *args, **options):
        output = options["output"]
        if not output:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            output = Path("backups") / f"ledgerhouse-local-{timestamp}.zip"
        backup = create_local_backup(Path(output))
        self.stdout.write(self.style.SUCCESS(f"Backup created: {backup['path']} ({backup['record_count']} records)"))
        if options["restore_rehearsal"]:
            result = verify_local_backup(Path(output), restore_rehearsal=True)
            self.stdout.write(self.style.SUCCESS(
                "Rollback-only restore rehearsal passed: "
                f"{result['restored_records']} mutable records restored then rolled back; "
                f"{result['immutable_records_validated']} immutable audit records deserialized and validated."
            ))
