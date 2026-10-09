from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0030_complete_tenant_table_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounting_tenantuseraccess ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS tenant_isolation_accounting_tenantuseraccess
                    ON accounting_tenantuseraccess;
                CREATE POLICY tenant_isolation_accounting_tenantuseraccess
                    ON accounting_tenantuseraccess
                    USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
                    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));
                GRANT SELECT, INSERT, UPDATE, DELETE ON accounting_tenantuseraccess
                    TO ledger_tenant_role;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
