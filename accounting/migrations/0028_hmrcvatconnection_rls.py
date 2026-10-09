from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0027_notificationevent_delivery_retry_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_hmrcvatconnection ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_hmrcvatconnection ON accounting_hmrcvatconnection;
                CREATE POLICY tenant_isolation_hmrcvatconnection ON accounting_hmrcvatconnection
                    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
                    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));
                GRANT SELECT, INSERT, UPDATE, DELETE ON accounting_hmrcvatconnection TO ledger_tenant_role;
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS tenant_isolation_hmrcvatconnection ON accounting_hmrcvatconnection;
                ALTER TABLE accounting_hmrcvatconnection DISABLE ROW LEVEL SECURITY;
                REVOKE SELECT, INSERT, UPDATE, DELETE ON accounting_hmrcvatconnection FROM ledger_tenant_role;
            """,
        ),
    ]
