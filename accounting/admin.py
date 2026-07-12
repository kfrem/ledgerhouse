from django.contrib import admin
from .models import (
    Tenant, NominalAccount, AccountingPeriod, Journal, JournalLine,
    AuditEvent, VatRate, VatDecisionRule, ImportedFile, BankTransaction,
    EvidenceDocument, JournalEvidenceLink, BankReconciliation, VatReturn,
    HmrcVatConnection, BankFeedConnection
)

admin.site.site_header = "LedgerHouse Operations"
admin.site.site_title = "LedgerHouse"
admin.site.index_title = "Accounting control room"

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)

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
    list_display = ('id', 'tenant', 'date', 'amount', 'reference', 'fitid')
    list_filter = ('tenant',)
    search_fields = ('reference', 'fitid')

@admin.register(EvidenceDocument)
class EvidenceDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'filename', 'content_type', 'uploaded_at', 'uploaded_by')
    list_filter = ('tenant',)

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

@admin.register(BankFeedConnection)
class BankFeedConnectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'tenant', 'bank_name', 'account_identifier', 'status', 'connected_at', 'last_sync_at', 'expires_at')
    list_filter = ('tenant', 'status', 'bank_name')
