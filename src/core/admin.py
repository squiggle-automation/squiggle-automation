from django.contrib import admin

from .models import (
    AutoApprovalRule,
    ConfigOption,
    ConfigValue,
    Container,
    Entity,
    EntityType,
    Event,
    Execution,
    ExecutionLog,
    Executor,
    Project,
    WorkerProfile,
)

admin.site.register(ConfigOption)


@admin.register(ConfigValue)
class ConfigValueAdmin(admin.ModelAdmin):
    def get_fields(self, request, obj=None):
        if obj is not None and obj.option.sensitive:
            return ["option", "executor", "masked_value"]
        return ["option", "executor", "value"]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.option.sensitive:
            return ["masked_value"]
        return []

    @admin.display(description="Value")
    def masked_value(self, obj):
        return "(sensitive value, hidden)"


admin.site.register(AutoApprovalRule)
admin.site.register(Container)
admin.site.register(Entity)
admin.site.register(EntityType)
admin.site.register(Event)
admin.site.register(Execution)
admin.site.register(ExecutionLog)
admin.site.register(Executor)
admin.site.register(Project)
admin.site.register(WorkerProfile)
