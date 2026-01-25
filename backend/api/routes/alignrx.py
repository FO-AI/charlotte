from schemas import EDIAnalysisRequest
from fastapi import APIRouter, Depends, File, UploadFile
from typing import Dict
from config import get_logger
from utils.auth import require_unc_email
from services import analyze_alignrx_range_service, export_alignrx_range_service, upload_alignrx_report_service, BlobStorageClient
from dependencies import get_alignrx_blob_client

logger = get_logger(__name__)
router = APIRouter(tags=["alignrx"])


@router.post("/api/alignrx/export")
async def export_alignrx_range(request: EDIAnalysisRequest, user: Dict = Depends(require_unc_email)):
    """Export AlignRx reports between start and end dates to Excel."""
    return export_alignrx_range_service(request.start, request.end)


@router.post("/api/alignrx/analyze")
async def analyze_alignrx_range(request: EDIAnalysisRequest, user: Dict = Depends(require_unc_email)):
    """Analyze AlignRx reports between start and end dates (YYYY-MM-DD)."""
    return analyze_alignrx_range_service(request.start, request.end)


@router.post("/api/alignrx/upload-report")
async def upload_alignrx_report(
    file: UploadFile = File(...),
    user: Dict = Depends(require_unc_email),
    blob_client: BlobStorageClient = Depends(get_alignrx_blob_client)
):
    """Upload AlignRx Excel report, parse it, and index parsed data."""
    return await upload_alignrx_report_service(blob_client, user, file)
