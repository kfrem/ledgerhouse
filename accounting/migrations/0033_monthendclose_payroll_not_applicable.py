from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0032_companies_house_sequence_grant"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthendclose",
            name="payroll_not_applicable",
            field=models.BooleanField(default=False),
        ),
    ]
