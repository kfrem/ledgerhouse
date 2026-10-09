import uuid
from django.conf import settings
from django.db import models

from .crypto import EncryptedTextField


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantUserAccess(models.Model):
    ROLE_CLIENT = "Client"
    ROLE_PRACTICE = "Practice"
    ROLE_CHOICES = [
        (ROLE_CLIENT, "Client"),
        (ROLE_PRACTICE, "Practice"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="user_access")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_access")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "user")

    def __str__(self):
        return f"{self.user_id} -> {self.tenant_id} ({self.role})"


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
    review_status = models.CharField(max_length=20, default='Unreviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        unique_together = ('tenant', 'fitid')

    def __str__(self):
        return f"BankTx {self.fitid}: {self.date} {self.amount} {self.reference}"


class EvidenceDocument(models.Model):
    CATEGORY_CHOICES = [
        ("Uncategorised", "Uncategorised"),
        ("SalesInvoice", "Sales invoice"),
        ("PurchaseInvoice", "Purchase invoice"),
        ("Receipt", "Receipt"),
        ("BankStatement", "Bank statement"),
        ("Payroll", "Payroll"),
        ("Contract", "Contract"),
        ("Tax", "Tax"),
        ("Other", "Other"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    file_content = models.BinaryField()
    content_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(max_length=100)
    review_status = models.CharField(max_length=20, default='Unreviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=100, blank=True, default='')
    document_category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default="Uncategorised")
    supplier_or_customer = models.CharField(max_length=160, blank=True, default='')
    document_date = models.DateField(null=True, blank=True)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    suggested_account_code = models.CharField(max_length=10, blank=True, default='')
    review_note = models.TextField(blank=True, default='')

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
    access_token = EncryptedTextField(blank=True, default='')
    refresh_token = EncryptedTextField(blank=True, default='')
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


class HmrcServiceApproval(models.Model):
    SERVICE_VAT_MTD = "VAT_MTD"
    SERVICE_CORPORATION_TAX = "CORPORATION_TAX"
    SERVICE_PAYE_RTI = "PAYE_RTI"
    SERVICE_CIS = "CIS"
    SERVICE_INCOME_TAX_MTD = "INCOME_TAX_MTD"
    SERVICE_SELF_ASSESSMENT = "SELF_ASSESSMENT"
    SERVICE_CHOICES = [
        (SERVICE_VAT_MTD, "VAT (Making Tax Digital)"),
        (SERVICE_CORPORATION_TAX, "Corporation Tax Online"),
        (SERVICE_PAYE_RTI, "PAYE Online / RTI"),
        (SERVICE_CIS, "Construction Industry Scheme Online"),
        (SERVICE_INCOME_TAX_MTD, "Income Tax (Making Tax Digital)"),
        (SERVICE_SELF_ASSESSMENT, "Self Assessment Online"),
    ]

    TRANSPORT_REST_OAUTH = "REST_OAUTH"
    TRANSPORT_XML_GATEWAY = "XML_GATEWAY"
    TRANSPORT_CHOICES = [
        (TRANSPORT_REST_OAUTH, "REST API with OAuth"),
        (TRANSPORT_XML_GATEWAY, "HMRC XML gateway"),
    ]

    STATUS_NOT_STARTED = "NotStarted"
    STATUS_DEVELOPMENT = "Development"
    STATUS_READY_TO_APPLY = "ReadyToApply"
    STATUS_CREDENTIALS_REQUESTED = "CredentialsRequested"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, "Not started"),
        (STATUS_DEVELOPMENT, "Development and local testing"),
        (STATUS_READY_TO_APPLY, "Ready to apply"),
        (STATUS_CREDENTIALS_REQUESTED, "Credentials requested"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    service = models.CharField(max_length=32, choices=SERVICE_CHOICES, unique=True)
    transport = models.CharField(max_length=20, choices=TRANSPORT_CHOICES)
    application_name = models.CharField(max_length=120, default="LedgerHouse")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    credentials_requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    credentials_verified_at = models.DateTimeField(null=True, blank=True)
    live_submission_enabled = models.BooleanField(default=False)
    review_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def live_ready(self):
        return all(
            [
                self.status == self.STATUS_APPROVED,
                self.credentials_verified_at,
                self.live_submission_enabled,
            ]
        )

    def __str__(self):
        return f"{self.get_service_display()} ({self.get_status_display()})"


class HmrcTaxProfile(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="hmrc_tax_profile")
    corporation_tax_utr = EncryptedTextField(blank=True, default="")
    company_number = EncryptedTextField(blank=True, default="")
    paye_reference = EncryptedTextField(blank=True, default="")
    accounts_office_reference = EncryptedTextField(blank=True, default="")
    cis_utr = EncryptedTextField(blank=True, default="")
    self_assessment_utr = EncryptedTextField(blank=True, default="")
    national_insurance_number = EncryptedTextField(blank=True, default="")
    income_tax_business_id = EncryptedTextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def masked(value):
        value = str(value or "")
        if not value:
            return "Not recorded"
        if len(value) <= 4:
            return "*" * len(value)
        return f"{'*' * (len(value) - 4)}{value[-4:]}"

    def __str__(self):
        return f"HMRC tax profile for {self.tenant}"


class HmrcFilingCase(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_VALIDATION_FAILED = "ValidationFailed"
    STATUS_READY_FOR_APPROVAL = "ReadyForApproval"
    STATUS_APPROVED_TO_FILE = "ApprovedToFile"
    STATUS_SUBMITTED = "Submitted"
    STATUS_ACCEPTED = "Accepted"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_VALIDATION_FAILED, "Validation failed"),
        (STATUS_READY_FOR_APPROVAL, "Ready for approval"),
        (STATUS_APPROVED_TO_FILE, "Approved to file"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="hmrc_filing_cases")
    service = models.CharField(max_length=32, choices=HmrcServiceApproval.SERVICE_CHOICES)
    filing_type = models.CharField(max_length=40)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    encrypted_payload = EncryptedTextField(blank=True, default="")
    validation_errors = models.JSONField(default=list, blank=True)
    validation_warnings = models.JSONField(default=list, blank=True)
    client_approved_at = models.DateTimeField(null=True, blank=True)
    client_approved_by = models.CharField(max_length=150, blank=True, default="")
    practice_approved_at = models.DateTimeField(null=True, blank=True)
    practice_approved_by = models.CharField(max_length=150, blank=True, default="")
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider_correlation_id = EncryptedTextField(blank=True, default="")
    provider_receipt_id = EncryptedTextField(blank=True, default="")
    provider_response = EncryptedTextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-period_end", "service", "filing_type")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="hmrc_filing_period_is_valid",
            ),
        ]

    @property
    def approvals_complete(self):
        return bool(self.client_approved_at and self.practice_approved_at)

    def __str__(self):
        return f"{self.get_service_display()} {self.filing_type} for {self.tenant}"


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


class ClientRequest(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='client_requests')
    subject = models.CharField(max_length=160)
    category = models.CharField(max_length=50, default='General')
    message = models.TextField()
    status = models.CharField(max_length=20, default='Open')  # Open, InProgress, Resolved
    priority = models.CharField(max_length=20, default='Normal')  # Low, Normal, High
    submitted_by = models.CharField(max_length=100)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return f"{self.tenant.name}: {self.subject} ({self.status})"


class BankFeedConnection(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    bank_name = models.CharField(max_length=100)
    account_identifier = models.CharField(max_length=100)  # Account number/IBAN
    status = models.CharField(max_length=20, default='Connected')  # Connected, Expired
    connected_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    consent_token = EncryptedTextField()

    def __str__(self):
        return f"{self.bank_name} - {self.account_identifier} ({self.status}) for Tenant {self.tenant_id}"


class ClientInvitation(models.Model):
    STATUS_PENDING = "Pending"
    STATUS_ACCEPTED = "Accepted"
    STATUS_REVOKED = "Revoked"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REVOKED, "Revoked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=TenantUserAccess.ROLE_CHOICES, default=TenantUserAccess.ROLE_CLIENT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    invited_by = models.CharField(max_length=100)
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.CharField(max_length=150, blank=True, default='')

    class Meta:
        unique_together = ("tenant", "email")

    def __str__(self):
        return f"{self.email} invited to {self.tenant.name} ({self.status})"


class SubscriptionPlan(models.Model):
    STATUS_TRIAL = "Trial"
    STATUS_ACTIVE = "Active"
    STATUS_PAUSED = "Paused"
    STATUS_CANCELLED = "Cancelled"
    STATUS_CHOICES = [
        (STATUS_TRIAL, "Trial"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    PROVIDER_MANUAL = "Manual"
    PROVIDER_STRIPE = "Stripe"
    PROVIDER_GOCARDLESS = "GoCardless"
    PROVIDER_CHOICES = [
        (PROVIDER_MANUAL, "Manual"),
        (PROVIDER_STRIPE, "Stripe"),
        (PROVIDER_GOCARDLESS, "GoCardless"),
    ]
    COLLECTION_CARD = "Card"
    COLLECTION_DIRECT_DEBIT = "DirectDebit"
    COLLECTION_BANK_TRANSFER = "BankTransfer"
    COLLECTION_CHOICES = [
        (COLLECTION_CARD, "Card"),
        (COLLECTION_DIRECT_DEBIT, "Direct debit"),
        (COLLECTION_BANK_TRANSFER, "Bank transfer"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="subscription")
    plan_name = models.CharField(max_length=80, default="Local trial")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="GBP")
    billing_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_MANUAL)
    collection_method = models.CharField(max_length=20, choices=COLLECTION_CHOICES, default=COLLECTION_DIRECT_DEBIT)
    provider_customer_id = models.CharField(max_length=120, blank=True, default='')
    provider_subscription_id = models.CharField(max_length=120, blank=True, default='')
    latest_invoice_status = models.CharField(max_length=40, blank=True, default='Not issued')
    next_invoice_date = models.DateField(null=True, blank=True)
    last_payment_at = models.DateTimeField(null=True, blank=True)
    billing_note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant.name}: {self.plan_name} ({self.status})"


class SalesInvoice(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_ISSUED = "Issued"
    STATUS_PART_PAID = "PartPaid"
    STATUS_PAID = "Paid"
    STATUS_OVERDUE = "Overdue"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_PART_PAID, "Part paid"),
        (STATUS_PAID, "Paid"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sales_invoices")
    invoice_number = models.CharField(max_length=40)
    customer_name = models.CharField(max_length=160)
    issue_date = models.DateField()
    due_date = models.DateField()
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant", "invoice_number")

    @property
    def balance_due(self):
        return self.gross_amount - self.paid_amount

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name} ({self.status})"


class SalesReceipt(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sales_receipts")
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="receipts")
    receipt_reference = models.CharField(max_length=120)
    receipt_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "receipt_reference"),
                name="unique_sales_receipt_reference_per_tenant",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="sales_receipt_amount_positive",
            ),
        ]
        ordering = ("-receipt_date", "-id")

    def __str__(self):
        return f"{self.receipt_reference}: {self.invoice.invoice_number}"


