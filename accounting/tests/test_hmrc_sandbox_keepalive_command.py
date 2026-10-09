from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class HmrcSandboxKeepaliveCommandTests(SimpleTestCase):
    @patch("accounting.management.commands.hmrc_sandbox_keepalive.call_hmrc_sandbox_keepalive")
    def test_command_writes_only_redacted_activity_evidence(self, keepalive):
        keepalive.return_value = {
            "application": "LedgerHouse",
            "endpoint": "GET /hello/application",
            "http_status": 200,
            "timestamp": "2026-08-02T22:36:41+00:00",
        }
        output_path = "/tmp/ledgerhouse-hmrc-keepalive-command.md"
        stdout = StringIO()

        call_command("hmrc_sandbox_keepalive", "--output", output_path, stdout=stdout)

        report = Path(output_path).read_text(encoding="utf-8")
        self.assertIn("HTTP status: 200", report)
        self.assertIn("GET /hello/application", report)
        self.assertNotIn("sandbox-access-token", report)
        self.assertNotIn("Authorization", report)
        self.assertIn("keep-alive succeeded", stdout.getvalue())
