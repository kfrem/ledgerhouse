"""Local-only database backup and restore-rehearsal helpers."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone as datetime_timezone
from io import StringIO
from pathlib import Path

from django import get_version
from django.core.management import call_command
from django.core.serializers import deserialize
from django.db import transaction


BACKUP_DATA_NAME = "ledgerhouse-data.json"
BACKUP_MANIFEST_NAME = "manifest.json"
BACKUP_EXCLUDES = ("contenttypes", "auth.Permission", "sessions")
# The production database blocks updates/deletes to audit events. A same-database
# rehearsal cannot replay those existing primary keys, but a clean-database restore
# can insert them. We therefore count successful deserialisation without saving.
IMMUTABLE_REHEARSAL_MODELS = {"accounting.auditevent"}


def create_local_backup(output_path: Path) -> dict:
    """Create a portable, checksummed data backup without contacting a provider."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = StringIO()
    arguments = [f"--exclude={label}" for label in BACKUP_EXCLUDES]
    call_command("dumpdata", *arguments, indent=2, stdout=serialized)
    data_text = serialized.getvalue()
    records = json.loads(data_text)
    data_bytes = data_text.encode("utf-8")
    manifest = {
        "format": "LedgerHouse local backup v1",
        "created_at": datetime.now(datetime_timezone.utc).isoformat(),
        "django_version": get_version(),
        "record_count": len(records),
        "sha256": hashlib.sha256(data_bytes).hexdigest(),
        "excluded_apps": list(BACKUP_EXCLUDES),
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(BACKUP_DATA_NAME, data_bytes)
        archive.writestr(BACKUP_MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))

    try:
        os.chmod(output_path, 0o600)
    except OSError:
        # Windows ACLs control local file permissions; the archive remains outside Git.
        pass
    return {"path": str(output_path), **manifest}


def verify_local_backup(archive_path: Path, restore_rehearsal: bool = False) -> dict:
    """Verify checksum/structure and optionally rehearse fixture restoration atomically."""
    archive_path = Path(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        if {BACKUP_DATA_NAME, BACKUP_MANIFEST_NAME} - names:
            raise ValueError("Backup archive is missing required LedgerHouse files.")
        data_bytes = archive.read(BACKUP_DATA_NAME)
        manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME).decode("utf-8"))

    actual_checksum = hashlib.sha256(data_bytes).hexdigest()
    if actual_checksum != manifest.get("sha256"):
        raise ValueError("Backup checksum does not match the manifest.")
    records = json.loads(data_bytes.decode("utf-8"))
    if not isinstance(records, list) or len(records) != manifest.get("record_count"):
        raise ValueError("Backup record count does not match the manifest.")

    restored_records = 0
    immutable_records_validated = 0
    if restore_rehearsal:
        # Django fixture deserialisation writes inside a nested transaction and is
        # deliberately rolled back, proving the snapshot can be restored without
        # changing the running local database.
        with transaction.atomic():
            for item in deserialize("json", data_bytes.decode("utf-8"), ignorenonexistent=False):
                if item.object._meta.label_lower in IMMUTABLE_REHEARSAL_MODELS:
                    immutable_records_validated += 1
                    continue
                item.save()
                restored_records += 1
            transaction.set_rollback(True)

    return {
        "path": str(archive_path),
        "record_count": len(records),
        "checksum_verified": True,
        "restore_rehearsal": restore_rehearsal,
        "restored_records": restored_records,
        "immutable_records_validated": immutable_records_validated,
    }