class SalesQuote(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_SENT = "Sent"
    STATUS_ACCEPTED = "Accepted"
    STATUS_EXPIRED = "Expired"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_EXPIRED, "Expired"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sales_quotes")
    quote_number = models.CharField(max_length=40)
    customer_name = models.CharField(max_length=160)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    converted_invoice = models.ForeignKey(SalesInvoice, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "quote_number")

    def __str__(self):
        return f"{self.quote_number} - {self.customer_name} ({self.status})"


class PurchaseBill(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_AWAITING_APPROVAL = "AwaitingApproval"
    STATUS_APPROVED = "Approved"
    STATUS_SCHEDULED = "Scheduled"
    STATUS_PAID = "Paid"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_AWAITING_APPROVAL, "Awaiting approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_PAID, "Paid"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="purchase_bills")
    bill_number = models.CharField(max_length=40)
    supplier_name = models.CharField(max_length=160)
    bill_date = models.DateField()
    due_date = models.DateField()
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approval_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("tenant", "bill_number")

    @property
    def balance_due(self):
        return self.gross_amount - self.paid_amount

    def __str__(self):
        return f"{self.bill_number} - {self.supplier_name} ({self.status})"


class PurchaseOrder(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_APPROVED = "Approved"
    STATUS_RECEIVED = "Received"
    STATUS_BILLED = "Billed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_BILLED, "Billed"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="purchase_orders")
    order_number = models.CharField(max_length=40)
    supplier_name = models.CharField(max_length=160)
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_by = models.CharField(max_length=100, blank=True, default="")
    linked_bill = models.ForeignKey(PurchaseBill, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "order_number")

    def __str__(self):
        return f"{self.order_number} - {self.supplier_name} ({self.status})"


class CreditControlAction(models.Model):
    ACTION_EMAIL = "EmailReminder"
    ACTION_CALL = "Call"
    ACTION_STATEMENT = "Statement"
    ACTION_HOLD = "Hold"
    ACTION_CHOICES = [
        (ACTION_EMAIL, "Email reminder"),
        (ACTION_CALL, "Call"),
        (ACTION_STATEMENT, "Statement"),
        (ACTION_HOLD, "Hold service"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="credit_control_actions")
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="credit_actions")
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES)
    action_date = models.DateField()
    owner = models.CharField(max_length=100)
    note = models.TextField()
    next_action_date = models.DateField(null=True, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sales_invoice.invoice_number}: {self.action_type}"


class SupplierPaymentRun(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_APPROVED = "Approved"
    STATUS_PAID = "Paid"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_PAID, "Paid"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="supplier_payment_runs")
    bills = models.ManyToManyField(
        PurchaseBill,
        through="SupplierPaymentRunBill",
        related_name="payment_runs",
        blank=True,
    )
    run_reference = models.CharField(max_length=40)
    scheduled_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_by = models.CharField(max_length=100, blank=True, default="")
    paid_by = models.CharField(max_length=100, blank=True, default="")
    payment_reference = models.CharField(max_length=120, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "run_reference")

    def __str__(self):
        return f"{self.run_reference} ({self.status})"


class SupplierPaymentRunBill(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="supplier_payment_run_bills")
    payment_run = models.ForeignKey(
        SupplierPaymentRun,
        on_delete=models.CASCADE,
        related_name="bill_links",
    )
    bill = models.ForeignKey(
        PurchaseBill,
        on_delete=models.PROTECT,
        related_name="payment_run_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("payment_run", "bill"),
                name="unique_bill_per_supplier_payment_run",
            ),
        ]

    def __str__(self):
        return f"{self.payment_run.run_reference}: {self.bill.bill_number}"


class BankRule(models.Model):
    ACTION_SUGGEST_JOURNAL = "SuggestJournal"
    ACTION_NEEDS_REVIEW = "NeedsReview"
    ACTION_CHOICES = [
        (ACTION_SUGGEST_JOURNAL, "Suggest journal"),
        (ACTION_NEEDS_REVIEW, "Needs review"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="bank_rules")
    name = models.CharField(max_length=120)
    match_text = models.CharField(max_length=120)
    account_code = models.CharField(max_length=10)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, default=ACTION_SUGGEST_JOURNAL)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "name")

    def __str__(self):
        return f"{self.name} -> {self.account_code}"


