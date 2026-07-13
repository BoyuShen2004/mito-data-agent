from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import AnnotatorProfile
from annotation.models import AnnotationTask
from core.choices import UserRole
from core.dev_data import STANDARD_ACCOUNTS, clear_dev_data, data_summary, seed_standard_data
from projects.models import Project

User = get_user_model()


@override_settings(DEBUG=True)
class DevDataCommandTests(TestCase):
    def test_seed_creates_accounts_only(self):
        seed_standard_data(log=lambda *a, **k: None)

        # One manager (superuser) + four annotators, and no pre-registered data.
        self.assertTrue(User.objects.get(username="manager").is_superuser)
        annotators = [
            n for n, r in STANDARD_ACCOUNTS.items() if r == UserRole.ANNOTATOR
        ]
        self.assertEqual(len(annotators), 4)
        for name in annotators:
            user = User.objects.get(username=name)
            self.assertFalse(user.is_superuser)
            self.assertTrue(AnnotatorProfile.objects.filter(user=user).exists())

        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(AnnotationTask.objects.count(), 0)

    def test_clear_preserves_superusers(self):
        seed_standard_data(log=lambda *a, **k: None)
        # Simulate data a developer registered manually.
        Project.objects.create(title="manual", dataset="manual")

        clear_dev_data(log=lambda *a, **k: None)

        self.assertEqual(Project.objects.count(), 0)
        # Superuser manager survives; non-superuser annotators are removed.
        self.assertTrue(User.objects.filter(username="manager").exists())
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_clear_keep_users(self):
        seed_standard_data(log=lambda *a, **k: None)
        clear_dev_data(keep_users=True, log=lambda *a, **k: None)
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_commands_run(self):
        call_command("seed_dev", "--fresh", stdout=StringIO())
        out = StringIO()
        call_command("dev_status", stdout=out)
        self.assertIn("projects", out.getvalue())
        self.assertEqual(data_summary()["projects"], 0)
        self.assertEqual(data_summary()["annotators"], 4)

        call_command("clear_dev_data", "--no-input", stdout=StringIO())
        self.assertEqual(data_summary()["annotators"], 0)
