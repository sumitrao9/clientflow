from django.contrib import admin

from projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "client", "owner", "status", "budget", "earned", "budget_remaining", "due_on"]
    list_filter = ["status"]
    search_fields = ["name", "description", "client__name", "owner__username"]
    list_select_related = ["client", "owner"]
    autocomplete_fields = ["client", "owner"]
    readonly_fields = ["earned", "budget_remaining"]

    @admin.display(description="Earned")
    def earned(self, obj):
        return obj.earned

    @admin.display(description="Budget left")
    def budget_remaining(self, obj):
        return "n/a" if obj.budget_remaining is None else obj.budget_remaining
