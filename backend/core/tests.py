import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from annotation.models import AnnotationTask
from core.dev_data import clear_dev_data, data_summary, seed_standard_data
from projects.models import Project

User = get_user_model()

_TMP_ROOT = tempfile.mkdtemp(prefix="mito_devcmd_test_")


@override_settings(MITO_DATA_ROOT=_TMP_ROOT, DEBUG=True)
class DevDataCommandTests(TestCase):
    def test_seed_creates_standard_dataset(self):
        seed_standard_data(log=lambda *a, **k: None)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Project.objects.first().dataset, "DemoCortex")
        self.assertTrue(User.objects.filter(username="lab_requester").exists())
        self.assertTrue(AnnotationTask.objects.filter(assigned_to__username="alice").exists())

    def test_clear_preserves_superusers(self):
        seed_standard_data(log=lambda *a, **k: None)
        User.objects.create_superuser("root", password="x")
        clear_dev_data(remove_files=True, log=lambda *a, **k: None)
        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(AnnotationTask.objects.count(), 0)
        # Superuser survives; seeded non-superusers are gone.
        self.assertTrue(User.objects.filter(username="root").exists())
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_seed_dev_and_status_commands_run(self):
        call_command("seed_dev", "--fresh", stdout=StringIO())
        out = StringIO()
        call_command("dev_status", stdout=out)
        self.assertIn("projects", out.getvalue())
        summary = data_summary()
        self.assertEqual(summary["projects"], 1)

    def test_clear_dev_data_command_no_input(self):
        seed_standard_data(log=lambda *a, **k: None)
        call_command("clear_dev_data", "--no-input", "--files", stdout=StringIO())
        self.assertEqual(Project.objects.count(), 0)
