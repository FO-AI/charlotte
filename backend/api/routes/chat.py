from fastapi import APIRouter, Depends
from typing import Dict
from schemas import QueryRequest
from utils.auth import require_unc_email
from config import get_logger
from services.edi import EDIConversationMemory, EDIChatService
from services.azure_services import AzureClient
from services.chat_services import chat_service, edi_conversation_history_service
from api.dependencies import get_edi_memory, get_edi_chat_service, get_azure_client
logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


# Chat endpoint that routes based on mode
@router.post("/api/chat")
async def chat(request: QueryRequest, user: Dict = Depends(require_unc_email), edi_memory: EDIConversationMemory = Depends(get_edi_memory), edi_chat_service: EDIChatService = Depends(get_edi_chat_service), azure_client: AzureClient = Depends(get_azure_client)):
    """Chat endpoint - routes to EDI search or Azure AI agent based on mode"""

    return await chat_service(request, user, edi_memory, edi_chat_service, azure_client=azure_client)




@router.get("/api/conversation/{conversation_id}/history")
async def get_edi_conversation_history(conversation_id: str, user: Dict = Depends(require_unc_email), edi_memory: EDIConversationMemory = Depends(get_edi_memory)):
    """Get EDI conversation history for a given conversation ID"""
    
    return await edi_conversation_history_service(conversation_id, edi_memory, user)

