from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0025_statutory_accounts_filing_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="statutoryaccountsdraft",
            name="average_number_employees",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
