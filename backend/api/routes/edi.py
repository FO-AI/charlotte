from fastapi import Depends, APIRouter, File, UploadFile
from typing import Dict
from utils.auth import require_unc_email
from config import get_logger
from services.edi import upload_service, get_dashboard_data_service, analyze_edi_range_service, get_reports_service, get_one_report_service, export_edi_range_service
from api.dependencies import get_master_edi_blob_client, get_azure_client
from services import BlobStorageClient, AzureClient
from schemas import EDIAnalysisRequest
from azure.search.documents import SearchClient
from api.dependencies import get_master_edi_search_client, get_chs_edi_search_client
logger = get_logger(__name__)
router = APIRouter(tags=["edi"])


@router.post("/api/upload-edi-report")
async def upload_edi_report(
    file: UploadFile = File(...),
    user: Dict = Depends(require_unc_email),
    blob_client: BlobStorageClient = Depends(get_master_edi_blob_client),
    chs_search_client: SearchClient = Depends(get_chs_edi_search_client),
    master_search_client: SearchClient = Depends(get_master_edi_search_client)
):
    """Upload EDI report to Azure Blob Storage"""
    return await upload_service(file, user, blob_client, chs_search_client, master_search_client)


@router.get("/api/edi/dashboard_data")
async def get_dashboard_data(
    user: Dict = Depends(require_unc_email),
    blob_client: BlobStorageClient = Depends(get_master_edi_blob_client),
    master_search_client: SearchClient = Depends(get_master_edi_search_client)
):
    """Get dashboard data for Master EDI transactions for current fiscal year"""
    return await get_dashboard_data_service(blob_client, master_search_client)


@router.post("/api/edi/analyze")
async def analyze_edi_range(
    request: EDIAnalysisRequest,
    user: Dict = Depends(require_unc_email),
    azure_client: AzureClient = Depends(get_azure_client),
    master_search_client: SearchClient = Depends(get_master_edi_search_client),
    chs_search_client: SearchClient = Depends(get_chs_edi_search_client)
):
    """Analyze EDI transactions between start and end dates (YYYY-MM-DD)."""
    return await analyze_edi_range_service(request, user, azure_client, master_search_client, chs_search_client)


@router.post("/api/edi/export")
async def export_edi_range(request: EDIAnalysisRequest, 
    user: Dict = Depends(require_unc_email), 
    master_search_client: SearchClient = Depends(get_master_edi_search_client), 
    chs_search_client: SearchClient = Depends(get_chs_edi_search_client)):
    """Export EDI transactions between start and end dates to Excel."""
    return await export_edi_range_service(request, user, master_search_client, chs_search_client)


@router.get("/api/edi/reports")
async def get_edi_reports(
    user: Dict = Depends(require_unc_email),
    page: int = 1,
    page_size: int = 20,
    blob_client: BlobStorageClient = Depends(get_master_edi_blob_client)
):
    """Get paginated list of EDI reports"""
    return await get_reports_service(user, page, page_size, blob_client)


@router.get("/api/edi/reports/{filename}")
async def get_edi_report(
    filename: str,
    user: Dict = Depends(require_unc_email),
    blob_client: BlobStorageClient = Depends(get_master_edi_blob_client)
):
    """Get a specific EDI report file from Azure Blob Storage"""
    return await get_one_report_service(filename, user, blob_client)