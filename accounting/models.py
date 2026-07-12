import uuid
from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class NominalAccount(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)  # Asset, Liability, Equity, Revenue, Cost of Sales, Expense
    canonical_taxonomy = models.CharField(max_length=100)

    class Meta:
        unique_together = ('tenant', 'code')

    def __str__(self):
        return f"{self.code} - {self.name}"


class AccountingPeriod(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        status = "Closed" if self.is_closed else "Open"
        return f"{self.start_date} to {self.end_date} ({status})"


class Journal(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.CharField(max_length=255)
    source_type = models.CharField(max_length=50)  # ManualJournal, SupplierInvoice, SalesInvoice, BankPayment, etc.
    source_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='Posted')  # Posted, RequiresReview

    def __str__(self):
        return f"{self.source_type} {self.id} on {self.date}"


class JournalLine(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(NominalAccount, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    vat_code = models.CharField(max_length=5, default='OS')  # SR, RR, ZR, EX, OS
    vat_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0.0000)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    department = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Line for Journal {self.journal_id}: {self.account.code} (Dr {self.debit} / Cr {self.credit})"


class AuditEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=50)
    username = models.CharField(max_length=100)
    description = models.TextField()
    details = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.timestamp} - {self.event_type} - {self.username}"


class VatRate(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    vat_code = models.CharField(max_length=5)  # SR, RR, ZR, EX, OS
    rate = models.DecimalField(max_digits=5, decimal_places=4)  # e.g. 0.2000
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('tenant', 'vat_code', 'effective_from')

    def __str__(self):
        return f"{self.vat_code} ({self.rate * 100}%) from {self.effective_from}"


class VatDecisionRule(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    priority = models.IntegerField(default=10)  # lower number = higher priority
    supplier_name_pattern = models.CharField(max_length=100, blank=True, default='')
    account_code_pattern = models.CharField(max_length=10, blank=True, default='')
    vat_code = models.CharField(max_length=5)  # SR, RR, ZR, EX, OS
    description = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f"Rule {self.id}: Supplier '{self.supplier_name_pattern}', Account '{self.account_code_pattern}' -> {self.vat_code}"


class ImportedFile(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    raw_content = models.TextField()
    file_hash = models.CharField(max_length=64)

    class Meta:
        unique_together = ('tenant', 'file_hash')

    def __str__(self):
        return f"{self.filename} uploaded at {self.uploaded_at}"


class BankTransaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    imported_file = models.ForeignKey(ImportedFile, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=255)
    fitid = models.CharField(max_length=100)

    class Meta:
        unique_together = ('tenant', 'fitid')

    def __str__(self):
        return f"BankTx {self.fitid}: {self.date} {self.amount} {self.reference}"


class EvidenceDocument(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    file_content = models.BinaryField()
    content_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(max_length=100)

    def __str__(self):
        return f"Evidence {self.filename} ({self.content_type})"


class JournalEvidenceLink(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='evidence_links')
    document = models.ForeignKey(EvidenceDocument, on_delete=models.CASCADE)
    linked_at = models.DateTimeField(auto_now_add=True)
    linked_by = models.CharField(max_length=100)

    class Meta:
        unique_together = ('tenant', 'journal', 'document')

    def __str__(self):
        return f"Link {self.id}: Journal {self.journal_id} <-> Doc {self.document_id}"


class BankReconciliation(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    bank_transaction = models.OneToOneField(BankTransaction, on_delete=models.CASCADE, related_name='reconciliation')
    matched_journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='reconciliations')
    reconciled_at = models.DateTimeField(auto_now_add=True)
    reconciled_by = models.CharField(max_length=100)

    def __str__(self):
        return f"Reconciliation {self.id}: BankTx {self.bank_transaction_id} <-> Journal {self.matched_journal_id}"


class VatReturn(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    locked_at = models.DateTimeField(auto_now_add=True)
    locked_by = models.CharField(max_length=100)
    total_output_vat = models.DecimalField(max_digits=12, decimal_places=2)
    total_input_vat = models.DecimalField(max_digits=12, decimal_places=2)
    net_vat_payable = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default='Draft')  # Draft, Submitted
    hmrc_receipt_id = models.CharField(max_length=100, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    period_key = models.CharField(max_length=10, null=True, blank=True)

    def __str__(self):
        return f"VatReturn {self.id} for {self.start_date} to {self.end_date} (Net: {self.net_vat_payable}, Status: {self.status})"


class HmrcVatConnection(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='hmrc_vat_connection')
    vrn = models.CharField(max_length=9, blank=True, default='')
    status = models.CharField(max_length=20, default='NotConnected')
    access_token = models.TextField(blank=True, default='')
    refresh_token = models.TextField(blank=True, default='')
    scope = models.CharField(max_length=120, blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    last_authorised_at = models.DateTimeField(null=True, blank=True)
    last_obligations_sync_at = models.DateTimeField(null=True, blank=True)
    latest_obligations = models.JSONField(default=list, blank=True)
    last_submission_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = self.vrn or "No VRN"
        return f"HMRC VAT {label} ({self.status}) for Tenant {self.tenant_id}"


class VatReview(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='vat_reviews')
    period_key = models.CharField(max_length=10)
    start_date = models.DateField()
    end_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Draft')  # Draft, Ready, ClientApproved, Submitted
    prepared_payload = models.JSONField(default=dict, blank=True)
    evidence_complete = models.BooleanField(default=False)
    bank_reconciled = models.BooleanField(default=False)
    vat_codes_reviewed = models.BooleanField(default=False)
    exceptions_resolved = models.BooleanField(default=False)
    client_approved = models.BooleanField(default=False)
    client_approved_at = models.DateTimeField(null=True, blank=True)
    client_approved_by = models.CharField(max_length=100, blank=True, default='')
    practice_approved_at = models.DateTimeField(null=True, blank=True)
    practice_approved_by = models.CharField(max_length=100, blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    hmrc_receipt_id = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'period_key')

    @property
    def checklist_complete(self):
        return all(
            [
                self.evidence_complete,
                self.bank_reconciled,
                self.vat_codes_reviewed,
                self.exceptions_resolved,
            ]
        )

    @property
    def ready_to_submit(self):
        return self.checklist_complete and self.client_approved

    def __str__(self):
        return f"VAT review {self.period_key} for {self.tenant_id} ({self.status})"


class BankFeedConnection(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    bank_name = models.CharField(max_length=100)
    account_identifier = models.CharField(max_length=100)  # Account number/IBAN
    status = models.CharField(max_length=20, default='Connected')  # Connected, Expired
    connected_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    consent_token = models.TextField()

    def __str__(self):
        return f"{self.bank_name} - {self.account_identifier} ({self.status}) for Tenant {self.tenant_id}"
