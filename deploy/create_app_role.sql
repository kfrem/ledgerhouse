-- Creates the restricted application login role for production.
--
-- Run once, as the database admin, after migrations have been applied:
--   docker exec -i ledgerhouse_db psql -U <admin_user> -d <db_name> < deploy/create_app_role.sql
--
-- Then set APP_DB_USER=ledgerhouse_app and APP_DB_PASSWORD in .env and
-- restart the web service. Because ledgerhouse_app is NOSUPERUSER and
-- NOBYPASSRLS, PostgreSQL row-level security applies to every query it
-- issues -- tenant isolation no longer depends solely on the middleware
-- executing SET ROLE.
--
-- CHANGE THE PASSWORD BELOW BEFORE RUNNING.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ledgerhouse_app') THEN
        CREATE ROLE ledgerhouse_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
            PASSWORD 'CHANGE-ME-BEFORE-RUNNING';
    END IF;
END
$$;

-- The app role is a member of ledger_tenant_role (created by migration 0001),
-- which already carries the per-table grants used with SET ROLE.
GRANT ledger_tenant_role TO ledgerhouse_app;

-- Framework tables (sessions, auth, admin) plus accounting tables that are
-- accessed outside an explicit SET ROLE (RLS still applies via FORCE RLS).
GRANT USAGE ON SCHEMA public TO ledgerhouse_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ledgerhouse_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ledgerhouse_app;

-- Ensure tables created by future migrations are also reachable
-- (run migrations as the admin/owner role, never as ledgerhouse_app).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ledgerhouse_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ledgerhouse_app;
