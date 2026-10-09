from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounting.models import AccountingPeriodLock, AuditEvent, FixedAsset, Journal, PayrollSummary, Tenant
from accounting.period_end import close_period_end, period_end_control_status, post_period_end_schedules


class PeriodEndScheduleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Period End Ltd")
        self.start = date(2026, 6, 1)
        self.end = date(2026, 6, 30)
        self.asset = FixedAsset.objects.create(
            tenant=self.tenant, asset_name="Laptop", purchase_date=self.start,
            cost=Decimal("1200.00"), depreciation_rate=Decimal("25.00"),
        )

    def test_posts_balanced_schedules_once_and_updates_close_controls(self):
        result = post_period_end_schedules(
            self.tenant, self.start, self.end, "practice",
            accrual_amount=Decimal("120.00"), prepayment_amount=Decimal("60.00"),
        )
        self.asset.refresh_from_db()
        close = result["month_end_close"]

        self.assertEqual(Journal.objects.filter(tenant=self.tenant).count(), 3)
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("25.00"))
        self.assertTrue(close.accruals_posted)
        self.assertTrue(close.prepayments_posted)
        self.assertTrue(close.depreciation_posted)
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, event_type="PeriodEndSchedules").exists())

        repeat = post_period_end_schedules(
            self.tenant, self.start, self.end, "practice",
            accrual_amount=Decimal("120.00"), prepayment_amount=Decimal("60.00"),
        )
        self.asset.refresh_from_db()
        self.assertEqual(repeat["created"], [])
        self.assertEqual(Journal.objects.filter(tenant=self.tenant).count(), 3)
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("25.00"))

    def test_locked_period_is_rejected_without_posting(self):
        AccountingPeriodLock.objects.create(
            tenant=self.tenant, period_start=self.start, period_end=self.end, locked_by="partner"
        )
        with self.assertRaisesMessage(ValueError, "period is locked"):
            post_period_end_schedules(self.tenant, self.start, self.end, "practice")
        self.assertFalse(Journal.objects.filter(tenant=self.tenant).exists())

    def test_close_requires_schedules_and_payroll_then_locks_period(self):
        with self.assertRaisesMessage(ValueError, "Post accruals"):
            close_period_end(self.tenant, self.start, self.end, "partner")

        post_period_end_schedules(
            self.tenant, self.start, self.end, "practice",
            accrual_amount=Decimal("20.00"), prepayment_amount=Decimal("10.00"),
        )
        with self.assertRaisesMessage(ValueError, "Post the payroll journal"):
            close_period_end(self.tenant, self.start, self.end, "partner")

        PayrollSummary.objects.create(
            tenant=self.tenant, period_start=self.start, period_end=self.end,
            gross_pay=Decimal("100.00"), journal_posted=True, status="Posted",
        )
        close = close_period_end(self.tenant, self.start, self.end, "partner")
        controls = period_end_control_status(self.tenant, self.start, self.end)

        self.assertEqual(close.status, "Closed")
        self.assertTrue(controls["locked"])
        self.assertTrue(AuditEvent.objects.filter(tenant=self.tenant, event_type="PeriodEndClosed").exists())

    def test_close_records_explicit_no_payroll_declaration(self):
        post_period_end_schedules(
            self.tenant, self.start, self.end, "practice",
            accrual_amount=Decimal("20.00"), prepayment_amount=Decimal("10.00"),
        )

        close = close_period_end(
            self.tenant, self.start, self.end, "partner", payroll_not_applicable=True
        )
        controls = period_end_control_status(self.tenant, self.start, self.end)

        self.assertTrue(close.payroll_not_applicable)
        self.assertFalse(close.payroll_posted)
        self.assertTrue(controls["payroll_ready"])
        self.assertTrue(controls["locked"])
        event = AuditEvent.objects.get(tenant=self.tenant, event_type="PeriodEndClosed")
        self.assertTrue(event.details["payroll_not_applicable"])
