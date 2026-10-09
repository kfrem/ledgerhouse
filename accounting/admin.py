from django.contrib import admin
from .models import (
    Tenant, TenantUserAccess, NominalAccount, AccountingPeriod, Journal, JournalLine,
    AuditEvent, VatRate, VatDecisionRule, ImportedFile, BankTransaction,
    EvidenceDocument, JournalEvidenceLink, BankReconciliation, VatReturn,
    HmrcVatConnection, HmrcServiceApproval, HmrcTaxProfile, HmrcFilingCase,
    VatReview, ClientRequest, BankFeedConnection,
    ClientInvitation, SubscriptionPlan, SalesInvoice, PurchaseBill,
    CreditControlAction, SupplierPaymentRun, MonthEndClose, FixedAsset,
    PayrollSummary, CorporationTaxEstimate, StatutoryAccountsDraft,
    CompaniesHouseApprovalGate, CompaniesHouseFilingSubmission,
    CompaniesHouseSubmissionPoll, AccountingTask, NotificationEvent,
)

admin.site.site_header = "LedgerHouse Operations"
admin.site.site_title = "LedgerHouse"
admin.site.index_title = "Accounting control room"

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)

@admin.register(TenantUserAccess)
class TenantUserAccessAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'user', 'role', 'is_active', 'created_at')
    list_filter = ('tenant', 'role', 'is_active')
    search_fields = ('tenant__name', 'user__username', 'user__email')

@admin.register(NominalAccount)
class NominalAccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'tenant', 'name', 'category', 'canonical_taxonomy')
    list_filter = ('category', 'tenant')
    search_fields = ('code', 'name')

@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'start_date', 'end_date', 'is_closed')
    list_filter = ('is_closed', 'tenant')

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0

@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'date', 'source_type', 'source_id', 'status', 'description')
    list_filter = ('source_type', 'status', 'tenant')
    search_fields = ('description', 'source_id')
    inlines = [JournalLineInline]

@admin.register(JournalLine)
class JournalLineAdmin(admin.ModelAdmin):
    list_display = ('id', 'journal', 'account', 'debit', 'credit', 'vat_code')
    list_filter = ('account__category', 'journal__tenant')

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'timestamp', 'event_type', 'username', 'description')
    list_filter = ('event_type', 'tenant')
    readonly_fields = ('tenant', 'timestamp', 'event_type', 'username', 'description', 'details')

@admin.register(VatRate)
class VatRateAdmin(admin.ModelAdmin):
    list_display = ('vat_code', 'tenant', 'rate', 'effective_from', 'effective_to')
    list_filter = ('vat_code', 'tenant')

@admin.register(VatDecisionRule)
class VatDecisionRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'priority', 'supplier_name_pattern', 'account_code_pattern', 'vat_code')
    list_filter = ('vat_code', 'tenant')

@admin.register(ImportedFile)
class ImportedFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'filename', 'uploaded_at', 'file_hash')
    list_filter = ('tenant',)

@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'date', 'amount', 'reference', 'fitid', 'review_status', 'reviewed_by')
    list_filter = ('tenant', 'review_status')
    search_fields = ('reference', 'fitid')

@admin.register(EvidenceDocument)
class EvidenceDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'filename', 'document_category', 'gross_amount', 'content_type', 'uploaded_at', 'uploaded_by', 'review_status', 'reviewed_by')
    list_filter = ('tenant', 'review_status', 'document_category')
    search_fields = ('filename', 'supplier_or_customer', 'review_note')

@admin.register(JournalEvidenceLink)
class JournalEvidenceLinkAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'journal', 'document', 'linked_at', 'linked_by')
    list_filter = ('tenant',)

@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'bank_transaction', 'matched_journal', 'reconciled_at', 'reconciled_by')
    list_filter = ('tenant',)

@admin.register(VatReturn)
class VatReturnAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'start_date', 'end_date', 'total_output_vat', 'total_input_vat', 'net_vat_payable', 'status', 'hmrc_receipt_id', 'submitted_at', 'locked_at')
    list_filter = ('tenant', 'status')

@admin.register(HmrcVatConnection)
class HmrcVatConnectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'vrn', 'status', 'scope', 'last_authorised_at', 'last_obligations_sync_at')
    list_filter = ('tenant', 'status')
    readonly_fields = ('created_at', 'updated_at')
    search_fields = ('tenant__name', 'vrn')


@admin.register(HmrcServiceApproval)
class HmrcServiceApprovalAdmin(admin.ModelAdmin):
    list_display = ('service', 'transport', 'status', 'credentials_requested_at', 'approved_at', 'credentials_verified_at', 'live_submission_enabled')
    list_filter = ('transport', 'status', 'live_submission_enabled')
    search_fields = ('service', 'application_name', 'review_note')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(HmrcTaxProfile)
class HmrcTaxProfileAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'masked_ct_utr', 'masked_paye_reference', 'masked_sa_utr', 'updated_at')
    search_fields = ('tenant__name',)
    readonly_fields = ('updated_at',)

    @admin.display(description='Corporation Tax UTR')
    def masked_ct_utr(self, obj):
        return obj.masked(obj.corporation_tax_utr)

    @admin.display(description='PAYE reference')
    def masked_paye_reference(self, obj):
        return obj.masked(obj.paye_reference)

    @admin.display(description='Self Assessment UTR')
    def masked_sa_utr(self, obj):
        return obj.masked(obj.self_assessment_utr)


