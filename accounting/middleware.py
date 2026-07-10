from django.db import connection
from contextlib import contextmanager


def set_connection_tenant(tenant_id):
    """Sets the active tenant UUID in the current PostgreSQL session and switches to restricted role."""
    with connection.cursor() as cursor:
        if tenant_id:
            cursor.execute("SET ROLE ledger_tenant_role")
            cursor.execute("SET app.current_tenant_id = %s", [str(tenant_id)])
        else:
            cursor.execute("SET app.current_tenant_id = ''")
            cursor.execute("RESET ROLE")


def reset_connection_tenant():
    """Resets the active tenant UUID in the current PostgreSQL session and returns to default role."""
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant_id")
        cursor.execute("RESET ROLE")


@contextmanager
def tenant_context(tenant_id):
    """
    Context manager to safely set and restore tenant context on the DB connection.
    Guarantees reset even if exceptions occur.
    """
    # Fetch current setting if possible (to nested-restore later)
    old_tenant = None
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            try:
                cursor.execute("SHOW app.current_tenant_id")
                row = cursor.fetchone()
                if row:
                    old_tenant = row[0]
            except Exception:
                pass

        set_connection_tenant(tenant_id)
    
    try:
        yield
    finally:
        if connection.vendor == 'postgresql':
            if old_tenant and old_tenant != 'off' and old_tenant != '':
                set_connection_tenant(old_tenant)
            else:
                reset_connection_tenant()


class TenantMiddleware:
    """
    Middleware that sets the current tenant variable on the PostgreSQL database
    connection based on the authenticated user's associated tenant.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant_id = None
        
        # In a real environment, we'd check request.user.profile.tenant_id.
        # For simplicity and testability, we check if request has a user and if
        # the user object has a tenant_id attribute, or we can check header/session.
        if hasattr(request, 'user') and request.user.is_authenticated:
            if hasattr(request.user, 'tenant_id'):
                tenant_id = request.user.tenant_id
            elif hasattr(request.user, 'profile') and hasattr(request.user.profile, 'tenant_id'):
                tenant_id = request.user.profile.tenant_id
                
        # Also allow passing it via request metadata (useful in tests/views)
        if hasattr(request, 'tenant_id'):
            tenant_id = request.tenant_id

        if tenant_id and connection.vendor == 'postgresql':
            set_connection_tenant(tenant_id)
            
        try:
            response = self.get_response(request)
        finally:
            if tenant_id and connection.vendor == 'postgresql':
                reset_connection_tenant()
                
        return response
