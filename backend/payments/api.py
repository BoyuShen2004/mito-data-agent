from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsAnnotator, IsManager

from .models import PaymentRecord
from .serializers import PaymentRecordSerializer


class PaymentListView(generics.ListAPIView):
    """All payment records. Managers only."""

    serializer_class = PaymentRecordSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return PaymentRecord.objects.select_related(
            "annotator", "task", "task__project"
        ).all()


class MyPaymentsView(generics.ListAPIView):
    """Estimated payments for the logged-in annotator."""

    serializer_class = PaymentRecordSerializer
    permission_classes = [IsAnnotator]

    def get_queryset(self):
        return PaymentRecord.objects.filter(
            annotator=self.request.user
        ).select_related("task", "task__project")
