from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path

from django.utils import timezone

from .models import AuditEvent, Tenant
from .operations import accounts_department_snapshot, build_local_accounts_department_suite
from .reports import (
    accounts_department_pack_pdf,
    client_data_export_zip,
    management_report_csv,
    management_report_pack_pdf,
    management_report_pdf,
)


LOCAL_NO_HMRC_BUILD_ITEMS = [
    {
        "item": "Client operating data suite",
        "status": "Built locally",
        "evidence": "Sales, purchase, payroll, tax estimate, statutory, task and approval records are generated from local fixtures.",
    },
    {
        "item": "Practice work queue",
        "status": "Built locally",
        "evidence": "Accounting tasks are created across phases 1 to 8 and can be completed from the practice workspace.",
    },
    {
        "item": "Client approval workflow",
        "status": "Built locally",
        "evidence": "Management pack and statutory accounts approval records are created locally without HMRC.",
    },
    {
        "item": "Sales ledger controls",
        "status": "Built locally",
        "evidence": "Quotes, invoices, payment status and credit control actions are present for debtor workflow testing.",
    },
    {
        "item": "Purchase ledger controls",
        "status": "Built locally",
        "evidence": "Purchase orders, supplier bills and payment-run records are present for creditor workflow testing.",
    },
    {
        "item": "Month-end close controls",
        "status": "Built locally",
        "evidence": "Close files, period locks and fixed asset records are generated and reported.",
    },
    {
        "item": "Payroll and corporation tax summaries",
        "status": "Built locally",
        "evidence": "Local payroll summaries and corporation tax estimates are generated for reporting, not live filing.",
    },
    {
        "item": "Document intelligence rules",
        "status": "Built locally",
        "evidence": "Local document classification rules are seeded for invoice and evidence review workflows.",
    },
    {
        "item": "Management report exports",
        "status": "Built locally",
        "evidence": "CSV, PDF and PDF pack exports are generated from local client records.",
    },
    {
        "item": "Accounts department pack export",
        "status": "Built locally",
        "evidence": "A local accounts department PDF pack is generated for the selected client.",
    },
    {
        "item": "Client data export",
        "status": "Built locally",
        "evidence": "A ZIP export includes client accounting, approval, task and control data.",
    },
    {
        "item": "Developer takeover pack",
        "status": "Built locally",
        "evidence": "A Markdown report, readiness CSV and JSON build register are written for another developer.",
    },
]


@dataclass(frozen=True)
class LocalCompletionResult:
    tenant_name: str
    tenant_id: str
    passed_count: int
    total_count: int
    output_dir: Path
    files: list[str]

    @property
    def passed(self):
        return self.passed_count == self.total_count


def _safe_name(value):
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "client"


def _readiness_csv(rows):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["tenant", "phase", "label", "passed", "detail"])
    for tenant_name, snapshot in rows:
        for phase in snapshot["phases"]:
            writer.writerow([tenant_name, phase["phase"], phase["label"], phase["passed"], phase["detail"]])
    return buffer.getvalue()


