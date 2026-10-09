from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase

from accounting.models import AuditEvent, Tenant


class PracticeOperationsTimelineTests(TransactionTestCase):
    def setUp(self):
        self.client = Client()
        self.staff = get_user_model().objects.create_user(
            username="timeline-practice", password="pass", is_staff=True
        )
        self.client_user = get_user_model().objects.create_user(
            username="timeline-client", password="pass"
        )
        self.tenant = Tenant.objects.create(name="Timeline Client Ltd")
        self.other_tenant = Tenant.objects.create(name="Other Timeline Ltd")
        AuditEvent.objects.create(
            tenant=self.tenant, event_type="EvidencePosting", username="practice",
            description="Evidence posted to the ledger.", details={"document_id": 1},
        )
        AuditEvent.objects.create(
            tenant=self.tenant, event_type="BankFeedSync", username="practice",
            description="Bank feed synchronised.", details={},
        )
        AuditEvent.objects.create(
            tenant=self.other_tenant, event_type="PrivateEvent", username="other",
            description="This must never appear.", details={},
        )

    def test_staff_sees_only_selected_client_and_can_filter_by_event_type(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            "/practice/timeline/",
            {"company": self.tenant.id, "event_type": "EvidencePosting"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Evidence posted to the ledger.")
        self.assertNotContains(response, "Bank feed synchronised.")
        self.assertNotContains(response, "This must never appear.")

    def test_non_practice_user_is_not_given_the_timeline(self):
        self.client.force_login(self.client_user)
        response = self.client.get("/practice/timeline/", {"company": self.tenant.id})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