@admin.register(HmrcFilingCase)
class HmrcFilingCaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'service', 'filing_type', 'period_start', 'period_end', 'status', 'updated_at')
    list_filter = ('tenant', 'service', 'filing_type', 'status')
    search_fields = ('tenant__name', 'filing_type', 'client_approved_by', 'practice_approved_by')
    readonly_fields = (
        'encrypted_payload', 'validation_errors', 'validation_warnings',
        'provider_correlation_id', 'provider_receipt_id', 'provider_response',
        'idempotency_key', 'submitted_at', 'decided_at', 'created_at', 'updated_at',
    )

@admin.register(VatReview)
class VatReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'period_key', 'start_date', 'end_date', 'status', 'client_approved', 'hmrc_receipt_id')
    list_filter = ('tenant', 'status', 'client_approved')
    readonly_fields = ('created_at', 'updated_at')
    search_fields = ('tenant__name', 'period_key', 'hmrc_receipt_id')

@admin.register(ClientRequest)
class ClientRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'subject', 'category', 'priority', 'status', 'submitted_by', 'submitted_at')
    list_filter = ('tenant', 'category', 'priority', 'status')
    readonly_fields = ('submitted_at', 'updated_at')
    search_fields = ('tenant__name', 'subject', 'message', 'submitted_by')

@admin.register(BankFeedConnection)
class BankFeedConnectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'bank_name', 'account_identifier', 'status', 'connected_at', 'last_sync_at', 'expires_at')
    list_filter = ('tenant', 'status', 'bank_name')

@admin.register(ClientInvitation)
class ClientInvitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'email', 'role', 'status', 'invited_by', 'invited_at', 'accepted_by')
    list_filter = ('tenant', 'role', 'status')
    search_fields = ('tenant__name', 'email', 'accepted_by')
    readonly_fields = ('id', 'invited_at', 'accepted_at')

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'plan_name', 'status', 'monthly_price', 'currency', 'billing_provider', 'collection_method', 'latest_invoice_status', 'updated_at')
    list_filter = ('status', 'currency', 'billing_provider', 'collection_method', 'latest_invoice_status')
    search_fields = ('tenant__name', 'plan_name', 'billing_note', 'provider_customer_id', 'provider_subscription_id')


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'invoice_number', 'customer_name', 'due_date', 'gross_amount', 'paid_amount', 'status')
    list_filter = ('tenant', 'status')
    search_fields = ('invoice_number', 'customer_name', 'notes')


@admin.register(PurchaseBill)
class PurchaseBillAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'bill_number', 'supplier_name', 'due_date', 'gross_amount', 'paid_amount', 'status')
    list_filter = ('tenant', 'status')
    search_fields = ('bill_number', 'supplier_name', 'approval_note')


@admin.register(CreditControlAction)
class CreditControlActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'sales_invoice', 'action_type', 'action_date', 'owner', 'resolved')
    list_filter = ('tenant', 'action_type', 'resolved')


@admin.register(SupplierPaymentRun)
class SupplierPaymentRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'run_reference', 'scheduled_date', 'total_amount', 'status', 'approved_by')
    list_filter = ('tenant', 'status')


@admin.register(MonthEndClose)
class MonthEndCloseAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'period_start', 'period_end', 'status', 'review_signed_off', 'closed_by')
    list_filter = ('tenant', 'status', 'review_signed_off')


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'asset_name', 'purchase_date', 'cost', 'accumulated_depreciation', 'status')
    list_filter = ('tenant', 'status')


@admin.register(PayrollSummary)
class PayrollSummaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'period_start', 'period_end', 'gross_pay', 'paye', 'journal_posted', 'status')
    list_filter = ('tenant', 'status', 'journal_posted')


@admin.register(CorporationTaxEstimate)
class CorporationTaxEstimateAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'period_start', 'period_end', 'taxable_profit', 'estimated_tax', 'status')
    list_filter = ('tenant', 'status')


@admin.register(StatutoryAccountsDraft)
class StatutoryAccountsDraftAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'period_start', 'period_end', 'accounts_type', 'status', 'client_approved', 'ixbrl_ready')
    list_filter = ('tenant', 'accounts_type', 'status', 'client_approved', 'ixbrl_ready')


@admin.register(CompaniesHouseFilingSubmission)
class CompaniesHouseFilingSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'submission_number', 'company_number', 'status', 'gateway_test', 'created_at')
    list_filter = ('tenant', 'status', 'gateway_test')
    search_fields = ('company_number', 'company_name', 'submission_number')
    readonly_fields = ('request_xml_sanitised', 'response_xml', 'validation_messages')


@admin.register(CompaniesHouseSubmissionPoll)
class CompaniesHouseSubmissionPollAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'submission_number', 'status', 'polled_by', 'polled_at')
    list_filter = ('tenant', 'status')
    search_fields = ('submission_number', 'polled_by')
    readonly_fields = ('response_xml', 'messages', 'polled_at')


@admin.register(CompaniesHouseApprovalGate)
class CompaniesHouseApprovalGateAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'statutory_accounts', 'status', 'practice_signed_off', 'test_mode_only', 'updated_at')
    list_filter = ('tenant', 'status', 'practice_signed_off', 'test_mode_only')
    search_fields = ('tenant__name', 'client_pack_reference', 'practice_signed_off_by')
    readonly_fields = ('readiness_messages', 'production_lock_note', 'created_at', 'updated_at')


@admin.register(AccountingTask)
class AccountingTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'phase', 'title', 'owner', 'priority', 'status', 'due_date')
    list_filter = ('tenant', 'phase', 'priority', 'status')
    search_fields = ('title', 'detail', 'owner')


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'channel', 'recipient', 'subject', 'status', 'attempt_count', 'next_attempt_at', 'created_at')
    list_filter = ('tenant', 'channel', 'status')
    search_fields = ('recipient', 'subject', 'body')
