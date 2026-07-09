from django.conf import settings
from django.db import models

from core.choices import PaymentStatus


class PaymentRecord(models.Model):
    """Estimated payment owed to an annotator for a completed task.

    MVP is estimate-only: no real payment processing is performed.
    """

    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_records",
    )
    task = models.OneToOneField(
        "annotation.AnnotationTask",
        on_delete=models.CASCADE,
        related_name="payment_record",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payment {self.amount} -> {self.annotator.get_username()}"
