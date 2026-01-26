from .azure_services import AzureCosmosClient
from fastapi import HTTPException, Request
from typing import Dict
import logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

async def create_session_service(request: Request, user: Dict, cosmos_client: AzureCosmosClient):
    """Create a new session"""
    try:
        data = await request.json()
        session_id = data.get('session_id')
        user_id = data.get('user_id', user.get('email'))
        title = data.get('title', 'New Chat')
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        session = cosmos_client.create_new_session(session_id, user_id, title)
        return {
            "session": session,
            "message": "Session created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating session: {str(e)}")

async def get_sessions_service(user_id: str, cosmos_client: AzureCosmosClient):
    """Get all sessions for a specific user"""
    try:
        sessions = cosmos_client.get_sessions_for_user_id(user_id)
        return {
            "user_id": user_id,
            "sessions": sessions,
            "count": len(sessions)
        }
    except Exception as e:
        logger.error(f"Error getting sessions for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting sessions: {str(e)}")

async def get_session_service_by_id(session_id: str, user: Dict, cosmos_client: AzureCosmosClient):
    """Get a specific session with its messages"""
    try:
        session = cosmos_client.get_session(session_id)
        return {
            "session": session,
            "message_count": len(session.get('messages', [])),
            "retrieved_by": user.get('email') if user and isinstance(user, dict) else None
        }
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting session: {str(e)}")


async def update_session_service(session_id: str, request: Request, user: Dict, cosmos_client: AzureCosmosClient):
    """Update a session (add messages, rename, etc.)"""
    try:
        data = await request.json()
        user_id = data.get('user_id', user.get('email'))
        messages = data.get('messages')
        title = data.get('title')
        
        session = cosmos_client.update_session(session_id, user_id, messages, title)
        return {
            "session": session,
            "message": "Session updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating session: {str(e)}")

async def delete_session_service(session_id: str, user: Dict, cosmos_client: AzureCosmosClient):
    """Delete a session"""
    try:
        cosmos_client.delete_session(session_id)
        return {
            "message": "Session deleted successfully",
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")
