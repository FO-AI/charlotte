from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from typing import Dict, List, Optional
from utils.rba import check_banking_or_admin_permissions
from config import get_logger
from services.banking import BankingUploadService
from services.azure_services import AzureClient
from api.dependencies import get_azure_client
from services.banking import OutsideScholarshipService
logger = get_logger(__name__)
router = APIRouter(tags=["banking"])

@router.post("/api/banking/upload-files")
async def upload_banking_files(files: List[UploadFile] = File(...), user: Dict = Depends(check_banking_or_admin_permissions), azure_client: AzureClient = Depends(get_azure_client)):
    """Upload banking files"""

    """
    Accepts multiple PDF files, extracts data via Azure OpenAI, and returns an Excel file.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    upload_service = BankingUploadService(azure_client)

    return await upload_service.upload_and_analyze_files(files)

@router.post("/api/banking/outside-scholarships")
async def outside_scholarships(
    files: List[UploadFile] = File(...),
    aid_year: Optional[str] = Form(None),
    aid_term: str = Form("F"),
    user: Dict = Depends(check_banking_or_admin_permissions),
    azure_client: AzureClient = Depends(get_azure_client),
):
    """Upload outside scholarship check PDF"""

    """
    Accepts a single PDF file containing scanned outside-scholarship check pages.

    Pages are ordered in front/back pairs: page 1 = front of check 1, page 2 = back
    of check 1, page 3 = front of check 2, page 4 = back of check 2, and so on.

    The multipart field is still named "files" (list of one) to match the shared
    upload plumbing, but exactly one PDF is expected.

    Calls OutsideScholarshipService to analyze the file.

    Optional multipart form fields:
    - aid_year: 4-digit aid year (defaults to current year)
    - aid_term: "F" or "S" (defaults to "F")

    returns:
    - Excel file download
    """
    if not files:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    if len(files) != 1:
        raise HTTPException(status_code=400, detail="Upload exactly one PDF file.")
    file_name = (files[0].filename or "").lower()
    content_type = (files[0].content_type or "").lower()
    if content_type and content_type != "application/pdf" and not file_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    normalized_term = (aid_term or "").strip().upper() or "F"
    if normalized_term not in {"F", "S"}:
        raise HTTPException(status_code=400, detail="Aid term must be 'F' or 'S'.")

    outside_scholarship_service = OutsideScholarshipService(azure_client)

    return await outside_scholarship_service.upload_and_analyze_files(
        files,
        aid_year=aid_year,
        aid_term=normalized_term,
    )
