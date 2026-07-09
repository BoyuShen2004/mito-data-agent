"""Deterministic service functions for estimated payment tracking."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum

from core.choices import PaymentStatus

from .models import PaymentRecord


def ensure_payment_record(task) -> PaymentRecord:
    """Create or update the payment record for an approved task.

    Amount comes from ``task.payment_amount``; falls back to the annotator's
    ``pay_rate_per_task`` when the task amount is zero.
    """
    amount = task.payment_amount or Decimal("0")
    if not amount:
        profile = getattr(task.assigned_to, "annotator_profile", None)
        if profile is not None:
            amount = profile.pay_rate_per_task

    record, _created = PaymentRecord.objects.update_or_create(
        task=task,
        defaults={
            "annotator": task.assigned_to,
            "amount": amount,
            "status": PaymentStatus.APPROVED,
        },
    )
    return record


def calculate_payment_summary(annotator=None, project=None) -> dict:
    """Totals of estimated payments grouped by status, optionally filtered."""
    qs = PaymentRecord.objects.all()
    if annotator is not None:
        qs = qs.filter(annotator=annotator)
    if project is not None:
        qs = qs.filter(task__project=project)

    by_status = {status.value: {"count": 0, "amount": Decimal("0")} for status in PaymentStatus}
    for row in qs.values("status").annotate(count=Count("id"), amount=Sum("amount")):
        by_status[row["status"]] = {
            "count": row["count"],
            "amount": row["amount"] or Decimal("0"),
        }

    total_amount = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "total_records": qs.count(),
        "total_amount": total_amount,
        "by_status": by_status,
    }


def payment_summary_by_annotator(project=None) -> list[dict]:
    """Estimated payment totals per annotator."""
    qs = PaymentRecord.objects.all()
    if project is not None:
        qs = qs.filter(task__project=project)
    rows = (
        qs.values("annotator", "annotator__username")
        .annotate(count=Count("id"), amount=Sum("amount"))
        .order_by("annotator__username")
    )
    return [
        {
            "annotator_id": r["annotator"],
            "username": r["annotator__username"],
            "count": r["count"],
            "amount": r["amount"] or Decimal("0"),
        }
        for r in rows
    ]
