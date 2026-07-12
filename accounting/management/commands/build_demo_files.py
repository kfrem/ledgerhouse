import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from accounting.models import Tenant


class Command(BaseCommand):
    help = "Builds realistic local demo upload files for each seeded client."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="local_demo_files",
            help="Directory to write generated demo files into.",
        )

    def handle(self, *args, **options):
        output_root = Path(options["output"])
        output_root.mkdir(parents=True, exist_ok=True)

        for tenant in Tenant.objects.order_by("name"):
            company_dir = output_root / tenant.name.lower().replace(" ", "-")
            company_dir.mkdir(parents=True, exist_ok=True)

            csv_path = company_dir / "bank-statement-july.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Date", "Amount", "Reference", "FITID"])
                writer.writerow(["2026-07-01", "-42.60", "Office stationery", f"{tenant.id}-CSV-001"])
                writer.writerow(["2026-07-02", "850.00", "Customer receipt", f"{tenant.id}-CSV-002"])
                writer.writerow(["2026-07-03", "-118.20", "Software subscription", f"{tenant.id}-CSV-003"])

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Bank statement"
            sheet.append(["Date", "Amount", "Reference", "FITID"])
            sheet.append(["2026-07-04", "-64.75", "Fuel and travel", f"{tenant.id}-XLSX-001"])
            sheet.append(["2026-07-05", "1250.00", "Invoice payment", f"{tenant.id}-XLSX-002"])
            workbook.save(company_dir / "bank-statement-july.xlsx")

            pdf_path = company_dir / "supplier-receipt.pdf"
            pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
            pdf.setTitle(f"{tenant.name} supplier receipt")
            pdf.drawString(72, 780, tenant.name)
            pdf.drawString(72, 750, "Supplier receipt")
            pdf.drawString(72, 720, "Amount: GBP 118.20")
            pdf.drawString(72, 700, "Description: Software subscription")
            pdf.save()

            (company_dir / "expense-note.txt").write_text(
                "Director expense note\nTaxi to client site: GBP 36.40\n",
                encoding="utf-8",
            )

            self.stdout.write(self.style.SUCCESS(f"Created demo upload pack for {tenant.name}"))

        self.stdout.write(self.style.SUCCESS(f"Demo files written to {output_root.resolve()}"))
