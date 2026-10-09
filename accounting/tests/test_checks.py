from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from accounting.checks import check_connection_not_superuser
from accounting.middleware import TenantMiddleware
from accounting.models import Tenant, TenantUserAccess


class DeploymentCheckTests(SimpleTestCase):
    @override_settings(DEBUG=False)
    @patch("accounting.checks.connections")
    def test_superuser_warning_is_skipped_for_disposable_test_database(self, connections):
        connections.__getitem__.return_value = SimpleNamespace(
            vendor="postgresql",
            settings_dict={"NAME": "test_ledgerhouse_db"},
        )

        warnings = check_connection_not_superuser(None, databases=["default"])

        self.assertEqual(warnings, [])

    @override_settings(DEBUG=False)
    @patch("accounting.checks.connections")
    def test_superuser_warning_remains_enabled_for_runtime_database(self, connections):
        cursor = MagicMock()
        cursor.fetchone.return_value = (True, False)
        connection = MagicMock()
        connection.vendor = "postgresql"
        connection.settings_dict = {"NAME": "ledgerhouse_db"}
        connection.cursor.return_value.__enter__.return_value = cursor
        connections.__getitem__.return_value = connection

        warnings = check_connection_not_superuser(None, databases=["default"])

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "accounting.W001")


class TenantMiddlewareSelectionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user("client-user", password="test-password")
        self.first_tenant = Tenant.objects.create(name="First authorised client")
        self.second_tenant = Tenant.objects.create(name="Second authorised client")
        self.private_tenant = Tenant.objects.create(name="Not authorised client")
        TenantUserAccess.objects.create(tenant=self.first_tenant, user=self.user)
        TenantUserAccess.objects.create(tenant=self.second_tenant, user=self.user)

    def test_posted_company_selects_that_authorised_tenant_for_rls(self):
        request = self.factory.post("/practice/action/", {"company": str(self.second_tenant.id)})
        request.user = self.user

        selected = TenantMiddleware._tenant_id_for_request(request)

        self.assertEqual(selected, self.second_tenant.id)

    def test_posted_unapproved_company_is_not_used_for_rls(self):
        request = self.factory.post("/practice/action/", {"company": str(self.private_tenant.id)})
        request.user = self.user

        selected = TenantMiddleware._tenant_id_for_request(request)

        self.assertEqual(selected, self.first_tenant.id)
