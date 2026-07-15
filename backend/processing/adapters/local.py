"""Local / mock processing backend.

Used for development and tests. It does not run heavy scientific work: a job is
"submitted" and immediately reported as succeeded, writing a small marker output
under the shared storage root so downstream lifecycle callbacks have something
to react to. This keeps the dispatcher fully exercisable without a cluster.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from core.choices import ProcessingJobStatus
from ..interfaces import JobResult, ProcessingBackend


class LocalProcessingBackend(ProcessingBackend):
    name = "local"

    def submit(self, job) -> JobResult:
        # Simulate an instantaneous, successful run and record a marker output.
        output_dir = self._job_dir(job)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            marker = output_dir / "result.json"
            marker.write_text(
                f'{{"job": {job.id}, "type": "{job.job_type}", "backend": "local"}}'
            )
            output_paths = {"result": str(marker)}
            log_path = str(output_dir / "job.log")
            Path(log_path).write_text(f"local job {job.id} {job.job_type} ok\n")
        except OSError as exc:  # storage not writable -> fail cleanly
            return JobResult(
                status=ProcessingJobStatus.FAILED,
                error_message=f"Local backend could not write outputs: {exc}",
            )
        return JobResult(
            status=ProcessingJobStatus.SUCCEEDED,
            external_job_id=f"local-{job.id}",
            output_paths=output_paths,
            log_path=log_path,
            detail="Local mock run completed.",
        )

    def poll(self, job) -> JobResult:
        # Local jobs finish on submit, so polling just echoes the current state.
        return JobResult(status=job.status, external_job_id=job.external_job_id)

    def cancel(self, job) -> JobResult:
        return JobResult(
            status=ProcessingJobStatus.CANCELLED,
            external_job_id=job.external_job_id,
            detail="Local job cancelled.",
        )

    @staticmethod
    def _job_dir(job) -> Path:
        root = Path(getattr(settings, "MITO_SHARED_STORAGE_ROOT", settings.MITO_DATA_ROOT))
        return root / "processing_jobs" / str(job.id)
