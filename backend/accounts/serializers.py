from rest_framework import serializers

from .models import AnnotatorProfile, Institution, UserProfile
from .roles import get_role


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = [
            "id",
            "name",
            "institution_type",
            "contact_email",
            "notes",
            "created_at",
        ]


class AnnotatorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnotatorProfile
        fields = [
            "is_active_annotator",
            "max_active_tasks",
            "pay_rate_per_task",
            "quality_score",
            "notes",
        ]


class CurrentUserSerializer(serializers.Serializer):
    """Serialized representation of the authenticated user for the frontend."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    is_superuser = serializers.BooleanField()
    role = serializers.SerializerMethodField()
    institution_name = serializers.SerializerMethodField()

    def get_role(self, user):
        return get_role(user)

    def get_institution_name(self, user):
        profile: UserProfile | None = getattr(user, "profile", None)
        if profile is None:
            return ""
        return profile.institution_name or (
            profile.institution.name if profile.institution else ""
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})
