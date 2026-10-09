from contextlib import contextmanager

from django.db import DatabaseError, connection


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
    # A database error inside Django's test transaction leaves PostgreSQL unable
    # to execute cleanup statements. Preserve the original application error;
    # Django will roll the transaction back before the connection is reused.
    if connection.needs_rollback:
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant_id")
            cursor.execute("RESET ROLE")
    except DatabaseError:
        # Do not hide the request's original database failure with cleanup
        # work on an already-aborted PostgreSQL transaction.
        connection.close()


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
                cursor.execute("SELECT current_setting('app.current_tenant_id', true)")
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
        tenant_id = self._tenant_id_for_request(request)

        if tenant_id and connection.vendor == 'postgresql':
            set_connection_tenant(tenant_id)
            
        try:
            response = self.get_response(request)
        finally:
            if tenant_id and connection.vendor == 'postgresql':
                reset_connection_tenant()
                
        return response

    @staticmethod
    def _tenant_id_for_request(request):
        """Select one authorised company for PostgreSQL RLS for this request."""
        if hasattr(request, "tenant_id") and request.tenant_id:
            return request.tenant_id

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        # Import lazily: this middleware loads while Django initialises apps.
        from .models import Tenant

        tenants = Tenant.objects.order_by("name") if (user.is_staff or user.is_superuser) else Tenant.objects.filter(
            user_access__user=user,
            user_access__is_active=True,
        ).distinct().order_by("name")
        # Forms carry the selected company in a hidden field. Honour that value
        # only after checking it belongs to the authenticated user's tenant set.
        # Without this, a practice POST could retain the first tenant's RLS
        # context while the view selected a different valid tenant from POST.
        requested_tenant_id = request.GET.get("company") or request.POST.get("company")
        if requested_tenant_id:
            selected = tenants.filter(id=requested_tenant_id).values_list("id", flat=True).first()
            if selected:
                return selected
        return tenants.values_list("id", flat=True).first()
