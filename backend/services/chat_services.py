from config import get_logger
from schemas import QueryRequest, EDIQuery, EDIResponse, TransactionResult
from typing import Dict
from datetime import datetime
from services import query_edi_transactions, query, EDIConversationMemory, EDIChatService
from fastapi import HTTPException, ListSortOrder
from utils.auth import require_unc_email
from services import AzureClient
logger = get_logger(__name__)

async def query_edi_transactions(query: EDIQuery, user: Dict, edi_memory: EDIConversationMemory, edi_chat_service: EDIChatService):
    """EDI transaction queries with conversation memory"""
    
    try:
        logger.info(f"EDI query received: {query.question}")
        
        # Generate conversation ID if not provided
        conversation_id = query.conversation_id
        if not conversation_id:
            user_email = user.get('email', 'anonymous') if user and isinstance(user, dict) else 'anonymous'
            conversation_id = f"edi_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_email}"
        
        # Add user message to EDI memory
        edi_memory.add_message(
            conversation_id, 
            "user", 
            query.question,
            {"user_email": user.get('email') if user and isinstance(user, dict) else None}
        )
        
        response = edi_chat_service.query(query.question, conversation_id)
        
        ai_answer = response["answer"]
        transaction_results = response["transactions"]
        params = response["params"]
        
        edi_memory.add_message(
            conversation_id,
            "assistant", 
            ai_answer,
            {"transactions_found": len(transaction_results), "params": params}
        )
        
        return EDIResponse(
            answer=ai_answer,
            transactions=transaction_results,
            query_type=params["query_type"],
            search_performed=True
        )
        
    except Exception as e:
        logger.error(f"Error processing EDI query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing EDI query: {str(e)}")


async def query_ai_agent(request: QueryRequest, azure_client: AzureClient):
    """Azure AI Foundry agent query endpoint. Agent manages its own thread memory."""
    
    try:
        # Get project client and agent from app state
        project_client = azure_client.project_client
        agent = azure_client.agent
        
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


async def chat_service(request: QueryRequest, user: Dict, edi_memory: EDIConversationMemory, edi_chat_service: EDIChatService, azure_client: AzureClient):
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
        edi_response = await query_edi_transactions(edi_query, user, edi_memory, edi_chat_service)

        return {
            "response": edi_response.answer,
            "type": "edi",
            "transactions_found": len(edi_response.transactions),
            "data": edi_response.transactions,
            "conversation_id": conversation_id
        }
    else:
        # General AI mode - Azure agent manages its own memory
        ai_response = await query_ai_agent(request, azure_client=azure_client)
        return {
            "response": ai_response["answer"],
            "type": "general",
            "sources": ai_response["sources"],
            "conversation_id": ai_response["conversation_id"]
        }

async def edi_conversation_history_service(conversation_id: str, edi_memory: EDIConversationMemory, user: Dict):
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
        logger.error(f"Error getting EDI conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting EDI conversation history: {str(e)}")