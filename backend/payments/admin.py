from django.contrib import admin

from .models import PaymentRecord


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "annotator", "task", "amount", "status", "created_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("annotator__username",)
