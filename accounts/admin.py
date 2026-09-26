from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from accounts.models import Client, TimeEntry, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "business_name", "hourly_rate", "created_at"]
    list_filter = ["is_staff", "is_active"]
    search_fields = ["username", "email", "business_name"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Freelancing", {"fields": ("business_name", "hourly_rate", "default_currency", "invoice_prefix")}),
    )
    readonly_fields = ["next_invoice_seq"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "owner", "status", "effective_rate", "is_active", "created_at"]
    list_filter = ["status", "is_active"]
    search_fields = ["name", "company", "email", "owner__username"]
    list_select_related = ["owner"]
    autocomplete_fields = ["owner"]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ["description", "client", "hours", "hourly_rate", "amount", "logged_on", "is_billed"]
    list_filter = ["is_billed", "logged_on"]
    search_fields = ["description", "client__name"]
    list_select_related = ["client", "project"]
    date_hierarchy = "logged_on"
