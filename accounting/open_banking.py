from datetime import datetime, date
from decimal import Decimal
from django.utils import timezone
from accounting.models import BankFeedConnection, BankTransaction, Journal
from accounting.reconciliation import reconcile_transaction_to_invoice

class MockOpenBankingClient:
    """Mock client simulating FCA-aggregator APIs (Nordigen / GoCardless)."""
    @staticmethod
    def fetch_transactions(account_identifier, since_date):
        # Generate mock transaction data for testing
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


def sync_bank_feed(tenant, connection):
    """
    Syncs transactions from the bank feed connection.
    Saves them idempotently as BankTransactions and triggers reconciliation.
    """
    from accounting.models import ImportedFile
    import hashlib

    client = MockOpenBankingClient()
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
                pass
                
    connection.last_sync_at = timezone.now()
    connection.save()
    
    return imported_count, reconciled_count
