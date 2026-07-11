"""Deployment system checks.

LedgerHouse's core safeguards (double-entry balance, closed periods, VAT
locks, audit immutability, tenant RLS) live in the PostgreSQL layer, so the
database backend and connection role are deployment-critical configuration.
Run with:  python manage.py check --database default
"""
from django.core.checks import Error, Warning, Tags, register
from django.db import connections


@register(Tags.database)
def check_database_backend(app_configs, databases=None, **kwargs):
    errors = []
    if not databases:
        return errors

    for alias in databases:
        conn = connections[alias]
        if conn.vendor != 'postgresql':
            errors.append(Error(
                f"Database '{alias}' uses backend '{conn.vendor}', but LedgerHouse "
                f"requires PostgreSQL. Balance/period/VAT-lock triggers, audit "
                f"immutability and tenant RLS only exist on PostgreSQL.",
                id='accounting.E001',
            ))
    return errors


@register(Tags.database)
def check_connection_not_superuser(app_configs, databases=None, **kwargs):
    """Warn when the app connects as a superuser/BYPASSRLS role.

    Superusers bypass row-level security entirely (even with FORCE RLS), so
    tenant isolation then depends solely on the middleware issuing SET ROLE.
    Production should connect as a non-superuser role (see
    deploy/create_app_role.sql).
    """
    from django.conf import settings
    warnings = []
    if not databases or settings.DEBUG:
        return warnings

    for alias in databases:
        conn = connections[alias]
        if conn.vendor != 'postgresql':
            continue
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
                row = cursor.fetchone()
        except Exception:
            continue  # connection problems are reported by Django's own checks
        if row and (row[0] or row[1]):
            warnings.append(Warning(
                f"Database '{alias}' connects as a superuser or BYPASSRLS role. "
                f"Row-level security is bypassed for any query that does not go "
                f"through tenant_context/TenantMiddleware. Create a restricted "
                f"application role with deploy/create_app_role.sql and connect as "
                f"that role in production.",
                id='accounting.W001',
            ))
    return warnings
