from dataclasses import dataclass

from .bank_import import import_bank_csv, import_bank_xlsx
from .models import EvidenceDocument


@dataclass(frozen=True)
class IntakeResult:
    kind: str
    message: str
    imported_count: int = 0
    skipped_count: int = 0
    document_id: int | None = None


def process_uploaded_file(tenant, uploaded_file, uploaded_by):
    """Process one client upload into the correct local intake path."""
    filename = uploaded_file.name
    content_type = getattr(uploaded_file, "content_type", "") or "application/octet-stream"
    payload = uploaded_file.read()
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix == "csv" or content_type in {"text/csv", "application/csv"}:
        text = payload.decode("utf-8-sig")
        imported, skipped = import_bank_csv(tenant, filename, text)
        return IntakeResult(
            kind="bank_csv",
            message=f"Imported {imported} bank lines from CSV.",
            imported_count=imported,
            skipped_count=skipped,
        )

    if suffix == "xlsx":
        imported, skipped = import_bank_xlsx(tenant, filename, payload)
        return IntakeResult(
            kind="bank_xlsx",
            message=f"Imported {imported} bank lines from spreadsheet.",
            imported_count=imported,
            skipped_count=skipped,
        )

    document = EvidenceDocument.objects.create(
        tenant=tenant,
        filename=filename,
        file_content=payload,
        content_type=content_type,
        uploaded_by=uploaded_by,
    )
    return IntakeResult(
        kind="evidence",
        message="Uploaded document into the evidence vault.",
        document_id=document.id,
    )
