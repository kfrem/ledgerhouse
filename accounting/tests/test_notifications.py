from django.test import TestCase

from accounting.models import AuditEvent, NotificationEvent, Tenant
from accounting.notifications import (
    MAX_NOTIFICATION_ATTEMPTS,
    mark_notification_sent,
    record_notification_preview,
    record_notification_failure,
)


class NotificationDeliveryTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Notification controls client")
        self.notification = NotificationEvent.objects.create(
            tenant=self.tenant,
            channel=NotificationEvent.CHANNEL_EMAIL_MOCK,
            recipient="client@example.test",
            subject="Approval required",
            body="Please review the accounts pack.",
        )

    def test_failure_is_retried_then_becomes_a_visible_terminal_failure(self):
        for attempt in range(1, MAX_NOTIFICATION_ATTEMPTS + 1):
            retry_scheduled = record_notification_failure(self.notification, "Provider unavailable", "practice")
            self.notification.refresh_from_db()
            self.assertEqual(self.notification.attempt_count, attempt)
            self.assertEqual(self.notification.last_error, "Provider unavailable")
            self.assertEqual(retry_scheduled, attempt < MAX_NOTIFICATION_ATTEMPTS)

        self.assertEqual(self.notification.status, NotificationEvent.STATUS_FAILED)
        self.assertIsNone(self.notification.next_attempt_at)
        self.assertEqual(AuditEvent.objects.filter(event_type="NotificationDeliveryFailed").count(), MAX_NOTIFICATION_ATTEMPTS)

    def test_delivery_is_idempotent_and_clears_retry_metadata(self):
        record_notification_failure(self.notification, "Temporary failure", "practice")
        self.assertTrue(mark_notification_sent(self.notification, "practice", "provider-123"))
        self.assertFalse(mark_notification_sent(self.notification, "practice", "provider-123"))
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, NotificationEvent.STATUS_SENT)
        self.assertEqual(self.notification.last_error, "")
        self.assertIsNone(self.notification.next_attempt_at)
        self.assertEqual(AuditEvent.objects.filter(event_type="NotificationDelivered").count(), 1)

    def test_sent_status_requires_provider_evidence(self):
        with self.assertRaisesRegex(ValueError, "Provider delivery evidence"):
            mark_notification_sent(self.notification, "practice", "")

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, NotificationEvent.STATUS_QUEUED)

    def test_preview_review_does_not_claim_delivery(self):
        self.assertTrue(record_notification_preview(self.notification, "practice"))
        self.assertFalse(record_notification_preview(self.notification, "practice"))

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, NotificationEvent.STATUS_QUEUED)
        self.assertEqual(
            AuditEvent.objects.filter(event_type="NotificationPreviewReviewed").count(),
            1,
        )
