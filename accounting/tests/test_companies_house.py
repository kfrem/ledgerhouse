import base64
import io
import json
from pathlib import Path
import urllib.error
import xml.etree.ElementTree as ET
import zipfile
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.companies_house import (
    CompaniesHouseApiError,
    assess_companies_house_approval_gate,
    build_companies_house_accounts_submission_xml,
    build_get_submission_status_xml,
    companies_house_next_local_build_items,
    companies_house_initial_filing_scope,
    companies_house_rejection_actions,
    companies_house_status,
    normalise_company_number,
    next_companies_house_submission_number,
    parse_companies_house_gateway_status,
    poll_companies_house_submission_status,
    prepare_companies_house_test_submission,
    sanitise_companies_house_xml,
    retrieve_company_profile,
    submit_companies_house_test_submission,
    submit_companies_house_live_submission,
)
from accounting.companies_house_evidence import build_companies_house_evidence_pack
from accounting.companies_house_scenarios import (
    SCENARIO_SPECS,
    build_companies_house_local_scenarios,
)
from accounting.ixbrl import generate_micro_entity_ixbrl, validate_micro_entity_ixbrl
from accounting.models import (
    AuditEvent,
    CompaniesHouseApprovalGate,
    CompaniesHouseFilingSubmission,
    CompaniesHouseSubmissionPoll,
    NominalAccount,
    StatutoryAccountsDraft,
    Tenant,
)


class FakeCompaniesHouseResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeCompaniesHouseXmlResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload.encode("utf-8")


def company_profile_payload(company_number="00000006", company_name="LEDGERHOUSE TEST LIMITED"):
    return {
        "company_number": company_number,
        "company_name": company_name,
        "company_status": "active",
        "type": "ltd",
        "date_of_creation": "2024-04-06",
        "accounts": {"next_due": "2026-12-31", "overdue": False},
        "confirmation_statement": {"next_due": "2026-05-01", "overdue": False},
        "sic_codes": ["69201"],
        "registered_office_address": {
            "address_line_1": "1 Practice Street",
            "locality": "London",
            "postal_code": "EC1A 1AA",
            "country": "England",
        },
    }


@override_settings(
    COMPANIES_HOUSE_API_KEY="test-api-key",
    COMPANIES_HOUSE_API_BASE_URL="https://api.company-information.service.gov.uk",
    COMPANIES_HOUSE_FILING_CREDENTIALS_FILE="/tmp/ledgerhouse-missing-companies-house-filing.env",
    COMPANIES_HOUSE_FILING_PRESENTER_ID="",
    COMPANIES_HOUSE_FILING_AUTHENTICATION_VALUE="",
    COMPANIES_HOUSE_FILING_PACKAGE_REFERENCE="",
)
class CompaniesHouseIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )

    def test_status_reports_configured_without_exposing_key(self):
        status = companies_house_status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["api_key_present"])
        self.assertEqual(status["key_source"], "environment")
        self.assertNotIn("test-api-key", str(status))
        self.assertFalse(status["filing_enabled"])
        self.assertEqual(status["filing_status"], "Not enabled")
        self.assertIn("Accounts filing uses the Companies House XML Gateway test account", status["filing_detail"])
        self.assertEqual(status["accounts_tis_version"], "Companies House Accounts TIS supplement 5.9")

    def test_company_number_is_normalised_for_numeric_input(self):
        self.assertEqual(normalise_company_number("6"), "00000006")
        self.assertEqual(normalise_company_number(" 00000006 "), "00000006")
        self.assertEqual(normalise_company_number("SC123456"), "SC123456")

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_retrieve_company_profile_uses_basic_auth_api_key(self, urlopen):
        urlopen.return_value = FakeCompaniesHouseResponse(company_profile_payload())

        profile = retrieve_company_profile("6")

        self.assertEqual(profile["company_name"], "LEDGERHOUSE TEST LIMITED")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.company-information.service.gov.uk/company/00000006",
        )
        expected_token = base64.b64encode(b"test-api-key:").decode("ascii")
        self.assertEqual(request.headers["Authorization"], f"Basic {expected_token}")

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_retrieve_company_profile_preserves_api_errors(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.company-information.service.gov.uk/company/00000006",
            404,
            "Not Found",
            {},
            io.BytesIO(b'{"error":"company-profile-not-found"}'),
        )

        with self.assertRaises(CompaniesHouseApiError) as exc:
            retrieve_company_profile("6")

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(str(exc.exception), "company-profile-not-found")

    @patch("accounting.views.retrieve_company_profile")
    def test_companies_house_workspace_displays_company_profile(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.get(reverse("companies_house_workspace"), {"company_number": "6"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LEDGERHOUSE TEST LIMITED")
        self.assertContains(response, "00000006")
        self.assertContains(response, "2026-12-31")
        self.assertContains(response, "Accounts filing status")
        self.assertContains(response, "Blocked until XML Gateway test credentials are configured")
        self.assertContains(response, "Companies House Accounts TIS supplement 5.9")
        retrieve_profile.assert_called_once_with("6")

    @patch("accounting.views.retrieve_company_profile")
    def test_companies_house_workspace_creates_client_from_profile(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace"),
            {"company_number": "6", "action": "create_client"},
        )

        tenant = Tenant.objects.get(name="LEDGERHOUSE TEST LIMITED")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("practice_client_detail", args=[tenant.id]))
        self.assertEqual(NominalAccount.objects.filter(tenant=tenant).count(), 6)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=tenant,
                event_type="CompaniesHouseSync",
                details__company_number="00000006",
            ).exists()
        )