class MonthEndClose(models.Model):
    STATUS_OPEN = "Open"
    STATUS_IN_REVIEW = "InReview"
    STATUS_CLOSED = "Closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_REVIEW, "In review"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="month_end_closes")
    period_start = models.DateField()
    period_end = models.DateField()
    bank_reconciled = models.BooleanField(default=False)
    accruals_posted = models.BooleanField(default=False)
    prepayments_posted = models.BooleanField(default=False)
    depreciation_posted = models.BooleanField(default=False)
    payroll_posted = models.BooleanField(default=False)
    payroll_not_applicable = models.BooleanField(default=False)
    review_signed_off = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    closed_by = models.CharField(max_length=100, blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "period_start", "period_end")

    @property
    def checklist_complete(self):
        return all(
            [
                self.bank_reconciled,
                self.accruals_posted,
                self.prepayments_posted,
                self.depreciation_posted,
                  self.payroll_posted or self.payroll_not_applicable,
                self.review_signed_off,
            ]
        )

    def __str__(self):
        return f"{self.tenant.name}: {self.period_start} to {self.period_end}"


class AccountingPeriodLock(models.Model):
    STATUS_LOCKED = "Locked"
    STATUS_REOPEN_REQUESTED = "ReopenRequested"
    STATUS_REOPENED = "Reopened"
    STATUS_CHOICES = [
        (STATUS_LOCKED, "Locked"),
        (STATUS_REOPEN_REQUESTED, "Reopen requested"),
        (STATUS_REOPENED, "Reopened"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="period_locks")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_LOCKED)
    locked_by = models.CharField(max_length=100)
    locked_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("tenant", "period_start", "period_end")

    def __str__(self):
        return f"{self.tenant.name}: {self.period_end} {self.status}"


