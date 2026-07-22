from datetime import datetime, date
from decimal import Decimal
from django.utils import timezone
from accounting.models import AuditEvent, BankFeedConnection, BankTransaction, Journal
from accounting.reconciliation import reconcile_transaction_to_invoice


class LocalDemoBankFeedProvider:
    """Deterministic local bank-feed provider used only for development tests.

    This provider deliberately does not claim to contact a bank or an Open
    Banking aggregator. A live provider must be configured separately after a
    provider contract, consent journey and credentials are available.
    """

    provider_name = "Local demonstration feed"
    is_live = False

    @staticmethod
    def fetch_transactions(account_identifier, since_date):
        """Return deterministic synthetic data for a local account identifier."""
        return [
            {
                "date": "2026-06-25",
                "amount": "1200.00",
                "reference": "OB CUSTOMER PAYMENT REF-101",
                "fitid": "FITID-OB-991",
                "matched_to": "TC-VI-991"
            },
            {
                "date": "2026-06-26",
                "amount": "-30.00",
                "reference": "OB BANK SERVICE CHARGES",
                "fitid": "FITID-OB-992",
                "matched_to": None
            }
        ]


def bank_feed_provider_status(connection=None):
    """Return a non-secret status payload suitable for local operator UI."""
    return {
        "provider_name": LocalDemoBankFeedProvider.provider_name,
        "is_live": LocalDemoBankFeedProvider.is_live,
        "connection_status": connection.status if connection else "Not configured",
        "message": (
            "Local demonstration data only. No bank account has been contacted."
        ),
    }


def sync_bank_feed(tenant, connection, provider=None):
    """
    Syncs transactions from the bank feed connection.
    Saves them idempotently as BankTransactions and triggers reconciliation.
    """
    from accounting.models import ImportedFile
    import hashlib

    if connection.status != 'Connected':
        raise ValueError(
            f"Bank feed connection {connection.id} ({connection.bank_name}) is not active "
            f"(status: {connection.status}). Reauthorization is required before syncing."
        )
    if connection.expires_at and connection.expires_at <= timezone.now():
        connection.status = 'Expired'
        connection.save(update_fields=['status'])
        raise ValueError(
            f"Bank feed consent for connection {connection.id} ({connection.bank_name}) expired "
            f"on {connection.expires_at:%Y-%m-%d}. Reauthorization is required before syncing."
        )

    client = provider or LocalDemoBankFeedProvider()
    since_date = connection.last_sync_at.date() if connection.last_sync_at else date(2026, 1, 1)
    
    txs = client.fetch_transactions(connection.account_identifier, since_date)
    
    imported_count = 0
    reconciled_count = 0
    
    # Filter out duplicate rows that already exist
    new_txs = []
    for tx in txs:
        if not BankTransaction.objects.filter(tenant=tenant, fitid=tx["fitid"]).exists():
            new_txs.append(tx)

    if not new_txs:
        return 0, 0

    # Create virtual ImportedFile record representing this sync session
    session_id = timezone.now().isoformat()
    file_hash = hashlib.sha256(f"open-banking-sync-{connection.id}-{session_id}".encode()).hexdigest()
    imp_file = ImportedFile.objects.create(
        tenant=tenant,
        filename=f"open_banking_sync_{connection.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json",
        file_hash=file_hash,
        raw_content=f"Open Banking sync: {len(new_txs)} transactions."
    )

    for tx in new_txs:
        bank_tx = BankTransaction.objects.create(
            tenant=tenant,
            imported_file=imp_file,
            date=datetime.strptime(tx["date"], "%Y-%m-%d").date(),
            amount=Decimal(tx["amount"]),
            reference=tx["reference"],
            fitid=tx["fitid"]
        )
        imported_count += 1
        
        # If there's a matched invoice reference/ID, attempt automatic reconciliation
        matched_to = tx.get("matched_to")
        if matched_to:
            try:
                invoice_j = Journal.objects.get(tenant=tenant, source_id=matched_to)
                reconcile_transaction_to_invoice(tenant, bank_tx, invoice_j, "Open Banking Autopost")
                reconciled_count += 1
            except Journal.DoesNotExist:
                bank_tx.review_status = "NeedsInfo"
                bank_tx.save(update_fields=["review_status"])
                AuditEvent.objects.create(
                    tenant=tenant,
                    event_type="BankFeedMatchMissing",
                    username="local-bank-feed",
                    description=(
                        f"Bank transaction {bank_tx.id} expected journal source "
                        f"'{matched_to}', but no journal was found."
                    ),
                    details={
                        "bank_transaction_id": bank_tx.id,
                        "expected_source_id": matched_to,
                        "provider": getattr(client, "provider_name", client.__class__.__name__),
                    },
                )

    connection.last_sync_at = timezone.now()
    connection.save()
    AuditEvent.objects.create(
        tenant=tenant,
        event_type="BankFeedSync",
        username="local-bank-feed",
        description=(
            f"{getattr(client, 'provider_name', client.__class__.__name__)} imported "
            f"{imported_count} transaction(s); {reconciled_count} reconciled."
        ),
        details={
            "connection_id": connection.id,
            "imported_count": imported_count,
            "reconciled_count": reconciled_count,
            "is_live_provider": bool(getattr(client, "is_live", False)),
        },
    )
    
    return imported_count, reconciled_count
