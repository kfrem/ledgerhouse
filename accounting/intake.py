from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import PurePath
import re
import zipfile

from .bank_import import import_bank_csv, import_bank_xlsx
from .models import EvidenceDocument


@dataclass(frozen=True)
class IntakeResult:
    kind: str
    message: str
    imported_count: int = 0
    skipped_count: int = 0
    document_id: int | None = None
    category: str = "Uncategorised"
    confidence: int = 0
    requires_review: bool = True


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_DOCUMENT_SUFFIXES = {"pdf", "txt", "csv", "xlsx", "jpg", "jpeg", "png", "webp", "heic"}
MAX_XLSX_ARCHIVE_MEMBERS = 2_000
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


def _validate_filename(filename: str) -> str:
    """Reject unsafe names before they become evidence or import records."""
    if not filename or len(filename) > 255:
        raise ValueError("Upload filename must be between 1 and 255 characters.")
    if PurePath(filename).name != filename or "\\" in filename or "/" in filename:
        raise ValueError("Upload filename must not contain a folder path.")
    if any(ord(character) < 32 for character in filename):
        raise ValueError("Upload filename contains unsupported control characters.")
    return filename


def _validate_xlsx_archive(payload: bytes) -> None:
    """Reject malformed or disproportionate spreadsheet archives before parsing."""
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > MAX_XLSX_ARCHIVE_MEMBERS:
                raise ValueError("Spreadsheet contains too many files to process safely.")
            if sum(member.file_size for member in members) > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise ValueError("Spreadsheet expands beyond the safe processing limit.")
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError("Spreadsheet is not a valid XLSX file.") from exc

    required_parts = {"[Content_Types].xml", "xl/workbook.xml"}
    if not required_parts.issubset(names):
        raise ValueError("Spreadsheet is not a valid XLSX workbook.")


def _validate_upload_content(suffix: str, payload: bytes) -> None:
    """Use file signatures and bounded parsers; browser content types are advisory."""
    if suffix == "pdf" and not payload.startswith(b"%PDF-"):
        raise ValueError("PDF upload does not contain a valid PDF file signature.")
    if suffix in {"jpg", "jpeg"} and not payload.startswith(b"\xff\xd8\xff"):
        raise ValueError("Image upload does not contain a valid JPEG file signature.")
    if suffix == "png" and not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Image upload does not contain a valid PNG file signature.")
    if suffix == "webp" and not (payload.startswith(b"RIFF") and payload[8:12] == b"WEBP"):
        raise ValueError("Image upload does not contain a valid WEBP file signature.")
    if suffix == "heic" and not (len(payload) >= 12 and payload[4:8] == b"ftyp"):
        raise ValueError("Image upload does not contain a valid HEIC file signature.")
    if suffix in {"txt", "csv"}:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text and CSV files must use UTF-8 text encoding.") from exc
        if "\x00" in text:
            raise ValueError("Text and CSV files must not contain binary data.")
    if suffix == "xlsx":
        _validate_xlsx_archive(payload)


def classify_evidence_upload(filename, content_type="", payload=b""):
    haystack = f"{filename} {content_type}".lower()
    decoded_payload = payload[:4096].decode("utf-8", errors="ignore")
    haystack = f"{haystack} {decoded_payload.lower()}"

    rules = [
        ("SalesInvoice", ["sales invoice", "customer invoice", "invoice to:", "invoice to ", "inv-out", "sales-"]),
        ("PurchaseInvoice", ["purchase invoice", "supplier invoice", "bill", "invoice", "supplier"]),
        ("Receipt", ["receipt", "expense", "till", "fuel", "parking"]),
        ("BankStatement", ["bank statement", "statement", "transactions"]),
        ("Payroll", ["payroll", "paye", "wages", "salary", "cis"]),
        ("Contract", ["contract", "agreement", "engagement"]),
        ("Tax", ["tax", "corporation tax", "vat", "hmrc", "ct600"]),
    ]
    for category, keywords in rules:
        if any(keyword in haystack for keyword in keywords):
            return category
    if content_type.startswith("image/"):
        return "Receipt"
    return "Other"


def _extract_amount(payload):
    text = payload[:4096].decode("utf-8", errors="ignore")
    matches = re.findall(r"(?:GBP|£)?\s*([0-9][0-9,]*\.[0-9]{2})", text)
    if not matches:
        return None
    try:
        return Decimal(matches[-1].replace(",", ""))
    except InvalidOperation:
        return None


def process_uploaded_file(tenant, uploaded_file, uploaded_by):
    """Process one client upload into the correct local intake path."""
    filename = _validate_filename(uploaded_file.name)
    content_type = getattr(uploaded_file, "content_type", "") or "application/octet-stream"
    payload = uploaded_file.read()
    if not payload:
        raise ValueError("Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file exceeds the 25 MB local upload limit.")
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ValueError("Unsupported file type. Upload a PDF, image, text, CSV or XLSX file.")
    _validate_upload_content(suffix, payload)

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

    category = classify_evidence_upload(filename, content_type, payload)
    gross_amount = _extract_amount(payload)
    suggested_account = ""
    if category == "PurchaseInvoice":
        suggested_account = "6000"
    elif category == "SalesInvoice":
        suggested_account = "4000"
    elif category == "Payroll":
        suggested_account = "7000"
    elif category == "Tax":
        suggested_account = "8200"
    elif category == "Receipt":
        suggested_account = "6000"

    confidence = 90 if gross_amount is not None and category != "Other" else 70 if category != "Other" else 35
    document = EvidenceDocument.objects.create(
        tenant=tenant,
        filename=filename,
        file_content=payload,
        content_type=content_type,
        uploaded_by=uploaded_by,
        document_category=category,
        gross_amount=gross_amount,
        suggested_account_code=suggested_account,
        review_note=(
            f"Local intake classified this upload as {category} with {confidence}% confidence. "
            "This is a suggested classification only; Practice review is still required before posting."
        ),
    )
    return IntakeResult(
        kind="evidence",
        message=f"Uploaded document into the evidence vault and classified it as {category}.",
        document_id=document.id,
        category=category,
        confidence=confidence,
        requires_review=True,
    )
