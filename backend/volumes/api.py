from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from annotation.serializers import AnnotationTaskSerializer
from core.permissions import IsManager
from projects.models import Project

from .models import Volume
from .serializers import VolumeSerializer, VolumeSplitSerializer
from .services import create_tasks_from_volume, register_volume, update_volume_metadata


class ProjectVolumesView(generics.ListCreateAPIView):
    """List volumes for a project, or register/upload a new one. Managers only."""

    serializer_class = VolumeSerializer
    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    def get_project(self) -> Project:
        return get_object_or_404(Project, pk=self.kwargs["project_id"])

    def get_queryset(self):
        return Volume.objects.filter(project_id=self.kwargs["project_id"])

    def create(self, request, *args, **kwargs):
        project = self.get_project()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        voxel_size = None
        if data.get("voxel_size_z") is not None:
            voxel_size = (
                data.get("voxel_size_z"),
                data.get("voxel_size_y"),
                data.get("voxel_size_x"),
            )
        volume = register_volume(
            project=project,
            name=data["name"],
            image_path=data.get("image_path", ""),
            image_file=data.get("image_file"),
            label_path=data.get("label_path", ""),
            label_file=data.get("label_file"),
            label_type=data.get("label_type", "none"),
            file_format=data.get("file_format"),
            voxel_size=voxel_size,
            metadata=data.get("metadata"),
        )
        out = VolumeSerializer(volume, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)


class VolumeDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or edit a volume's metadata. Managers only."""

    queryset = Volume.objects.all()
    serializer_class = VolumeSerializer
    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    def update(self, request, *args, **kwargs):
        volume = self.get_object()
        serializer = self.get_serializer(volume, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_volume_metadata(volume, **serializer.validated_data)
        volume.refresh_from_db()
        return Response(VolumeSerializer(volume).data)


class VolumeSplitView(APIView):
    """Split a volume into frame-based tasks. Managers only."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        volume = get_object_or_404(Volume, pk=pk)
        serializer = VolumeSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        z_step = data.get("z_step") or settings.MITO_DEFAULT_Z_STEP
        try:
            tasks = create_tasks_from_volume(
                volume,
                z_step=z_step,
                payment_amount=data.get("payment_amount", 0),
                task_type=data.get("task_type") or None,
                priority=data.get("priority", 0),
                instructions=data.get("instructions", ""),
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {
                "created": len(tasks),
                "tasks": AnnotationTaskSerializer(tasks, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )
