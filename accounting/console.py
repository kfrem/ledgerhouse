from django.utils import timezone
from accounting.models import Tenant, Journal, BankFeedConnection, VatReturn
from accounting.middleware import tenant_context
from accounting.audit import run_accountant_audit_check

def get_firm_dashboard():
    """
    Aggregates cross-tenant metrics for the partner firm dashboard.
    Loops through tenants using the tenant_context context manager to respect RLS boundaries.
    """
    dashboard = []
    
    for tenant in Tenant.objects.all():
        with tenant_context(tenant.id):
            # Check pending review count
            pending_reviews = Journal.objects.filter(status='RequiresReview').count()
            
            # Run accountant audit check
            audit_info = run_accountant_audit_check(tenant)
            
            # Get bank feed status
            feeds = []
            for feed in BankFeedConnection.objects.all():
                feeds.append({
                    "bank_name": feed.bank_name,
                    "account_identifier": feed.account_identifier,
                    "status": feed.status,
                    "expires_at": feed.expires_at.isoformat() if feed.expires_at else None
                })
                
            # Get latest filed VAT return
            latest_vat = VatReturn.objects.order_by('-end_date').first()
            vat_info = {
                "period": f"{latest_vat.start_date.isoformat()} to {latest_vat.end_date.isoformat()}" if latest_vat else "None Filed",
                "status": latest_vat.status if latest_vat else None,
                "receipt_id": latest_vat.hmrc_receipt_id if latest_vat else None
            }
            
            dashboard.append({
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "trial_balance_balanced": audit_info.get("trial_balance_balanced", False),
                "bank_reconciled": audit_info.get("bank_reconciliation", {}).get("reconciled", False),
                "pending_reviews_count": pending_reviews,
                "latest_vat_return": vat_info,
                "active_bank_feeds": feeds
            })
            
    return dashboard
