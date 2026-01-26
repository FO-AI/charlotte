from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict
from services import AzureCosmosClient, get_sessions_service, get_session_service_by_id, create_session_service, update_session_service, delete_session_service
from utils.auth import require_unc_email
from api.dependencies import get_cosmos_client
import logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


router = APIRouter(tags=["sessions"])

@router.get("/api/sessions/{user_id}")
async def get_user_sessions(user_id: str, user: Dict = Depends(require_unc_email), cosmos_client: AzureCosmosClient = Depends(get_cosmos_client)):
    """Get all sessions for a specific user"""
    
    return await get_sessions_service(user_id, cosmos_client)

@router.get("/api/session/{session_id}")
async def get_session(session_id: str, user: Dict = Depends(require_unc_email), cosmos_client: AzureCosmosClient = Depends(get_cosmos_client)):
    """Get a specific session with its messages"""
    return await get_session_service_by_id(session_id, user, cosmos_client)

@router.post("/api/session")
async def create_session(request: Request, user: Dict = Depends(require_unc_email), cosmos_client: AzureCosmosClient = Depends(get_cosmos_client)):
    """Create a new session"""
    return await create_session_service(request, user, cosmos_client)


@router.put("/api/session/{session_id}")
async def update_session(session_id: str, request: Request, user: Dict = Depends(require_unc_email), cosmos_client: AzureCosmosClient = Depends(get_cosmos_client)):
    """Update a session (add messages, rename, etc.)"""
    return await update_session_service(session_id, request, user, cosmos_client)

@router.delete("/api/session/{session_id}")
async def delete_session(session_id: str, user: Dict = Depends(require_unc_email), cosmos_client: AzureCosmosClient = Depends(get_cosmos_client)):
    """Delete a session"""
    return await delete_session_service(session_id, user, cosmos_client)
