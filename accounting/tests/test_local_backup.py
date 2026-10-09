from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from django.test import TestCase

from accounting.local_backup import create_local_backup, verify_local_backup
from accounting.models import AuditEvent, Tenant


class LocalBackupTests(TestCase):
    def test_backup_checksum_and_rollback_only_restore_rehearsal_pass(self):
        Tenant.objects.create(name="Backup rehearsal client")
        AuditEvent.objects.create(
            tenant=Tenant.objects.get(name="Backup rehearsal client"),
            event_type="BackupTest",
            username="practice",
            description="Prove immutable audit records are handled safely.",
        )
        with TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "ledgerhouse.zip"
            backup = create_local_backup(archive_path)
            result = verify_local_backup(archive_path, restore_rehearsal=True)

        self.assertTrue(archive_path.name.endswith(".zip"))
        self.assertGreater(backup["record_count"], 0)
        self.assertTrue(result["checksum_verified"])
        self.assertTrue(result["restore_rehearsal"])
        self.assertEqual(
            result["restored_records"] + result["immutable_records_validated"],
            backup["record_count"],
        )
        self.assertGreaterEqual(result["immutable_records_validated"], 1)
        self.assertTrue(Tenant.objects.filter(name="Backup rehearsal client").exists())

    def test_tampered_backup_is_rejected(self):
        with TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "ledgerhouse.zip"
            create_local_backup(archive_path)
            archive_path.write_bytes(b"not a zip")
            with self.assertRaises(BadZipFile):
                verify_local_backup(archive_path)
