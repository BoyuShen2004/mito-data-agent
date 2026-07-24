import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from rest_framework.test import APIRequestFactory

from accounts.models import AnnotatorProfile
from annotation.models import AnnotationTask
from core.choices import UserRole
from core.dev_api import DevResetView
from core.dev_data import STANDARD_ACCOUNTS, clear_dev_data, data_summary, seed_standard_data
from projects.models import Project

User = get_user_model()

# clear_dev_data() wipes everything under MITO_DATA_ROOT (see dev_data.py) —
# without overriding it to a throwaway tempdir here, these tests would wipe
# the *real* dev data/ directory every time the suite runs. Same pattern as
# annotation/tests.py and friends.
_TMP_ROOT = tempfile.mkdtemp(prefix="mito_devdata_test_")


@override_settings(DEBUG=True, MITO_DATA_ROOT=_TMP_ROOT)
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

    def test_clear_wipes_working_copy_files_not_just_filefields(self):
        """Regression test for a real bug: the in-app editor's working label
        copies (annotation/label_paths.py) are written directly by path, not
        through a Django FileField, so a per-FileField .delete() loop alone
        (the old implementation) never touched them — "Clear all data &
        reset" left them orphaned on disk. See
        progress/history/17-fix-dev-reset-orphaned-files.md.
        """
        import os

        # Stand in for a working-copy file (and an uploaded-file-style path)
        # written directly under MITO_DATA_ROOT, exactly as the app would —
        # not going through any model/FileField.
        working_copy = os.path.join(_TMP_ROOT, "some-project", "some-dataset", "volume_1_labels.tif")
        os.makedirs(os.path.dirname(working_copy), exist_ok=True)
        with open(working_copy, "wb") as f:
            f.write(b"fake tif bytes")

        clear_dev_data(log=lambda *a, **k: None)

        self.assertFalse(os.path.exists(working_copy))
        self.assertFalse(os.path.exists(os.path.join(_TMP_ROOT, "some-project")))

    def test_commands_run(self):
        call_command("seed_dev", "--fresh", stdout=StringIO())
        out = StringIO()
        call_command("dev_status", stdout=out)
        self.assertIn("projects", out.getvalue())
        self.assertEqual(data_summary()["projects"], 0)
        self.assertEqual(data_summary()["annotators"], 4)

        call_command("clear_dev_data", "--no-input", stdout=StringIO())
        self.assertEqual(data_summary()["annotators"], 0)


class DevResetApiTests(TestCase):
    """The endpoint behind the login page's "Clear all data & reset" button.

    The route itself is only registered when DEBUG is on, so these drive the
    view directly rather than going through the (production) URLconf.
    """

    def _post(self):
        request = APIRequestFactory().post("/api/dev/reset/")
        return DevResetView.as_view()(request)

    @override_settings(DEBUG=True, MITO_DATA_ROOT=_TMP_ROOT)
    def test_reset_clears_data_and_reseeds_accounts(self):
        seed_standard_data(log=lambda *a, **k: None)
        Project.objects.create(title="manual", dataset="manual")
        User.objects.create_user(username="registered-by-hand")

        response = self._post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted"]["projects"], 1)
        # Data is gone, but the dev chips on the login page still work.
        self.assertEqual(Project.objects.count(), 0)
        self.assertFalse(User.objects.filter(username="registered-by-hand").exists())
        for name in STANDARD_ACCOUNTS:
            self.assertTrue(User.objects.filter(username=name).exists())
        self.assertEqual(response.data["summary"]["annotators"], 4)

    @override_settings(DEBUG=False)
    def test_reset_refuses_outside_debug(self):
        Project.objects.create(title="keep me", dataset="real")

        response = self._post()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Project.objects.count(), 1)
