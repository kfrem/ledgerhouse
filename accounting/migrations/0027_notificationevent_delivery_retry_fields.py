from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0026_statutoryaccountsdraft_average_number_employees"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationevent",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="notificationevent",
            name="last_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="notificationevent",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