class FixedAsset(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fixed_assets")
    asset_name = models.CharField(max_length=160)
    purchase_date = models.DateField()
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    accumulated_depreciation = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    depreciation_rate = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    status = models.CharField(max_length=20, default="Active")

    @property
    def net_book_value(self):
        return self.cost - self.accumulated_depreciation

    def __str__(self):
        return f"{self.asset_name} ({self.status})"


class PayrollSummary(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payroll_summaries")
    period_start = models.DateField()
    period_end = models.DateField()
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2)
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    employee_ni = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    employer_ni = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pension = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cis_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    journal_posted = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="Draft")

    class Meta:
        unique_together = ("tenant", "period_start", "period_end")

    def __str__(self):
        return f"{self.tenant.name}: payroll {self.period_start} to {self.period_end}"


class CorporationTaxEstimate(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="corporation_tax_estimates")
    period_start = models.DateField()
    period_end = models.DateField()
    accounting_profit = models.DecimalField(max_digits=12, decimal_places=2)
    disallowable_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    capital_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable_profit = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=25)
    estimated_tax = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="Draft")
    prepared_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.name}: CT estimate {self.period_end}"


class StatutoryAccountsDraft(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_INTERNAL_REVIEW = "InternalReview"
    STATUS_CLIENT_APPROVAL = "ClientApproval"
    STATUS_READY_FOR_FILING = "ReadyForFiling"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_INTERNAL_REVIEW, "Internal review"),
        (STATUS_CLIENT_APPROVAL, "Client approval"),
        (STATUS_READY_FOR_FILING, "Ready for filing"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="statutory_accounts_drafts")
    period_start = models.DateField()
    period_end = models.DateField()
    accounts_type = models.CharField(max_length=40, default="MicroEntity")
    directors_report_ready = models.BooleanField(default=False)
    balance_sheet_ready = models.BooleanField(default=False)
    notes_ready = models.BooleanField(default=False)
    ixbrl_ready = models.BooleanField(default=False)
    comparative_facts = models.JSONField(default=dict, blank=True)
    average_number_employees = models.PositiveIntegerField(default=0)
    approval_date = models.DateField(null=True, blank=True)
    approving_director_name = models.CharField(max_length=160, blank=True, default="")
    client_approved = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    review_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "period_start", "period_end", "accounts_type")

    @property
    def locally_complete(self):
        return all(
            [
                self.directors_report_ready,
                self.balance_sheet_ready,
                self.notes_ready,
                self.client_approved,
            ]
        )

    def __str__(self):
        return f"{self.tenant.name}: {self.accounts_type} accounts {self.period_end}"