@override_settings(
    COMPANIES_HOUSE_API_KEY="test-api-key",
    COMPANIES_HOUSE_API_BASE_URL="https://api.company-information.service.gov.uk",
    COMPANIES_HOUSE_FILING_CREDENTIALS_FILE="/tmp/ledgerhouse-missing-companies-house-filing.env",
    COMPANIES_HOUSE_FILING_PRESENTER_ID="12345678901",
    COMPANIES_HOUSE_FILING_AUTHENTICATION_VALUE="secret-test-auth",
    COMPANIES_HOUSE_FILING_TEST_FLAG="1",
    COMPANIES_HOUSE_FILING_PACKAGE_REFERENCE="0012",
    COMPANIES_HOUSE_FILING_GATEWAY_URL="https://xmlgw.companieshouse.gov.uk/v1-0/xmlgw/Gateway",
    COMPANIES_HOUSE_FILING_SEND_ENABLED=True,
)
class CompaniesHouseFilingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="admin2",
            is_staff=True,
        )
        self.tenant = Tenant.objects.create(name="LEDGERHOUSE TEST LIMITED")
        self.draft = StatutoryAccountsDraft.objects.create(
            tenant=self.tenant,
            period_start="2025-01-01",
            period_end="2025-12-31",
            accounts_type="MicroEntity",
            directors_report_ready=True,
            balance_sheet_ready=True,
            notes_ready=True,
            client_approved=True,
            status=StatutoryAccountsDraft.STATUS_READY_FOR_FILING,
            ixbrl_ready=False,
            approval_date="2026-01-31",
            approving_director_name="LedgerHouse Test Director",
        )

    def test_filing_status_reports_configuration_without_secret(self):
        status = companies_house_status()

        self.assertTrue(status["filing_enabled"])
        self.assertEqual(status["filing_status"], "Test credentials ready")
        self.assertEqual(status["filing_test_flag"], "1")
        self.assertTrue(status["filing_package_reference_present"])
        self.assertEqual(status["production_safety_lock"], "Test mode only")
        self.assertTrue(status["test_mode_only"])
        self.assertTrue(status["test_send_enabled"])
        self.assertNotIn("secret-test-auth", str(status))
        self.assertNotIn("12345678901", str(status))

    def test_next_local_build_items_are_explicitly_recorded(self):
        items = companies_house_next_local_build_items()

        self.assertEqual(len(items), 12)
        self.assertTrue(all(item["status"] == "Built locally" for item in items))
        self.assertIn("Evidence ZIP export", {item["item"] for item in items})

    def test_build_submission_xml_uses_unique_number_and_masks_secret(self):
        xml_text = build_companies_house_accounts_submission_xml(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            1,
        )
        sanitised = sanitise_companies_house_xml(xml_text)

        self.assertIn("SubmissionNumber>000001</", xml_text)
        self.assertIn("PackageReference>0012</", xml_text)
        self.assertIn("FormSubmission-v2-11.xsd", xml_text)
        self.assertIn("<EnvelopeVersion>2.0</EnvelopeVersion>", xml_text)
        self.assertIn("<Function>submit</Function>", xml_text)
        self.assertIn("CompanyNumber>00000006</", xml_text)
        self.assertIn("<GatewayTest>1</GatewayTest>", xml_text)
        self.assertIn('Type="FormType">Accounts</', xml_text)
        self.assertIn("<Organisation>Companies House</Organisation>", xml_text)
        self.assertIn("CompanyType>EW</", xml_text)
        self.assertIn('xmlns="http://www.govtalk.gov.uk/CM/envelope"', xml_text)
        self.assertIn('<FormSubmission xmlns="http://xmlgw.companieshouse.gov.uk/Header"', xml_text)
        self.assertNotIn("ns2:FormSubmission", xml_text)
        self.assertIn("FormIdentifier>Accounts</", xml_text)
        self.assertIn("Category>ACCOUNTS</", xml_text)
        self.assertIn("<Value>REDACTED</Value>", sanitised)
        self.assertNotIn("12345678901", xml_text)
        self.assertNotIn("secret-test-auth", xml_text)
        self.assertNotIn("secret-test-auth", sanitised)

    def test_generated_ixbrl_is_well_formed_and_contains_required_accounts_facts(self):
        ixbrl_text = generate_micro_entity_ixbrl(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
        )
        validation = validate_micro_entity_ixbrl(ixbrl_text, self.draft, "00000006")

        self.assertTrue(validation.passed, validation.messages)
        self.assertTrue(ixbrl_text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertIn("ix:nonFraction", ixbrl_text)
        self.assertIn("uk-core:TurnoverRevenue", ixbrl_text)
        self.assertIn("uk-core:CostSales", ixbrl_text)
        self.assertIn("uk-core:NetAssetsLiabilities", ixbrl_text)
        self.assertIn("uk-bus:UKCompaniesHouseRegisteredNumber", ixbrl_text)

    def test_submission_wrapper_embeds_decodable_ixbrl_accounts_document(self):
        xml_text = build_companies_house_accounts_submission_xml(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            3,
        )
        root = ET.fromstring(xml_text.encode("utf-8"))
        ns = {
            "gt": "http://www.govtalk.gov.uk/schemas/govtalk/govtalkheader",
            "ch": "http://xmlgw.companieshouse.gov.uk/Header",
        }
        data = root.find(".//ch:Document/ch:Data", ns)
        self.assertIsNotNone(data)
        decoded_ixbrl = base64.b64decode(data.text).decode("utf-8")
        validation = validate_micro_entity_ixbrl(decoded_ixbrl, self.draft, "00000006")

        self.assertTrue(validation.passed, validation.messages)
        self.assertIn("LEDGERHOUSE TEST LIMITED", decoded_ixbrl)
        self.assertIn("Company number:", decoded_ixbrl)
        self.assertIn("uk-bus:UKCompaniesHouseRegisteredNumber", decoded_ixbrl)
        self.assertIn(">00000006</ix:nonNumeric>", decoded_ixbrl)

    def test_prepare_submission_allocates_incremental_number_and_blocks_until_ixbrl_ready(self):
        first = prepare_companies_house_test_submission(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            created_by="admin",
        )
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["ixbrl_ready"])
        second = prepare_companies_house_test_submission(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            created_by="admin",
        )

        self.assertEqual(first.submission_number, 1)
        self.assertEqual(second.submission_number, 2)
        self.assertIn("Valid XHTML/iXBRL accounts", " ".join(first.validation_messages))
        self.assertEqual(second.validation_messages, [])
        self.assertNotIn("secret-test-auth", first.request_xml_sanitised)
        self.assertEqual(CompaniesHouseFilingSubmission.objects.count(), 2)

    def test_submission_numbers_are_independent_and_incremental_per_product(self):
        self.assertEqual(next_companies_house_submission_number("ledgerhouse"), 1)
        self.assertEqual(next_companies_house_submission_number("ledgerhouse"), 2)
        self.assertEqual(next_companies_house_submission_number("sterling-suite"), 1)

    @override_settings(COMPANIES_HOUSE_FILING_SEND_ENABLED=False)
    def test_test_submission_send_is_locked_until_explicitly_enabled(self):
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["ixbrl_ready"])

        with self.assertRaisesMessage(CompaniesHouseApiError, "test sending is locked"):
            submit_companies_house_test_submission(
                self.draft,
                "00000006",
                "LEDGERHOUSE TEST LIMITED",
                "TEST12",
                created_by="admin",
            )

    @override_settings(
        COMPANIES_HOUSE_FILING_TEST_FLAG="0",
        COMPANIES_HOUSE_FILING_LIVE_ENABLED=False,
        COMPANIES_HOUSE_LIVE_APPROVAL_CONFIRMED=True,
    )
    def test_test_submission_refuses_live_credentials(self):
        with self.assertRaisesMessage(CompaniesHouseApiError, "credentials are for live filing"):
            submit_companies_house_test_submission(
                self.draft,
                "00000006",
                "LEDGERHOUSE TEST LIMITED",
                "TEST12",
                created_by="admin",
            )

    @override_settings(
        COMPANIES_HOUSE_FILING_TEST_FLAG="0",
        COMPANIES_HOUSE_FILING_SEND_ENABLED=False,
        COMPANIES_HOUSE_FILING_LIVE_ENABLED=False,
        COMPANIES_HOUSE_LIVE_APPROVAL_CONFIRMED=True,
    )
    def test_live_submission_requires_release_manager_enablement(self):
        with self.assertRaisesMessage(CompaniesHouseApiError, "release manager enables production filing"):
            submit_companies_house_live_submission(
                self.draft,
                "00000006",
                "LEDGERHOUSE TEST LIMITED",
                "TEST12",
                created_by="admin",
            )

    def test_status_polling_xml_uses_get_submission_status_class(self):
        xml_text = build_get_submission_status_xml(7)

        self.assertIn("<Class>GetSubmissionStatus</Class>", xml_text)
        self.assertIn("SubmissionNumber>000007</", xml_text)
        self.assertIn("<GatewayTest>1</GatewayTest>", xml_text)

    def test_gateway_status_parser_preserves_rejection_messages(self):
        status, messages = parse_companies_house_gateway_status(
            "<GovTalkMessage><GovTalkDetails><GovTalkErrors>"
            "<Error><Text>Submission number already used</Text></Error>"
            "</GovTalkErrors></GovTalkDetails></GovTalkMessage>"
        )

        self.assertEqual(status, "Rejected")
        self.assertIn("Submission number already used", messages)

    def test_rejection_messages_are_mapped_to_practical_actions(self):
        actions = companies_house_rejection_actions(
            [
                "Submission number already used",
                "iXBRL taxonomy validation failed",
                "Company number is invalid",
            ]
        )

        self.assertTrue(any("next unused incremental" in action for action in actions))
        self.assertTrue(any("Regenerate the XHTML/iXBRL" in action for action in actions))
        self.assertTrue(any("preserve leading zeros" in action for action in actions))

    def test_gateway_status_parser_treats_unprocessed_status_poll_as_pending(self):
        status, messages = parse_companies_house_gateway_status(
            "<GovTalkMessage><GovTalkDetails><GovTalkErrors>"
            "<Error><Text>No Accepted or Rejected Documents Found</Text></Error>"
            "</GovTalkErrors></GovTalkDetails></GovTalkMessage>"
        )

        self.assertEqual(status, "Pending")
        self.assertEqual(messages, [])

    def test_gateway_acknowledgement_is_pending_until_an_acceptance_is_polled(self):
        status, messages = parse_companies_house_gateway_status(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>acknowledgement</Qualifier>"
            "</MessageDetails></Header></GovTalkMessage>"
        )

        self.assertEqual(status, "Pending")
        self.assertEqual(messages, [])

    def test_gateway_status_parser_fails_closed_for_an_unrecognised_response(self):
        status, messages = parse_companies_house_gateway_status(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>response</Qualifier>"
            "</MessageDetails></Header></GovTalkMessage>"
        )

        self.assertEqual(status, "Failed")
        self.assertIn("unrecognised status", messages[0])

    @patch("accounting.companies_house._gateway_request")
    def test_poll_submission_status_updates_record_and_audit_trail(self, gateway_request):
        submission = CompaniesHouseFilingSubmission.objects.create(
            tenant=self.tenant,
            statutory_accounts=self.draft,
            submission_number=25,
            company_number="00000006",
            company_name="LEDGERHOUSE TEST LIMITED",
            package_reference="0012",
            gateway_test=1,
            status=CompaniesHouseFilingSubmission.STATUS_SUBMITTED,
            created_by="admin",
        )
        gateway_request.return_value = (
            200,
            "<GovTalkMessage><GovTalkDetails><GovTalkErrors>"
            "<Error><Text>No Accepted or Rejected Documents Found</Text></Error>"
            "</GovTalkErrors></GovTalkDetails></GovTalkMessage>",
        )

        updated = poll_companies_house_submission_status(submission, username="admin")

        self.assertEqual(updated.status, CompaniesHouseFilingSubmission.STATUS_PENDING)
        self.assertEqual(updated.validation_messages, [])
        self.assertIn("GovTalkMessage", updated.response_xml)
        poll = CompaniesHouseSubmissionPoll.objects.get()
        self.assertEqual(poll.submission_number, 25)
        self.assertEqual(poll.status, CompaniesHouseFilingSubmission.STATUS_PENDING)
        self.assertEqual(poll.messages, [])
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                event_type="CompaniesHouseStatusPolled",
                details__submission_number="000025",
            ).exists()
        )

    def test_local_scenario_builder_creates_valid_accounts_scenarios(self):
        results = build_companies_house_local_scenarios(username="admin")

        self.assertEqual(len(results), len(SCENARIO_SPECS))
        self.assertTrue(all(result.passed for result in results), [result.messages for result in results])
        self.assertEqual(StatutoryAccountsDraft.objects.filter(ixbrl_ready=True).count(), len(SCENARIO_SPECS))
        self.assertTrue(AuditEvent.objects.filter(event_type="CompaniesHouseScenarioBuilt").exists())
        dormant = StatutoryAccountsDraft.objects.filter(accounts_type="Dormant").order_by("-id").first()
        self.assertIsNotNone(dormant)
        ixbrl_text = generate_micro_entity_ixbrl(dormant, "00000006", dormant.tenant.name)
        self.assertIn("uk-bus:EntityDormantTruefalse", ixbrl_text)
        self.assertIn(">true</ix:nonNumeric>", ixbrl_text)

    def test_declared_initial_scope_includes_filleted_and_treats_amended_as_variant(self):
        scope = companies_house_initial_filing_scope()
        self.assertIn(
            {"accounts_type": "SmallUnauditedFilleted", "label": "Small unaudited filleted accounts"},
            scope,
        )
        self.assertEqual(len(scope), 4)
        self.assertNotIn(
            {"accounts_type": "AmendedMicroEntity", "label": "Amended micro-entity accounts"},
            scope,
        )

        self.draft.accounts_type = "AmendedMicroEntity"
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["accounts_type", "ixbrl_ready"])
        amended_xml = build_companies_house_accounts_submission_xml(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            1,
        )
        self.assertIn("<Class>Accounts</Class>", amended_xml)

        self.draft.accounts_type = "MediumAudited"
        self.draft.save(update_fields=["accounts_type"])
        with self.assertRaisesMessage(ValueError, "outside LedgerHouse's declared initial Companies House filing scope"):
            build_companies_house_accounts_submission_xml(
                self.draft,
                "00000006",
                "LEDGERHOUSE TEST LIMITED",
                "TEST12",
                1,
            )

    def test_approval_gate_records_client_approval_practice_signoff_and_test_lock(self):
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["ixbrl_ready"])

        gate = assess_companies_house_approval_gate(self.draft, username="admin", signoff=True)

        self.assertEqual(gate.status, CompaniesHouseApprovalGate.STATUS_SIGNED_OFF)
        self.assertTrue(gate.practice_signed_off)
        self.assertEqual(gate.practice_signed_off_by, "admin")
        self.assertTrue(gate.test_mode_only)
        self.assertEqual(gate.readiness_messages, [])

    def test_local_scenario_management_command_reports_success(self):
        output = StringIO()

        call_command("build_companies_house_scenarios", "--strict", stdout=output)

        self.assertIn("All 18 Companies House local scenarios passed.", output.getvalue())

    def test_second_round_plan_records_unsent_filleted_item_without_allocating_a_number(self):
        output_path = "/tmp/ledgerhouse-second-round-plan-test.md"
        call_command("build_companies_house_second_round_plan", "--output", output_path)
        plan = Path(output_path).read_text(encoding="utf-8")

        self.assertIn("Small unaudited filleted accounts", plan)
        self.assertIn("Initial test requires explicit XML Team-authorised sending", plan)
        self.assertEqual(CompaniesHouseFilingSubmission.objects.count(), 0)

    def test_xml_team_review_round_dry_run_builds_current_drafts_without_allocating_numbers(self):
        output_path = "/tmp/ledgerhouse-xml-team-round-dry-run.md"

        call_command("run_companies_house_xml_team_round", "--output", output_path)

        report = Path(output_path).read_text(encoding="utf-8")
        self.assertIn("small-unaudited-filleted", report)
        self.assertIn("Ready; dry run only", report)
        self.assertEqual(CompaniesHouseFilingSubmission.objects.count(), 0)

    @override_settings(COMPANIES_HOUSE_FILING_SEND_ENABLED=False)
    def test_xml_team_review_round_refuses_to_send_while_gateway_lock_is_enabled(self):
        with self.assertRaisesMessage(CommandError, "Gateway sending is locked"):
            call_command(
                "run_companies_house_xml_team_round",
                "--send",
                "--output",
                "/tmp/ledgerhouse-xml-team-round-send-lock.md",
            )

    def test_additional_examples_dry_run_prepares_three_examples_per_declared_type_without_numbers(self):
        output_path = "/tmp/ledgerhouse-additional-examples-dry-run.md"

        call_command("run_companies_house_additional_examples", "--output", output_path)

        report = Path(output_path).read_text(encoding="utf-8")
        self.assertEqual(report.count("| MicroEntity | Not allocated | Not sent | None | Ready; dry run only |"), 3)
        self.assertEqual(report.count("| SmallUnaudited | Not allocated | Not sent | None | Ready; dry run only |"), 3)
        self.assertEqual(report.count("| SmallUnauditedFilleted | Not allocated | Not sent | None | Ready; dry run only |"), 3)
        self.assertEqual(report.count("| Dormant | Not allocated | Not sent | None | Ready; dry run only |"), 3)
        self.assertEqual(CompaniesHouseFilingSubmission.objects.count(), 0)

    def test_evidence_pack_contains_scenarios_and_no_raw_filing_secret(self):
        output = "/tmp/ledgerhouse-companies-house-evidence-test.zip"

        path = build_companies_house_evidence_pack(output, username="admin")

        self.assertTrue(path.exists())
        data = path.read_bytes()
        self.assertIn(b"scenario_matrix.csv", data)
        self.assertIn(b"README.md", data)
        self.assertNotIn(b"secret-test-auth", data)
        self.assertNotIn(b"12345678901", data)
        with zipfile.ZipFile(path) as archive:
            readme = archive.read("README.md").decode("utf-8")
        self.assertIn("Test gateway sending explicitly enabled", readme)
        self.assertIn("Registered filing product key", readme)

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_submit_submission_posts_xml_gateway_request_and_stores_response(self, urlopen):
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["ixbrl_ready"])
        urlopen.return_value = FakeCompaniesHouseXmlResponse(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>acknowledgement</Qualifier>"
            "</MessageDetails></Header></GovTalkMessage>"
        )

        submission = submit_companies_house_test_submission(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            created_by="admin",
        )

        self.assertEqual(submission.submission_number, 1)
        self.assertEqual(submission.status, submission.STATUS_PENDING)
        self.assertIsNotNone(submission.submitted_at)
        self.assertIn("GovTalkMessage", submission.response_xml)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://xmlgw.companieshouse.gov.uk/v1-0/xmlgw/Gateway")
        self.assertIn(b"<Class>Accounts</Class>", request.data)
        self.assertIn(b"SubmissionNumber>000001</", request.data)
        self.assertNotIn(b"12345678901", request.data)
        self.assertNotIn(b"secret-test-auth", request.data)
        self.assertNotIn(b"secret-test-auth", submission.request_xml_sanitised.encode("utf-8"))

    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_submit_submission_does_not_call_gateway_when_readiness_fails(self, urlopen):
        submission = submit_companies_house_test_submission(
            self.draft,
            "00000006",
            "LEDGERHOUSE TEST LIMITED",
            "TEST12",
            created_by="admin",
        )

        self.assertEqual(submission.status, submission.STATUS_FAILED)
        self.assertIn("Valid XHTML/iXBRL accounts", " ".join(submission.validation_messages))
        urlopen.assert_not_called()

    @patch("accounting.views.retrieve_company_profile")
    def test_workspace_can_prepare_test_submission_from_company_profile(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace") + "?company_number=6",
            {
                "action": "prepare_test_submission",
                "company_number": "6",
                "statutory_accounts_id": str(self.draft.id),
                "company_authentication_code": "TEST12",
            },
        )

        self.assertEqual(response.status_code, 302)
        submission = CompaniesHouseFilingSubmission.objects.get()
        self.assertEqual(submission.submission_number, 1)
        self.assertEqual(submission.company_number, "00000006")
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                event_type="CompaniesHouseTestSubmissionPrepared",
                details__submission_number="000001",
            ).exists()
        )

    @patch("accounting.views.retrieve_company_profile")
    def test_workspace_generates_and_validates_ixbrl_before_preparation(self, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace") + "?company_number=6",
            {
                "action": "validate_ixbrl",
                "company_number": "6",
                "statutory_accounts_id": str(self.draft.id),
                "company_authentication_code": "TEST12",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.ixbrl_ready)
        self.assertEqual(self.draft.status, StatutoryAccountsDraft.STATUS_READY_FOR_FILING)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                event_type="CompaniesHouseIxbrlValidated",
                details__company_number="00000006",
            ).exists()
        )

    @patch("accounting.views.retrieve_company_profile")
    @patch("accounting.companies_house.urllib.request.urlopen")
    def test_workspace_can_send_test_submission_from_company_profile(self, urlopen, retrieve_profile):
        retrieve_profile.return_value = company_profile_payload()
        urlopen.return_value = FakeCompaniesHouseXmlResponse(
            "<GovTalkMessage><Header><MessageDetails><Qualifier>acknowledgement</Qualifier>"
            "</MessageDetails></Header></GovTalkMessage>"
        )
        self.draft.ixbrl_ready = True
        self.draft.save(update_fields=["ixbrl_ready"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace") + "?company_number=6",
            {
                "action": "send_test_submission",
                "company_number": "6",
                "statutory_accounts_id": str(self.draft.id),
                "company_authentication_code": "TEST12",
            },
        )

        self.assertEqual(response.status_code, 302)
        submission = CompaniesHouseFilingSubmission.objects.get()
        self.assertEqual(submission.status, submission.STATUS_PENDING)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                event_type="CompaniesHouseTestSubmissionSent",
                details__submission_number="000001",
            ).exists()
        )

    def test_workspace_can_build_local_scenarios_without_profile_lookup(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace"),
            {"action": "build_local_scenarios"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Tenant.objects.filter(name__startswith="LH TEST").count(), len(SCENARIO_SPECS))

    def test_staff_can_preview_report_style_accounts_before_gateway_send(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("companies_house_accounts_preview", args=[self.draft.id]),
            {"company_number": "6"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xhtml+xml; charset=utf-8")
        self.assertContains(response, 'class="financial-statement"')
        self.assertContains(response, "Balance Sheet")
        self.assertContains(response, "Company number:")

    @patch("accounting.views.poll_companies_house_submission_status")
    def test_workspace_can_poll_existing_submission_without_resubmitting(self, poll_status):
        submission = CompaniesHouseFilingSubmission.objects.create(
            tenant=self.tenant,
            statutory_accounts=self.draft,
            submission_number=25,
            company_number="00000006",
            company_name="LEDGERHOUSE TEST LIMITED",
            package_reference="0012",
            gateway_test=1,
            status=CompaniesHouseFilingSubmission.STATUS_SUBMITTED,
            created_by="admin",
        )
        submission.status = CompaniesHouseFilingSubmission.STATUS_PENDING
        poll_status.return_value = submission
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("companies_house_workspace"),
            {"action": "poll_submission", "submission_id": str(submission.id)},
        )

        self.assertEqual(response.status_code, 302)
        poll_status.assert_called_once()

    def test_workspace_displays_local_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("companies_house_workspace"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Production safety lock")
        self.assertContains(response, "Twelve Companies House items completed without external approval")
        self.assertContains(response, "Client approval and practice signoff gates")
