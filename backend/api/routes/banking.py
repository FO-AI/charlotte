from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from typing import Dict, List
from utils.rba import check_banking_or_admin_permissions
from config import get_logger
from services.banking import BankingUploadService
from services.azure_services import AzureClient
from api.dependencies import get_azure_client
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