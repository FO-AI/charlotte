from fastapi import APIRouter
from fastapi import Depends, HTTPException
from typing import Dict
from schemas.chat import QueryRequest, QueryResponse
from utils.auth import require_unc_email

from schemas.edi import EDIQuery
from azure.ai.agents.models import ListSortOrder
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# Chat endpoint that routes based on mode
@router.post("/api/chat")
async def chat(request: QueryRequest, user: Dict = Depends(require_unc_email)):
    """Chat endpoint - routes to EDI search or Azure AI agent based on mode"""
    
    if request.mode == "EDI":
        # EDI mode - uses EDI memory
        conversation_id = request.conversation_id
        if not conversation_id:
            user_email = user.get('email', 'anonymous') if user and isinstance(user, dict) else 'anonymous'
            conversation_id = f"edi_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_email}"
        
        edi_query = EDIQuery(
            question=request.query,
            conversation_id=conversation_id,
            messages=request.messages
        )
        edi_response = await query_edi_transactions(edi_query, user)

        return {
            "response": edi_response.answer,
            "type": "edi",
            "transactions_found": len(edi_response.transactions),
            "data": edi_response.transactions,
            "conversation_id": conversation_id
        }
    else:
        # General AI mode - Azure agent manages its own memory
        ai_response = await query(request, user)
        return {
            "response": ai_response["answer"],
            "type": "general",
            "sources": ai_response["sources"],
            "conversation_id": ai_response["conversation_id"]
        }

@router.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest, user: Dict = Depends(require_unc_email)):
    """Azure AI Foundry agent query endpoint. Agent manages its own thread memory."""
    
    try:
        # Get project client and agent from app state
        project_client = app.state.project_client
        agent = app.state.agent
        
        # Get or create thread - use existing thread_id from request or create new
        thread_id = request.conversation_id
        if thread_id:
            try:
                thread = project_client.agents.threads.get(thread_id)
            except Exception:
                # Thread doesn't exist, create new one
                thread = project_client.agents.threads.create()
        else:
            thread = project_client.agents.threads.create()
        
        # Create user message in Azure thread
        project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=request.query
        )
        
        # Run the agent
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id
        )

        if run.status == "failed":
            logger.error(f"Agent run failed: {run.error}")
            return {
                "answer": "I'm sorry, I'm having trouble answering your question. Please try again later.",
                "sources": [],
                "conversation_id": thread.id
            }
        
        # Get the latest assistant message
        messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
        assistant_messages = [msg for msg in messages if msg.role == "assistant"]
        
        text_content = "I'm sorry, I couldn't find a valid response."
        if assistant_messages:
            latest_message = assistant_messages[-1]
            if latest_message.content and isinstance(latest_message.content, list):
                for part in latest_message.content:
                    if part.get("type") == "text" and "text" in part and "value" in part["text"]:
                        text_content = part["text"]["value"]
                        break

        return {
            "answer": text_content,
            "sources": [],
            "conversation_id": thread.id
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Azure AI Foundry query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@router.get("/api/conversation/{conversation_id}/history")
async def get_edi_conversation_history(conversation_id: str, user: Dict = Depends(require_unc_email)):
    """Get EDI conversation history for a given conversation ID"""
    
    try:
        history = edi_memory.get_history(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "message_count": len(history),
            "messages": history,
            "retrieved_by": user.get('email') if user and isinstance(user, dict) else None
        }
        
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation history: {str(e)}")

