from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, HTTPException, Form, Body
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional
from utils.auth import get_bearer_token
from utils.rba import check_banking_or_admin_permissions
from config import get_logger
from services.banking import BankingUploadService
from services.azure_services import AzureClient, GraphUserDirectory
from api.dependencies import get_azure_client, get_graph_user_directory
from services.banking import OutsideScholarshipService
from services.banking.outside_scholarships.jobs import (
    STATUS_ERROR,
    STATUS_PROCESSING,
    can_accept_job,
    complete_job,
    create_job,
    fail_job,
    get_job,
    job_owner,
)
from services.data_loaders.outside_scholarships_json_to_excel import (
    ALLOWED_AID_TERMS,
    DEFAULT_AID_TERM,
)

logger = get_logger(__name__)
router = APIRouter(tags=["banking"])


@router.post("/api/banking/upload-files")
async def upload_banking_files(
    files: List[UploadFile] = File(...),
    user: Dict = Depends(check_banking_or_admin_permissions),
    azure_client: AzureClient = Depends(get_azure_client),
):
    """Upload banking files and return a consolidated Excel download."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    upload_service = BankingUploadService(azure_client)
    return await upload_service.upload_and_analyze_files(files)


async def _run_outside_scholarships_job(
    job_id: str,
    service: OutsideScholarshipService,
    pdf_bytes: bytes,
    filename: str,
    graph_access_token: str,
    aid_year: Optional[str],
    aid_term: str,
) -> None:
    try:
        preview = await service.analyze_pdf_bytes(
            pdf_bytes,
            filename,
            graph_access_token,
            aid_year=aid_year,
            aid_term=aid_term,
        )
        complete_job(job_id, preview)
    except HTTPException as exc:
        fail_job(job_id, exc.detail, exc.status_code)
    except Exception:
        logger.exception("outside_scholarships.job: extraction failed job_id=%s", job_id)
        fail_job(job_id, "Failed to process outside scholarship PDF.", 500)


@router.post("/api/banking/outside-scholarships")
async def outside_scholarships(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    aid_year: Optional[str] = Form(None),
    aid_term: str = Form("F"),
    user: Dict = Depends(check_banking_or_admin_permissions),
    azure_client: AzureClient = Depends(get_azure_client),
    user_directory: GraphUserDirectory = Depends(get_graph_user_directory),
    graph_access_token: str = Depends(get_bearer_token),
):
    """Accept a check-batch PDF and return a job id. Poll GET .../jobs/{id} for the preview.

    Azure App Service closes requests around 240s. Extraction of a large scanned
    batch often exceeds that if it runs inside this POST, so work continues after
    the upload response.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    if len(files) != 1:
        raise HTTPException(status_code=400, detail="Upload exactly one PDF file.")
    file_name = (files[0].filename or "").lower()
    content_type = (files[0].content_type or "").lower()
    if content_type and content_type != "application/pdf" and not file_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    normalized_term = (aid_term or "").strip().upper() or DEFAULT_AID_TERM
    if normalized_term not in ALLOWED_AID_TERMS:
        allowed = ", ".join(sorted(ALLOWED_AID_TERMS))
        raise HTTPException(status_code=400, detail=f"Aid term must be one of: {allowed}.")

    if not can_accept_job():
        raise HTTPException(
            status_code=429,
            detail="Another scholarship batch is still extracting. Wait for it to finish, then upload again.",
        )

    outside_scholarship_service = OutsideScholarshipService(azure_client, user_directory)
    filename, pdf_bytes = await outside_scholarship_service.read_single_pdf(files)
    job_id = create_job(job_owner(user))
    background_tasks.add_task(
        _run_outside_scholarships_job,
        job_id,
        outside_scholarship_service,
        pdf_bytes,
        filename,
        graph_access_token,
        aid_year,
        normalized_term,
    )
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": STATUS_PROCESSING})


@router.get("/api/banking/outside-scholarships/jobs/{job_id}")
async def outside_scholarships_job(
    job_id: str,
    user: Dict = Depends(check_banking_or_admin_permissions),
):
    """Return the review preview when extraction finishes, or 400/500 if it failed."""
    job = get_job(job_id)
    if not job or job["owner"] != job_owner(user):
        raise HTTPException(status_code=404, detail="Upload job not found.")
    if job["status"] == STATUS_PROCESSING:
        return {"job_id": job_id, "status": STATUS_PROCESSING}
    if job["status"] == STATUS_ERROR:
        raise HTTPException(status_code=job.get("status_code") or 500, detail=job.get("detail"))
    return job["preview"]


@router.post("/api/banking/outside-scholarships/active-directory-names")
async def outside_scholarships_active_directory_names(
    body: Dict[str, Any] = Body(...),
    user: Dict = Depends(check_banking_or_admin_permissions),
    azure_client: AzureClient = Depends(get_azure_client),
    user_directory: GraphUserDirectory = Depends(get_graph_user_directory),
    graph_access_token: str = Depends(get_bearer_token),
):
    """Look up Active Directory names for one or more PIDs during review."""
    raw_pids = body.get("pids") if isinstance(body, dict) else None
    if not isinstance(raw_pids, list):
        raise HTTPException(status_code=400, detail="Body must include a pids array.")
    pids = [str(pid).strip() for pid in raw_pids if pid is not None and str(pid).strip()]
    service = OutsideScholarshipService(azure_client, user_directory)
    return await service.lookup_active_directory_for_pids(pids, graph_access_token)


@router.post("/api/banking/outside-scholarships/export")
async def outside_scholarships_export(
    body: Dict[str, Any] = Body(...),
    user: Dict = Depends(check_banking_or_admin_permissions),
    azure_client: AzureClient = Depends(get_azure_client),
    user_directory: GraphUserDirectory = Depends(get_graph_user_directory),
    graph_access_token: str = Depends(get_bearer_token),
):
    """Export reviewed outside-scholarship checks to Excel.

    Active Directory names are re-resolved on the server so the workbook does not
    trust client-supplied directory results.
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid export payload.")
    reviewed_by = (
        user.get("email")
        or user.get("preferred_username")
        or user.get("upn")
        or user.get("id")
        or ""
    )
    service = OutsideScholarshipService(azure_client, user_directory)
    return await service.export_reviewed(
        body,
        reviewed_by=str(reviewed_by),
        graph_access_token=graph_access_token,
    )