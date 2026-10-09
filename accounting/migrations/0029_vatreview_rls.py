from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0028_hmrcvatconnection_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_vatreview ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_vatreview ON accounting_vatreview;
                CREATE POLICY tenant_isolation_vatreview ON accounting_vatreview
                    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
                    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));
                GRANT SELECT, INSERT, UPDATE, DELETE ON accounting_vatreview TO ledger_tenant_role;
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS tenant_isolation_vatreview ON accounting_vatreview;
                ALTER TABLE accounting_vatreview DISABLE ROW LEVEL SECURITY;
                REVOKE SELECT, INSERT, UPDATE, DELETE ON accounting_vatreview FROM ledger_tenant_role;
            """,
        ),
    ]
