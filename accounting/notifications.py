"""Provider-neutral notification delivery controls.

The local application records delivery attempts but deliberately does not claim
to send external email until a provider is configured.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, NotificationEvent


MAX_NOTIFICATION_ATTEMPTS = 3


@transaction.atomic
def mark_notification_sent(
    notification: NotificationEvent,
    username: str,
    provider_reference: str,
) -> bool:
    """Record delivery only after an external provider supplies evidence."""
    provider_reference = (provider_reference or "").strip()
    if not provider_reference:
        raise ValueError("Provider delivery evidence is required before marking a notification sent.")
    if notification.status == NotificationEvent.STATUS_SENT:
        return False
    notification.status = NotificationEvent.STATUS_SENT
    notification.sent_at = timezone.now()
    notification.last_error = ""
    notification.next_attempt_at = None
    notification.save(update_fields=["status", "sent_at", "last_error", "next_attempt_at"])
    AuditEvent.objects.create(
        tenant=notification.tenant,
        event_type="NotificationDelivered",
        username=username,
        description=f"Notification '{notification.subject}' recorded as delivered.",
        details={
            "notification_id": notification.id,
            "channel": notification.channel,
            "provider_reference": provider_reference,
        },
    )
    return True


@transaction.atomic
def record_notification_preview(notification: NotificationEvent, username: str) -> bool:
    """Record local content review without claiming external delivery."""
    prior = AuditEvent.objects.filter(
        tenant=notification.tenant,
        event_type="NotificationPreviewReviewed",
        details__notification_id=notification.id,
    ).exists()
    if prior:
        return False
    AuditEvent.objects.create(
        tenant=notification.tenant,
        event_type="NotificationPreviewReviewed",
        username=username,
        description=f"Notification '{notification.subject}' preview reviewed locally.",
        details={
            "notification_id": notification.id,
            "channel": notification.channel,
            "delivery_status": notification.status,
        },
    )
    return True


@transaction.atomic
def record_notification_failure(notification: NotificationEvent, error: str, username: str) -> bool:
    """Persist a bounded retry plan without silently discarding a failed message."""
    if notification.status == NotificationEvent.STATUS_SENT:
        raise ValueError("A delivered notification cannot be marked as failed.")
    notification.attempt_count += 1
    notification.last_error = error[:1000]
    if notification.attempt_count >= MAX_NOTIFICATION_ATTEMPTS:
        notification.status = NotificationEvent.STATUS_FAILED
        notification.next_attempt_at = None
    else:
        notification.status = NotificationEvent.STATUS_RETRY_SCHEDULED
        notification.next_attempt_at = timezone.now() + timedelta(minutes=5 * notification.attempt_count)
    notification.save(update_fields=["attempt_count", "last_error", "status", "next_attempt_at"])
    AuditEvent.objects.create(
        tenant=notification.tenant,
        event_type="NotificationDeliveryFailed",
        username=username,
        description=f"Notification '{notification.subject}' delivery attempt {notification.attempt_count} failed.",
        details={
            "notification_id": notification.id,
            "attempt_count": notification.attempt_count,
            "terminal": notification.status == NotificationEvent.STATUS_FAILED,
        },
    )
    return notification.status == NotificationEvent.STATUS_RETRY_SCHEDULED
