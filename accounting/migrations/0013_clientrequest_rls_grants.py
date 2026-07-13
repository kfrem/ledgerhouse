from django.db import migrations


def grant_clientrequest_access(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE accounting_clientrequest ENABLE ROW LEVEL SECURITY;")
        cursor.execute("ALTER TABLE accounting_clientrequest FORCE ROW LEVEL SECURITY;")
        cursor.execute(
            """
            DROP POLICY IF EXISTS tenant_isolation_clientrequest ON accounting_clientrequest;
            CREATE POLICY tenant_isolation_clientrequest ON accounting_clientrequest
                USING (tenant_id = current_setting('app.current_tenant_id')::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
            """
        )
        cursor.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON accounting_clientrequest TO ledger_tenant_role;")
        cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ledger_tenant_role;")


def revoke_clientrequest_access(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP POLICY IF EXISTS tenant_isolation_clientrequest ON accounting_clientrequest;")
        cursor.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON accounting_clientrequest FROM ledger_tenant_role;")


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0012_banktransaction_review_status_and_more"),
    ]

    operations = [
        migrations.RunPython(grant_clientrequest_access, revoke_clientrequest_access),
    ]
