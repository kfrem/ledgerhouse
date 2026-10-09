from io import BytesIO
import zipfile

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.test import TestCase

from accounting.intake import _validate_filename, process_uploaded_file
from accounting.models import EvidenceDocument, Tenant


def uploaded(name, content, content_type="application/pdf"):
    stream = BytesIO(content)
    return InMemoryUploadedFile(stream, "documents", name, content_type, len(content), None)


class IntakeHardeningTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Intake Controls Ltd")

    def test_invoice_has_explicit_confidence_and_review_requirement(self):
        result = process_uploaded_file(
            self.tenant,
            uploaded("sales-invoice.txt", b"Sales invoice GBP 120.00" , "text/plain"),
            "client",
        )

        self.assertEqual(result.category, "SalesInvoice")
        self.assertEqual(result.confidence, 90)
        self.assertTrue(result.requires_review)
        self.assertIn("90% confidence", EvidenceDocument.objects.get(id=result.document_id).review_note)

    def test_unsupported_extension_is_rejected_before_storage(self):
        with self.assertRaisesMessage(ValueError, "Unsupported file type"):
            process_uploaded_file(self.tenant, uploaded("payload.exe", b"content"), "client")

    def test_invalid_csv_encoding_has_actionable_failure(self):
        with self.assertRaisesMessage(ValueError, "UTF-8 text encoding"):
            process_uploaded_file(
                self.tenant,
                uploaded("bank.csv", b"\xff\xfe\x00", "text/csv"),
                "client",
            )

    def test_rejects_disguised_pdf_before_evidence_storage(self):
        with self.assertRaisesMessage(ValueError, "PDF file signature"):
            process_uploaded_file(
                self.tenant,
                uploaded("invoice.pdf", b"This is not a PDF", "application/pdf"),
                "client",
            )
        self.assertFalse(EvidenceDocument.objects.filter(tenant=self.tenant).exists())

    def test_rejects_disguised_image_before_evidence_storage(self):
        with self.assertRaisesMessage(ValueError, "PNG file signature"):
            process_uploaded_file(
                self.tenant,
                uploaded("receipt.png", b"not-an-image", "image/png"),
                "client",
            )
        self.assertFalse(EvidenceDocument.objects.filter(tenant=self.tenant).exists())

    def test_rejects_invalid_xlsx_archive_before_bank_import(self):
        with self.assertRaisesMessage(ValueError, "valid XLSX"):
            process_uploaded_file(
                self.tenant,
                uploaded(
                    "statement.xlsx",
                    b"not-a-zip",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "client",
            )

    def test_rejects_xlsx_archive_missing_workbook_parts(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
        with self.assertRaisesMessage(ValueError, "valid XLSX workbook"):
            process_uploaded_file(
                self.tenant,
                uploaded(
                    "statement.xlsx",
                    buffer.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "client",
            )

    def test_rejects_path_like_filename(self):
        with self.assertRaisesMessage(ValueError, "must not contain a folder path"):
            _validate_filename("folder/receipt.pdf")
