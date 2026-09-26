from django.contrib import admin

from invoices.models import Invoice, InvoiceLine, Payment


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    fields = ["description", "quantity", "unit_price", "position"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ["amount", "method", "reference", "received_on"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "client", "owner", "status", "total", "amount_paid", "balance_due", "due_on"]
    list_filter = ["status", "currency"]
    search_fields = ["number", "client__name", "owner__username"]
    list_select_related = ["client", "owner", "project"]
    autocomplete_fields = ["client", "owner"]
    readonly_fields = ["number", "subtotal", "tax_amount", "total", "amount_paid", "balance_due"]
    date_hierarchy = "issued_on"
    inlines = [InvoiceLineInline, PaymentInline]

    @admin.display(description="Balance due")
    def balance_due(self, obj):
        return obj.balance_due
