from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0022_companieshousefilingsubmission"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompaniesHouseSubmissionPoll",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("submission_number", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Prepared", "Prepared"),
                            ("Submitted", "Submitted"),
                            ("Pending", "Pending"),
                            ("Accepted", "Accepted"),
                            ("Rejected", "Rejected"),
                            ("Failed", "Failed"),
                        ],
                        max_length=20,
                    ),
                ),
                ("response_xml", models.TextField(blank=True, default="")),
                ("messages", models.JSONField(blank=True, default=list)),
                ("polled_by", models.CharField(blank=True, default="", max_length=150)),
                ("polled_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="poll_history",
                        to="accounting.companieshousefilingsubmission",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="companies_house_submission_polls",
                        to="accounting.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ("-polled_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="CompaniesHouseApprovalGate",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("client_pack_reference", models.CharField(blank=True, default="", max_length=80)),
                ("practice_signed_off", models.BooleanField(default=False)),
                ("practice_signed_off_by", models.CharField(blank=True, default="", max_length=150)),
                ("practice_signed_off_at", models.DateTimeField(blank=True, null=True)),
                ("test_mode_only", models.BooleanField(default=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Blocked", "Blocked"),
                            ("Ready", "Ready"),
                            ("SignedOff", "Signed off"),
                        ],
                        default="Blocked",
                        max_length=20,
                    ),
                ),
                ("readiness_messages", models.JSONField(blank=True, default=list)),
                (
                    "production_lock_note",
                    models.TextField(
                        blank=True,
                        default="Companies House filing remains locked to test mode until production approval and live settings are explicitly configured.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client_approval",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="companies_house_approval_gates",
                        to="accounting.clientapprovalrecord",
                    ),
                ),
                (
                    "statutory_accounts",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="companies_house_approval_gate",
                        to="accounting.statutoryaccountsdraft",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="companies_house_approval_gates",
                        to="accounting.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
            },
        ),
    ]
