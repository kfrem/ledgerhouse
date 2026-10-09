from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0031_tenant_user_access_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON accounting_companieshousesubmissionsequence
                    TO ledger_tenant_role;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
