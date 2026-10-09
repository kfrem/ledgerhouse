from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0029_vatreview_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                DECLARE
                    tenant_table record;
                    policy_name text;
                BEGIN
                    FOR tenant_table IN
                        SELECT table_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name LIKE 'accounting_%'
                          AND column_name = 'tenant_id'
                        GROUP BY table_name
                    LOOP
                        policy_name := 'tenant_isolation_' || tenant_table.table_name;
                        EXECUTE format(
                            'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                            tenant_table.table_name
                        );
                        EXECUTE format(
                            'DROP POLICY IF EXISTS %I ON public.%I',
                            policy_name,
                            tenant_table.table_name
                        );
                        EXECUTE format(
                            'CREATE POLICY %I ON public.%I '
                            'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant_id'', true), '''')) '
                            'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant_id'', true), ''''))',
                            policy_name,
                            tenant_table.table_name
                        );
                        EXECUTE format(
                            'GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO ledger_tenant_role',
                            tenant_table.table_name
                        );
                    END LOOP;

                    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ledger_tenant_role;
                END $$;
            """,
            # This is a monotonic hardening migration. Older individual
            # policies are intentionally not removed on a reverse migration.
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
