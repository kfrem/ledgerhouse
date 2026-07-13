import csv
import io
import zipfile
from decimal import Decimal

from django.db.models import Q, Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    BankReconciliation,
    BankTransaction,
    ClientRequest,
    EvidenceDocument,
    ImportedFile,
    Journal,
    JournalLine,
    NominalAccount,
    VatReturn,
)


def _sum_lines(tenant, categories, side):
    aggregate = JournalLine.objects.filter(
        tenant=tenant,
        account__category__in=categories,
    ).aggregate(total=Sum(side))
    return aggregate["total"] or Decimal("0")


def management_report_context(tenant):
    revenue = _sum_lines(tenant, ["Revenue"], "credit")
    expenses = _sum_lines(tenant, ["Expense", "Cost of Sales"], "debit")
    reconciled_ids = BankReconciliation.objects.filter(tenant=tenant).values("bank_transaction_id")
    bank_count = BankTransaction.objects.filter(tenant=tenant).count()
    unreconciled_count = (
        BankTransaction.objects.filter(tenant=tenant)
        .exclude(id__in=reconciled_ids)
        .count()
    )
    vat_due = VatReturn.objects.filter(tenant=tenant).aggregate(
        total=Sum("net_vat_payable")
    )["total"] or Decimal("0")

    return {
        "tenant": tenant,
        "revenue": revenue,
        "expenses": expenses,
        "profit": revenue - expenses,
        "vat_due": vat_due,
        "bank_count": bank_count,
        "unreconciled_count": unreconciled_count,
        "journal_count": Journal.objects.filter(tenant=tenant).count(),
        "evidence_count": EvidenceDocument.objects.filter(tenant=tenant).count(),
    }


def management_report_csv(tenant):
    report = management_report_context(tenant)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Company", tenant.name])
    writer.writerow(["Revenue", report["revenue"]])
    writer.writerow(["Expenses", report["expenses"]])
    writer.writerow(["Profit", report["profit"]])
    writer.writerow(["VAT due", report["vat_due"]])
    writer.writerow(["Bank lines", report["bank_count"]])
    writer.writerow(["Unmatched bank lines", report["unreconciled_count"]])
    writer.writerow(["Bookkeeping entries", report["journal_count"]])
    writer.writerow(["Evidence documents", report["evidence_count"]])
    return output.getvalue()


def management_report_pdf(tenant):
    report = management_report_context(tenant)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"{tenant.name} management report")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("LedgerHouse Management Report", styles["Title"]),
        Paragraph(tenant.name, styles["Heading2"]),
        Spacer(1, 16),
    ]
    rows = [
        ["Metric", "Value"],
        ["Revenue", f"GBP {report['revenue']:,.2f}"],
        ["Expenses", f"GBP {report['expenses']:,.2f}"],
        ["Profit", f"GBP {report['profit']:,.2f}"],
        ["VAT due", f"GBP {report['vat_due']:,.2f}"],
        ["Bank lines", str(report["bank_count"])],
        ["Unmatched bank lines", str(report["unreconciled_count"])],
        ["Bookkeeping entries", str(report["journal_count"])],
        ["Evidence documents", str(report["evidence_count"])],
    ]
    table = Table(rows, hAlign="LEFT", colWidths=[180, 260])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b7a65")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dce6e4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _csv_bytes(headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def client_data_export_zip(tenant):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as export:
        export.writestr(
            "README.txt",
            (
                "LedgerHouse client data export\n"
                f"Company: {tenant.name}\n"
                "This package contains accounting records, source file indexes, "
                "client questions, VAT records and uploaded evidence files for "
                "provider switching or client archive purposes.\n"
            ),
        )
        export.writestr(
            "nominal_accounts.csv",
            _csv_bytes(
                ["id", "code", "name", "category", "canonical_taxonomy"],
                NominalAccount.objects.filter(tenant=tenant)
                .order_by("code")
                .values_list("id", "code", "name", "category", "canonical_taxonomy"),
            ),
        )
        export.writestr(
            "journals.csv",
            _csv_bytes(
                ["id", "date", "source_type", "source_id", "status", "description", "created_by"],
                Journal.objects.filter(tenant=tenant)
                .order_by("date", "id")
                .values_list("id", "date", "source_type", "source_id", "status", "description", "created_by"),
            ),
        )
        export.writestr(
            "journal_lines.csv",
            _csv_bytes(
                [
                    "id",
                    "journal_id",
                    "account_code",
                    "account_name",
                    "debit",
                    "credit",
                    "vat_code",
                    "vat_rate",
                    "vat_amount",
                    "department",
                ],
                JournalLine.objects.filter(tenant=tenant)
                .select_related("account")
                .order_by("journal_id", "id")
                .values_list(
                    "id",
                    "journal_id",
                    "account__code",
                    "account__name",
                    "debit",
                    "credit",
                    "vat_code",
                    "vat_rate",
                    "vat_amount",
                    "department",
                ),
            ),
        )
        export.writestr(
            "imported_files.csv",
            _csv_bytes(
                ["id", "filename", "uploaded_at", "file_hash"],
                ImportedFile.objects.filter(tenant=tenant)
                .order_by("uploaded_at", "id")
                .values_list("id", "filename", "uploaded_at", "file_hash"),
            ),
        )
        export.writestr(
            "bank_transactions.csv",
            _csv_bytes(
                ["id", "imported_file_id", "date", "amount", "reference", "fitid", "review_status", "reviewed_by"],
                BankTransaction.objects.filter(tenant=tenant)
                .order_by("date", "id")
                .values_list("id", "imported_file_id", "date", "amount", "reference", "fitid", "review_status", "reviewed_by"),
            ),
        )
        export.writestr(
            "vat_returns.csv",
            _csv_bytes(
                [
                    "id",
                    "start_date",
                    "end_date",
                    "period_key",
                    "status",
                    "total_output_vat",
                    "total_input_vat",
                    "net_vat_payable",
                    "hmrc_receipt_id",
                ],
                VatReturn.objects.filter(tenant=tenant)
                .order_by("start_date", "id")
                .values_list(
                    "id",
                    "start_date",
                    "end_date",
                    "period_key",
                    "status",
                    "total_output_vat",
                    "total_input_vat",
                    "net_vat_payable",
                    "hmrc_receipt_id",
                ),
            ),
        )
        export.writestr(
            "client_requests.csv",
            _csv_bytes(
                ["id", "subject", "category", "priority", "status", "submitted_by", "submitted_at", "resolved_by"],
                ClientRequest.objects.filter(tenant=tenant)
                .order_by("submitted_at", "id")
                .values_list("id", "subject", "category", "priority", "status", "submitted_by", "submitted_at", "resolved_by"),
            ),
        )
        evidence_rows = []
        for document in EvidenceDocument.objects.filter(tenant=tenant).order_by("uploaded_at", "id"):
            evidence_path = f"evidence/{document.id}-{document.filename}"
            evidence_rows.append(
                [
                    document.id,
                    document.filename,
                    evidence_path,
                    document.content_type,
                    document.uploaded_at,
                    document.uploaded_by,
                    document.review_status,
                    document.reviewed_by,
                ]
            )
            export.writestr(evidence_path, bytes(document.file_content))
        export.writestr(
            "evidence_documents.csv",
            _csv_bytes(
                [
                    "id",
                    "filename",
                    "export_path",
                    "content_type",
                    "uploaded_at",
                    "uploaded_by",
                    "review_status",
                    "reviewed_by",
                ],
                evidence_rows,
            ),
        )
    return buffer.getvalue()
