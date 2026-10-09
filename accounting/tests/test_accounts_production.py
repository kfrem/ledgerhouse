from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import (
    AccountingTask,
    AuditEvent,
    ClientApprovalRecord,
    CompaniesHouseFilingSubmission,
    ManagementPackSection,
    StatutoryAccountsDraft,
    Tenant,
)
from accounting.production import accounts_production_snapshot


class AccountsProductionWorkspaceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Production Client Ltd")
        self.other_tenant = Tenant.objects.create(name="Private Production Ltd")
        self.staff = get_user_model().objects.create_user(
            username="production-practice", password="pass", is_staff=True
        )
        self.client_user = get_user_model().objects.create_user(
            username="production-client", password="pass"
        )
        self.draft = StatutoryAccountsDraft.objects.create(
            tenant=self.tenant,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            accounts_type="SmallUnaudited",
            status=StatutoryAccountsDraft.STATUS_CLIENT_APPROVAL,
        )
        ClientApprovalRecord.objects.create(
            tenant=self.tenant,
            approval_type=ClientApprovalRecord.TYPE_STATUTORY_ACCOUNTS,
            reference="STAT-2025-12-31",
            title="Statutory accounts",
            status=ClientApprovalRecord.STATUS_PENDING,
        )
        ClientApprovalRecord.objects.create(
            tenant=self.tenant,
            approval_type=ClientApprovalRecord.TYPE_MANAGEMENT_PACK,
            reference="PACK-2025-12-31",
            title="Management pack",
            status=ClientApprovalRecord.STATUS_APPROVED,
        )
        ManagementPackSection.objects.create(
            tenant=self.tenant,
            section_name="Director commentary",
            period_end=date(2025, 12, 31),
            commentary="Reviewed commentary.",
            status=ManagementPackSection.STATUS_REVIEWED,
        )
        CompaniesHouseFilingSubmission.objects.create(
            tenant=self.tenant,
            statutory_accounts=self.draft,
            product_key="production-test",
            submission_number=1,
            company_number="12345678",
            company_name=self.tenant.name,
            package_reference="0012",
            status=CompaniesHouseFilingSubmission.STATUS_PENDING,
        )
        AccountingTask.objects.create(
            tenant=self.tenant,
            phase="Statutory",
            title="Partner review",
            owner="Partner A",
            status=AccountingTask.STATUS_IN_PROGRESS,
            due_date=date(2026, 1, 15),
        )
        AuditEvent.objects.create(
            tenant=self.tenant,
            event_type="AccountsReview",
            username="practice",
            description="Accounts review completed.",
        )
        AuditEvent.objects.create(
            tenant=self.other_tenant,
            event_type="Private",
            username="other",
            description="This must not appear.",
        )

    def test_snapshot_uses_real_client_records_and_keeps_release_history(self):
        snapshot = accounts_production_snapshot(self.tenant)

        self.assertEqual(snapshot["company"]["company_number"], "12345678")
        self.assertEqual(len(snapshot["annual_register"]), 1)
        self.assertEqual(snapshot["annual_register"][0]["delivery_status"], "Pending")
        self.assertEqual(snapshot["annual_register"][0]["approval"].status, "Pending")
        self.assertEqual(len(snapshot["management_register"]), 1)
        self.assertEqual(snapshot["management_register"][0]["reference"], "PACK-2025-12-31")
        self.assertEqual(len(snapshot["release_ready"]), 1)
        self.assertEqual(snapshot["open_tasks"][0].owner, "Partner A")
        self.assertEqual(list(snapshot["latest_events"])[0].description, "Accounts review completed.")

    def test_practice_screen_renders_registers_and_is_tenant_scoped(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("practice_accounts_production"), {"company": self.tenant.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Controlled filing register")
        self.assertContains(response, "12345678")
        self.assertContains(response, "Partner review")
        self.assertContains(response, "Accounts review completed.")
        self.assertNotContains(response, "This must not appear.")

    def test_client_cannot_open_practice_production_workspace(self):
        self.client.force_login(self.client_user)
        response = self.client.get(
            reverse("practice_accounts_production"), {"company": self.tenant.id}
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_practice_can_transition_work_and_release_approved_management_pack(self):
        approval = ClientApprovalRecord.objects.get(
            tenant=self.tenant, approval_type=ClientApprovalRecord.TYPE_MANAGEMENT_PACK
        )
        task = AccountingTask.objects.get(tenant=self.tenant, title="Partner review")
        self.client.force_login(self.staff)

        start = self.client.post(reverse("practice_accounts_production"), {
            "company": str(self.tenant.id), "action": "start_task", "task_id": task.id,
        })
        complete = self.client.post(reverse("practice_accounts_production"), {
            "company": str(self.tenant.id), "action": "complete_task", "task_id": task.id,
        })
        released = self.client.post(reverse("practice_accounts_production"), {
            "company": str(self.tenant.id), "action": "release_approval_pack", "approval_id": approval.id,
        })

        task.refresh_from_db()
        self.assertEqual(start.status_code, 302)
        self.assertEqual(complete.status_code, 302)
        self.assertEqual(released.status_code, 302)
        self.assertEqual(task.status, AccountingTask.STATUS_DONE)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, event_type="ApprovalPackReleased").exists())
