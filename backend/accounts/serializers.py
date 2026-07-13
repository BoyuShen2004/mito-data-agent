from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from core.choices import UserRole

from .models import AnnotatorProfile, Institution, UserProfile
from .roles import get_role

User = get_user_model()


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
    # Which login tab was used: "requester" or "annotator". Managers use the
    # annotator tab. Optional; when provided the role is validated against it.
    portal = serializers.ChoiceField(
        choices=["requester", "annotator"], required=False, allow_blank=True
    )


# Roles a member of the public may self-register as. Managers are provisioned
# by administrators only; there is no public manager registration.
PUBLIC_ROLES = (UserRole.ANNOTATOR, UserRole.REQUESTER)


class RegisterSerializer(serializers.Serializer):
    """Public account creation for annotators and requesters."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        style={"input_type": "password"}, write_only=True
    )
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=[r.value for r in PUBLIC_ROLES])
    institution_name = serializers.CharField(
        required=False, allow_blank=True, default=""
    )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        # ``ensure_user_profile`` created a default profile via post_save; set
        # the chosen role on that same (cached) instance so ``user.profile``
        # reflects the update immediately.
        profile = getattr(user, "profile", None) or UserProfile.objects.create(
            user=user
        )
        profile.role = validated_data["role"]
        profile.institution_name = validated_data.get("institution_name", "")
        profile.save(update_fields=["role", "institution_name"])

        if validated_data["role"] == UserRole.ANNOTATOR:
            AnnotatorProfile.objects.get_or_create(user=user)
        return user
