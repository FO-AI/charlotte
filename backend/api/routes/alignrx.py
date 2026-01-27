from schemas import AlignRxAnalysisRequest
from fastapi import APIRouter, Depends, File, UploadFile
from typing import Dict
from config import get_logger
from utils.rba import check_accounting_or_admin_permissions
from services import analyze_alignrx_range_service, export_alignrx_range_service, upload_alignrx_report_service
from services.azure_services import BlobStorageClient
from api.dependencies import get_alignrx_blob_client
from azure.search.documents import SearchClient
from api.dependencies import get_alignrx_search_client
logger = get_logger(__name__)
router = APIRouter(tags=["alignrx"])


@router.post("/api/alignrx/export")
async def export_alignrx_range(request: AlignRxAnalysisRequest, user: Dict = Depends(check_accounting_or_admin_permissions), search_client: SearchClient = Depends(get_alignrx_search_client)):
    """Export AlignRx reports between start and end dates to Excel."""
    return await export_alignrx_range_service(request.start, request.end, search_client)


@router.post("/api/alignrx/analyze")
async def analyze_alignrx_range(request: AlignRxAnalysisRequest, user: Dict = Depends(check_accounting_or_admin_permissions), search_client: SearchClient = Depends(get_alignrx_search_client)):
    """Analyze AlignRx reports between start and end dates (YYYY-MM-DD)."""
    logger.info('analyzing alignrx range: %s', request)

    return await analyze_alignrx_range_service(request.start, request.end, search_client)


@router.post("/api/alignrx/upload-report")
async def upload_alignrx_report(
    file: UploadFile = File(...),
    user: Dict = Depends(check_accounting_or_admin_permissions),
    blob_client: BlobStorageClient = Depends(get_alignrx_blob_client),
    search_client: SearchClient = Depends(get_alignrx_search_client)
):
    """Upload AlignRx Excel report, parse it, and index parsed data."""
    return await upload_alignrx_report_service(blob_client, user, file, search_client)
