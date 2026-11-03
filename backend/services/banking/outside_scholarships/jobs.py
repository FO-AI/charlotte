"""In-memory outside-scholarship upload jobs.

Azure App Service closes HTTP requests that stay open around 240 seconds.
Upload plus vision extraction of a large scanned check batch often exceeds
that if they share one request; the browser then reports a dropped connection.
Accept the PDF, return a job id, and finish extraction after the response so
the request only has to last as long as the upload.

Jobs live in this process. Charlotte runs one App Service backend instance, so
that is enough to beat the request timeout. Recycles still lose in-flight jobs;
Always On should stay enabled so idle unload does not drop a running batch.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional

STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"

STAGE_STARTING = "starting"
STAGE_CLASSIFYING = "classifying_pages"
STAGE_EXTRACTING = "extracting_checks"
STAGE_LOOKUP = "looking_up_names"

# One cashier is the usual case; a second slot covers a retry while the first
# job is finishing. More than this on a Basic B2 risks OOM during vision work.
MAX_PROCESSING_JOBS = 2
JOB_TTL_SECONDS = 30 * 60

_PROGRESS_KEYS = (
    "stage",
    "message",
    "pages_total",
    "pages_classified",
    "checks_total",
    "checks_done",
)

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def job_owner(user: Dict[str, Any]) -> str:
    return str(user.get("id") or user.get("oid") or user.get("email") or "unknown")


def reset_jobs() -> None:
    with _LOCK:
        _JOBS.clear()


def processing_count() -> int:
    with _LOCK:
        _prune_locked()
        return sum(1 for job in _JOBS.values() if job["status"] == STATUS_PROCESSING)


def can_accept_job() -> bool:
    return processing_count() < MAX_PROCESSING_JOBS


def create_job(owner: str) -> str:
    job_id = str(uuid.uuid4())
    with _LOCK:
        _prune_locked()
        _JOBS[job_id] = {
            "id": job_id,
            "owner": owner,
            "status": STATUS_PROCESSING,
            "created_at": time.time(),
            "preview": None,
            "detail": None,
            "status_code": None,
            "stage": STAGE_STARTING,
            "message": "Upload accepted. Starting extraction…",
            "pages_total": None,
            "pages_classified": None,
            "checks_total": None,
            "checks_done": None,
        }
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        _prune_locked()
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def processing_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """Public poll body while extraction is still running."""
    snapshot: Dict[str, Any] = {
        "job_id": job["id"],
        "status": STATUS_PROCESSING,
    }
    for key in _PROGRESS_KEYS:
        value = job.get(key)
        if value is not None:
            snapshot[key] = value
    return snapshot


def update_job_progress(job_id: str, **fields: Any) -> None:
    """Merge progress fields into a processing job. Unknown keys are ignored."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["status"] != STATUS_PROCESSING:
            return
        for key, value in fields.items():
            if key in _PROGRESS_KEYS:
                job[key] = value


def mark_check_done(job_id: str) -> None:
    """Increment checks_done after one parallel extract worker finishes."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job["status"] != STATUS_PROCESSING:
            return
        total = job.get("checks_total")
        done = int(job.get("checks_done") or 0) + 1
        if isinstance(total, int) and total > 0:
            done = min(done, total)
        job["checks_done"] = done
        job["stage"] = STAGE_EXTRACTING
        if isinstance(total, int) and total > 0:
            job["message"] = f"Reading check {done} of {total}…"
        else:
            job["message"] = f"Reading check {done}…"


def complete_job(job_id: str, preview: Dict[str, Any]) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["status"] = STATUS_COMPLETE
        job["preview"] = preview
        job["finished_at"] = time.time()
        job["message"] = "Preview ready"


def fail_job(job_id: str, detail: Any, status_code: int) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["status"] = STATUS_ERROR
        job["detail"] = detail
        job["status_code"] = status_code
        job["finished_at"] = time.time()


def _prune_locked() -> None:
    now = time.time()
    expired = [
        job_id
        for job_id, job in _JOBS.items()
        if now - job["created_at"] >= JOB_TTL_SECONDS
    ]
    for job_id in expired:
        del _JOBS[job_id]