class CompaniesHouseFilingSubmission(models.Model):
    STATUS_PREPARED = "Prepared"
    STATUS_SUBMITTED = "Submitted"
    STATUS_PENDING = "Pending"
    STATUS_ACCEPTED = "Accepted"
    STATUS_REJECTED = "Rejected"
    STATUS_FAILED = "Failed"
    STATUS_CHOICES = [
        (STATUS_PREPARED, "Prepared"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="companies_house_submissions")
    statutory_accounts = models.ForeignKey(
        StatutoryAccountsDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies_house_submissions",
    )
    # Each Companies House software product has a separate presenter account,
    # package reference and incremental submission-number sequence.
    product_key = models.CharField(max_length=80, default="ledgerhouse")
    submission_number = models.PositiveIntegerField()
    company_number = models.CharField(max_length=8)
    company_name = models.CharField(max_length=160)
    form_identifier = models.CharField(max_length=32, default="Accounts")
    package_reference = models.CharField(max_length=20)
    gateway_test = models.PositiveSmallIntegerField(default=1)
    company_authentication_hint = models.CharField(max_length=20, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PREPARED)
    request_xml_sanitised = models.TextField(blank=True, default="")
    response_xml = models.TextField(blank=True, default="")
    validation_messages = models.JSONField(default=list, blank=True)
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("product_key", "submission_number"),
                name="companies_house_submission_number_per_product",
            ),
        ]
        ordering = ("-submission_number", "-created_at")

    def __str__(self):
        return f"{self.company_number} submission {self.submission_number:06d} ({self.status})"


class CompaniesHouseSubmissionSequence(models.Model):
    """The sole allocator for a product's Companies House test numbers."""

    product_key = models.CharField(max_length=80, unique=True)
    last_submission_number = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product_key}: {self.last_submission_number:06d}"


class CompaniesHouseSubmissionPoll(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="companies_house_submission_polls")
    submission = models.ForeignKey(
        CompaniesHouseFilingSubmission,
        on_delete=models.CASCADE,
        related_name="poll_history",
    )
    submission_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=CompaniesHouseFilingSubmission.STATUS_CHOICES)
    response_xml = models.TextField(blank=True, default="")
    messages = models.JSONField(default=list, blank=True)
    polled_by = models.CharField(max_length=150, blank=True, default="")
    polled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-polled_at", "-id")

    def __str__(self):
        return f"{self.submission_number:06d} poll {self.status}"


