from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from accounting.checks import check_connection_not_superuser


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
