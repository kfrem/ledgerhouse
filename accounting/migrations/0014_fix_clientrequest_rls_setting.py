from django.db import migrations


def fix_clientrequest_policy(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DROP POLICY IF EXISTS tenant_isolation_clientrequest ON accounting_clientrequest;
            CREATE POLICY tenant_isolation_clientrequest ON accounting_clientrequest
                USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0013_clientrequest_rls_grants"),
    ]

    operations = [
        migrations.RunPython(fix_clientrequest_policy, migrations.RunPython.noop),
    ]