class CompaniesHouseApprovalGate(models.Model):
    STATUS_BLOCKED = "Blocked"
    STATUS_READY = "Ready"
    STATUS_SIGNED_OFF = "SignedOff"
    STATUS_CHOICES = [
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_READY, "Ready"),
        (STATUS_SIGNED_OFF, "Signed off"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="companies_house_approval_gates")
    statutory_accounts = models.OneToOneField(
        StatutoryAccountsDraft,
        on_delete=models.CASCADE,
        related_name="companies_house_approval_gate",
    )
    client_approval = models.ForeignKey(
        "ClientApprovalRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies_house_approval_gates",
    )
    client_pack_reference = models.CharField(max_length=80, blank=True, default="")
    practice_signed_off = models.BooleanField(default=False)
    practice_signed_off_by = models.CharField(max_length=150, blank=True, default="")
    practice_signed_off_at = models.DateTimeField(null=True, blank=True)
    test_mode_only = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_BLOCKED)
    readiness_messages = models.JSONField(default=list, blank=True)
    production_lock_note = models.TextField(
        blank=True,
        default="Companies House filing remains locked to test mode until production approval and live settings are explicitly configured.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")

    def __str__(self):
        return f"{self.statutory_accounts} Companies House gate ({self.status})"


class ManagementPackSection(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_REVIEWED = "Reviewed"
    STATUS_RELEASED = "Released"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_RELEASED, "Released"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="management_pack_sections")
    section_name = models.CharField(max_length=120)
    period_end = models.DateField()
    commentary = models.TextField()
    owner = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "section_name", "period_end")

    def __str__(self):
        return f"{self.section_name} to {self.period_end} ({self.status})"


class ClientApprovalRecord(models.Model):
    TYPE_MANAGEMENT_PACK = "ManagementPack"
    TYPE_STATUTORY_ACCOUNTS = "StatutoryAccounts"
    TYPE_TAX_REVIEW = "TaxReview"
    TYPE_OTHER = "Other"
    TYPE_CHOICES = [
        (TYPE_MANAGEMENT_PACK, "Management pack"),
        (TYPE_STATUTORY_ACCOUNTS, "Statutory accounts"),
        (TYPE_TAX_REVIEW, "Tax review"),
        (TYPE_OTHER, "Other"),
    ]
    STATUS_PENDING = "Pending"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="approval_records")
    approval_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    reference = models.CharField(max_length=80)
    title = models.CharField(max_length=160)
    summary = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.CharField(max_length=100, blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.CharField(max_length=100, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")

    class Meta:
        unique_together = ("tenant", "approval_type", "reference")

    def __str__(self):
        return f"{self.title} ({self.status})"


class DocumentIntelligenceRule(models.Model):
    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="document_intelligence_rules")
    name = models.CharField(max_length=120)
    keyword = models.CharField(max_length=120)
    document_category = models.CharField(max_length=40, choices=EvidenceDocument.CATEGORY_CHOICES)
    suggested_account_code = models.CharField(max_length=10)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=75)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "name")

    def __str__(self):
        return f"{self.name}: {self.document_category}"


class AccountingTask(models.Model):
    PRIORITY_LOW = "Low"
    PRIORITY_NORMAL = "Normal"
    PRIORITY_HIGH = "High"
    STATUS_OPEN = "Open"
    STATUS_IN_PROGRESS = "InProgress"
    STATUS_DONE = "Done"

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="accounting_tasks")
    phase = models.CharField(max_length=80)
    title = models.CharField(max_length=160)
    owner = models.CharField(max_length=100, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, default=PRIORITY_NORMAL)
    status = models.CharField(max_length=20, default=STATUS_OPEN)
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.phase}: {self.title} ({self.status})"


class NotificationEvent(models.Model):
    CHANNEL_IN_APP = "InApp"
    CHANNEL_EMAIL_MOCK = "EmailMock"
    STATUS_QUEUED = "Queued"
    STATUS_RETRY_SCHEDULED = "RetryScheduled"
    STATUS_SENT = "Sent"
    STATUS_FAILED = "Failed"

    id = models.BigAutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="notification_events")
    channel = models.CharField(max_length=20, default=CHANNEL_IN_APP)
    recipient = models.CharField(max_length=160)
    subject = models.CharField(max_length=160)
    body = models.TextField()
    status = models.CharField(max_length=20, default=STATUS_QUEUED)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.channel}: {self.subject} ({self.status})"