def _takeover_markdown(rows, generated_files):
    now = timezone.now().isoformat()
    lines = [
        "# LedgerHouse Local No-HMRC Completion And Takeover Report",
        "",
        f"Generated: {now}",
        "",
        "## Purpose",
        "",
        "This report records what LedgerHouse can do locally without HMRC live approval. It is intended for a developer taking over the project, a technical reviewer, or a product owner checking what is already working.",
        "",
        "## Local Build Items",
        "",
    ]
    for item in LOCAL_NO_HMRC_BUILD_ITEMS:
        lines.append(f"- {item['item']}: {item['status']} - {item['evidence']}")
    lines.extend(["", "## Tenant Readiness", ""])
    for tenant_name, snapshot in rows:
        lines.append(f"### {tenant_name}")
        lines.append(f"- Local phase coverage: {snapshot['passed_count']} / {snapshot['total_count']}")
        lines.append(f"- Sales invoices: {snapshot['sales_count']} with {snapshot['open_sales_count']} open")
        lines.append(f"- Purchase bills: {snapshot['purchase_count']} with {snapshot['open_purchase_count']} open")
        lines.append(f"- Open work queue: {snapshot['open_task_count']} of {snapshot['task_count']} task(s)")
        for phase in snapshot["phases"]:
            state = "PASS" if phase["passed"] else "REVIEW"
            lines.append(f"- {state} {phase['phase']} - {phase['label']}: {phase['detail']}")
        lines.append("")
    lines.extend(
        [
            "## Generated Files",
            "",
        ]
    )
    for file_name in generated_files:
        lines.append(f"- `{file_name}`")
    lines.extend(
        [
            "",
            "## Still Externally Blocked",
            "",
            "- HMRC live submission routes and production OAuth approval.",
            "- Companies House live filing approval and production enablement.",
            "- Bank-feed, payment-provider, DNS/server deployment and legal review where those services are required.",
            "",
            "## Developer Notes",
            "",
            "- The local suite should be refreshed with `python manage.py build_no_hmrc_completion_pack` before handover.",
            "- Run focused workflow tests and then the full Django regression suite after local changes.",
            "- Do not commit local secret files, live credentials, downloaded bank files, or payment data.",
            "- Treat local reports as evidence of local readiness only; they are not proof of HMRC live filing approval.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_no_hmrc_completion_pack(output_dir, username="loop-engineering"):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tenants = list(Tenant.objects.order_by("name"))
    if not tenants:
        tenants = [Tenant.objects.create(name="LedgerHouse Local Demo Ltd")]

    rows = []
    generated_files = []
    for tenant in tenants:
        snapshot = build_local_accounts_department_suite(tenant, username=username)
        rows.append((tenant.name, snapshot))
        tenant_dir = output_dir / _safe_name(tenant.name)
        tenant_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "management_report.csv": management_report_csv(tenant),
            "management_report.pdf": management_report_pdf(tenant),
            "management_pack.pdf": management_report_pack_pdf(tenant),
            "accounts_department_pack.pdf": accounts_department_pack_pdf(tenant),
            "client_data_export.zip": client_data_export_zip(tenant),
        }
        for file_name, content in files.items():
            path = tenant_dir / file_name
            path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
            generated_files.append(str(path.relative_to(output_dir)))

        AuditEvent.objects.create(
            tenant=tenant,
            event_type="NoHmrcCompletionPack",
            username=username,
            description="Local no-HMRC completion pack generated.",
            details={
                "passed_count": snapshot["passed_count"],
                "total_count": snapshot["total_count"],
                "output_dir": str(output_dir),
            },
        )

    (output_dir / "tenant_readiness.csv").write_text(_readiness_csv(rows), encoding="utf-8")
    generated_files.append("tenant_readiness.csv")
    (output_dir / "local_no_hmrc_build_items.json").write_text(
        json.dumps(LOCAL_NO_HMRC_BUILD_ITEMS, indent=2),
        encoding="utf-8",
    )
    generated_files.append("local_no_hmrc_build_items.json")
    (output_dir / "README.md").write_text(_takeover_markdown(rows, generated_files), encoding="utf-8")
    generated_files.append("README.md")

    return [
        LocalCompletionResult(
            tenant_name=tenant_name,
            tenant_id=str(snapshot["tenant"].id),
            passed_count=snapshot["passed_count"],
            total_count=snapshot["total_count"],
            output_dir=output_dir,
            files=generated_files,
        )
        for tenant_name, snapshot in rows
    ]


def build_no_hmrc_completion_zip(output_dir, username="loop-engineering"):
    output_dir = Path(output_dir)
    results = build_no_hmrc_completion_pack(output_dir, username=username)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir))
    buffer.seek(0)
    return buffer.getvalue(), results
