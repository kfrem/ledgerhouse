from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from django.utils import timezone

from .companies_house import (
    build_companies_house_accounts_submission_xml,
    companies_house_next_local_build_items,
    companies_house_rejection_actions,
    companies_house_status,
    sanitise_companies_house_xml,
)
from .companies_house_scenarios import SCENARIO_SPECS, build_companies_house_local_scenarios
from .ixbrl import generate_micro_entity_ixbrl
from .models import (
    CompaniesHouseApprovalGate,
    CompaniesHouseFilingSubmission,
    CompaniesHouseSubmissionPoll,
    StatutoryAccountsDraft,
    Tenant,
)


def _scenario_csv(summary_rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "slug",
            "company_name",
            "company_number",
            "accounts_type",
            "ixbrl_passed",
            "readiness_passed",
            "gateway_xml_built",
            "messages",
        ],
    )
    writer.writeheader()
    for row in summary_rows:
        writer.writerow(
            {
                "slug": row.slug,
                "company_name": row.company_name,
                "company_number": row.company_number,
                "accounts_type": row.accounts_type,
                "ixbrl_passed": row.ixbrl_passed,
                "readiness_passed": row.readiness_passed,
                "gateway_xml_built": row.gateway_xml_built,
                "messages": " | ".join(row.messages),
            }
        )
    return buffer.getvalue()


def _submissions_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["submission_number", "company_number", "company_name", "status", "message_count", "created_at"])
    for submission in CompaniesHouseFilingSubmission.objects.order_by("-submission_number")[:100]:
        writer.writerow(
            [
                f"{submission.submission_number:06d}",
                submission.company_number,
                submission.company_name,
                submission.status,
                len(submission.validation_messages),
                submission.created_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def _polls_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["submission_number", "status", "message_count", "polled_by", "polled_at"])
    for poll in CompaniesHouseSubmissionPoll.objects.order_by("-polled_at")[:100]:
        writer.writerow(
            [
                f"{poll.submission_number:06d}",
                poll.status,
                len(poll.messages),
                poll.polled_by,
                poll.polled_at.isoformat(),
            ]
        )
    return buffer.getvalue()


def _approval_gates_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["tenant", "period_end", "accounts_type", "status", "practice_signed_off", "test_mode_only", "readiness_messages"])
    for gate in CompaniesHouseApprovalGate.objects.select_related("tenant", "statutory_accounts").order_by("-updated_at")[:100]:
        writer.writerow(
            [
                gate.tenant.name,
                gate.statutory_accounts.period_end.isoformat(),
                gate.statutory_accounts.accounts_type,
                gate.status,
                gate.practice_signed_off,
                gate.test_mode_only,
                " | ".join(gate.readiness_messages),
            ]
        )
    return buffer.getvalue()


def companies_house_evidence_markdown(results):
    status = companies_house_status()
    lines = [
        "# LedgerHouse Companies House Local Evidence Pack",
        "",
        f"Generated: {timezone.now().isoformat()}",
        "",
        "## Purpose",
        "",
        "This pack records the local Companies House accounts filing work completed for LedgerHouse before live production approval.",
        "",
        "## Current Boundary",
        "",
        f"- Public API configured: {status['configured']}",
        f"- XML Gateway test filing configured: {status['filing_enabled']}",
        f"- Registered filing product key: {status['filing_product_key']}",
        f"- Test gateway sending explicitly enabled: {status['test_send_enabled']}",
        f"- Production safety lock: {status['production_safety_lock']}",
        "- Raw presenter credentials and authentication values are not included in this pack.",
        "",
        "## Local Scenario Results",
        "",
    ]
    for result in results:
        lines.append(
            f"- {result.slug}: iXBRL={result.ixbrl_passed}, readiness={result.readiness_passed}, "
            f"gateway_xml={result.gateway_xml_built}, messages={'; '.join(result.messages) or 'none'}"
        )
    lines.extend(
        [
            "",
            "## Local Filing Controls Included In This Pack",
            "",
        ]
    )
    for item in companies_house_next_local_build_items():
        lines.append(f"- {item['item']}: {item['status']} - {item['evidence']}")
    lines.extend(
        [
            "",
            "## Remaining External Boundaries",
            "",
            "- These are local validation results only. Companies House must review and accept the required gateway test submissions before production filing is treated as approved.",
            "- The current taxonomy version is based on the supplied successful reference and must be confirmed by the Companies House validator/Gateway test before external acceptance is claimed.",
            "- Live filing must remain disabled until production credentials/settings are configured deliberately.",
            "- HMRC live filing and bank/payment provider flows remain separate external approvals.",
            "",
            "## Rejection Handling",
            "",
            "If Companies House rejects a submission, LedgerHouse maps gateway messages into local correction actions. Examples:",
        ]
    )
    examples = [
        "Submission number already used",
        "Company number is invalid",
        "iXBRL taxonomy validation failed",
    ]
    for example in examples:
        lines.append(f"- {example}: {' '.join(companies_house_rejection_actions([example]))}")
    return "\n".join(lines) + "\n"


def build_companies_house_evidence_pack(output_path, username="loop-engineering"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = build_companies_house_local_scenarios(username=username)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", companies_house_evidence_markdown(results))
        archive.writestr("scenario_matrix.csv", _scenario_csv(results))
        archive.writestr(
            "scenario_matrix.json",
            json.dumps([result.__dict__ for result in results], indent=2, default=str),
        )
        archive.writestr("submissions.csv", _submissions_csv())
        archive.writestr("poll_history.csv", _polls_csv())
        archive.writestr("approval_gates.csv", _approval_gates_csv())
        archive.writestr(
            "next_12_local_items.json",
            json.dumps(companies_house_next_local_build_items(), indent=2),
        )

        for index, spec in enumerate(SCENARIO_SPECS, start=1):
            tenant = Tenant.objects.get(name=spec.company_name)
            draft = StatutoryAccountsDraft.objects.filter(
                tenant=tenant,
                accounts_type=spec.accounts_type,
            ).order_by("-period_end").first()
            if not draft:
                continue
            ixbrl_text = generate_micro_entity_ixbrl(draft, spec.company_number, spec.company_name)
            archive.writestr(f"ixbrl/{spec.slug}.xhtml", ixbrl_text)
            try:
                gateway_xml = build_companies_house_accounts_submission_xml(
                    draft,
                    spec.company_number,
                    spec.company_name,
                    "TEST12",
                    index,
                )
                archive.writestr(f"gateway_xml/{spec.slug}.xml", sanitise_companies_house_xml(gateway_xml))
            except Exception as exc:
                archive.writestr(f"gateway_xml/{spec.slug}.blocked.txt", f"Gateway XML build blocked locally: {exc}")

    return output_path
