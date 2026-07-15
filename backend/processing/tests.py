"""Tests for the ProcessingJob foundation: creation, local adapter, dispatch."""

import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.choices import ProcessingJobStatus, ProcessingJobType
from processing.models import ProcessingJob
from processing.registry import get_processing_backend
from processing.services import (
    claim_next_queued_job,
    create_processing_job,
    dispatch_job,
    retry_job,
    run_dispatch_once,
)

_TMP_ROOT = tempfile.mkdtemp(prefix="mito-processing-test-")

User = get_user_model()


@override_settings(
    MITO_SHARED_STORAGE_ROOT=_TMP_ROOT, MITO_PROCESSING_BACKEND="local"
)
class ProcessingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("mgr", password="x")

    def test_create_job_is_queued(self):
        job = create_processing_job(
            job_type=ProcessingJobType.INGEST, created_by=self.user
        )
        self.assertEqual(job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(job.backend, "local")

    def test_unknown_job_type_rejected(self):
        with self.assertRaises(ValueError):
            create_processing_job(job_type="not_a_type")

    def test_provider_selection(self):
        self.assertEqual(get_processing_backend().name, "local")
        self.assertEqual(get_processing_backend("slurm").name, "slurm")
        with self.assertRaises(ValueError):
            get_processing_backend("nope")

    def test_local_dispatch_succeeds(self):
        job = create_processing_job(job_type=ProcessingJobType.PREDICT)
        claimed = claim_next_queued_job()
        self.assertEqual(claimed.id, job.id)
        self.assertEqual(claimed.status, ProcessingJobStatus.SUBMITTED)
        dispatch_job(claimed)
        claimed.refresh_from_db()
        self.assertEqual(claimed.status, ProcessingJobStatus.SUCCEEDED)
        self.assertTrue(claimed.external_job_id)
        self.assertIn("result", claimed.output_paths)
        self.assertIsNotNone(claimed.finished_at)

    def test_run_dispatch_once(self):
        for _ in range(3):
            create_processing_job(job_type=ProcessingJobType.INSPECT)
        summary = run_dispatch_once()
        self.assertEqual(summary["submitted"], 3)
        self.assertEqual(
            ProcessingJob.objects.filter(
                status=ProcessingJobStatus.SUCCEEDED
            ).count(),
            3,
        )

    def test_claim_returns_none_when_empty(self):
        self.assertIsNone(claim_next_queued_job())

    def test_retry_requeues_terminal_job(self):
        job = create_processing_job(job_type=ProcessingJobType.INGEST)
        job.status = ProcessingJobStatus.FAILED
        job.error_message = "boom"
        job.save(update_fields=["status", "error_message"])
        retry_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingJobStatus.QUEUED)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.error_message, "")

    def test_retry_rejects_non_terminal(self):
        job = create_processing_job(job_type=ProcessingJobType.INGEST)
        with self.assertRaises(ValueError):
            retry_job(job)
