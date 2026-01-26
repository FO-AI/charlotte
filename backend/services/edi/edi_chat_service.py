import os
from typing import List, Dict
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from config import get_logger
from openai import AzureOpenAI
from .conversation_memory import EDIConversationMemory
from prompts import extract_params_prompt, ai_overview_prompt, rag_response_prompt
from schemas import TransactionResult
import json

logger = get_logger(__name__)

# EDI Search Service Integration
class EDIChatService:
    """Integration class for EDI search in Charlotte"""
    
    def __init__(self, edi_memory: EDIConversationMemory, openai_client: AzureOpenAI, search_client: SearchClient):
        self.edi_memory = edi_memory
        self.search_client = search_client
        self.openai_client = openai_client
    

    def query(self, question: str, conversation_id: str = None) -> dict:
        """Query the EDI chat service"""
        
        params = self.extract_query_parameters(question)
        transactions = self.search_transactions(params)
        transaction_results = [
            TransactionResult(
                trace_number=t.get('trace_number', ''),
                amount=t.get('amount', 0.0),
                effective_date=t.get('effective_date', ''),
                originator=t.get('originator', ''),
                receiver=t.get('receiver', ''),
                page_number=t.get('page_number')
            )
            for t in transactions
        ]
        ai_answer = self.generate_rag_response(question, transaction_results, params, conversation_id)
        return {
            "answer": ai_answer,
            "transactions": transaction_results,
            "params": params
        }
    
    def extract_query_parameters(self, question: str) -> Dict:
        """Extract structured parameters from natural language query using AI"""
        try:
            # Prompt for parameter extraction
            system_prompt = extract_params_prompt

            user_prompt = f"Extract parameters from this query: {question}"
            
            response = self.openai_client.chat.completions.create(
                model=os.getenv("SMALL_MODEL_NAME", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=200

            )
            
            # Parse the AI response
            ai_response = response.choices[0].message.content.strip()
            logger.info(f"AI parameter extraction response: {ai_response}")
            
            # Clean JSON response (remove markdown formatting if present)
            json_text = ai_response
            if json_text.startswith('```json'):
                json_text = json_text.replace('```json', '').replace('```', '').strip()
            elif json_text.startswith('```'):
                json_text = json_text.replace('```', '').strip()
            
            # Parse JSON response
            params = json.loads(json_text)
            
            # Validate and set defaults
            default_params = {
                "amount": None,
                "amount_min": None,
                "amount_max": None,
                "date": None,
                "date_start": None,
                "date_end": None,
                "trace_number": None,
                "originator": None,
                "query_type": "general"
            }
            
            # Merge with defaults
            for key in default_params:
                if key not in params or params[key] == "":
                    params[key] = default_params[key]
            
            logger.info(f"Extracted parameters: {params}")
            return params
            
        except Exception as e:
            logger.error(f"Error in AI parameter extraction: {e}")
            # Fallback to basic parameters
            return {
                "amount": None,
                "amount_min": None,
                "amount_max": None,
                "date": None,
                "date_start": None,
                "date_end": None,
                "trace_number": None,
                "originator": None,
                "query_type": "general"
            }
    
    def search_transactions(self, params: Dict) -> List[Dict]:
        """Search for transactions based on extracted parameters using flexible filters"""
        if not self.search_client:
            logger.warning("Search client not available")
            return []
        
        logger.info(f"Searching with params: {params}")
        
        try:
            filter_conditions = []
            search_text = ""
            top_count = 100  # Default limit
            
            # Build filter conditions based on parameters
            if params.get("amount"):
                filter_conditions.append(f"amount eq {params['amount']}")
            
            if params.get("amount_min"):
                filter_conditions.append(f"amount ge {params['amount_min']}")
                
            if params.get("amount_max"):
                filter_conditions.append(f"amount le {params['amount_max']}")
            
            if params.get("date"):
                filter_conditions.append(f"effective_date eq '{params['date']}'")
                
            if params.get("date_start"):
                filter_conditions.append(f"effective_date ge '{params['date_start']}'")
                
            if params.get("date_end"):
                filter_conditions.append(f"effective_date le '{params['date_end']}'")
            
            if params.get("trace_number"):
                filter_conditions.append(f"trace_number eq '{params['trace_number']}'")
                top_count = 1  # Only need one result for specific trace
            
            if params.get("originator"):
                # Use search text for originator to allow partial matches
                search_text = params["originator"]
                
            # Handle special query types
            if params.get("query_type") == "count_all":
                results = self.search_client.search(
                    search_text="*",
                    include_total_count=True,
                    top=0
                )
                total_count = results.get_count()
                logger.info(f"Total transactions count: {total_count}")
                return [{"total_count": total_count, "query_type": "count_all"}]
            
            # If asking for all transactions (e.g., "all transactions in June")
            if params.get("query_type") == "all_in_period":
                top_count = 1000  # Increase limit for period queries
            
            # Build final filter expression
            filter_expr = " and ".join(filter_conditions) if filter_conditions else None
            
            logger.info(f"Filter expression: {filter_expr}")
            logger.info(f"Search text: '{search_text}'")
            logger.info(f"Top count: {top_count}")
            
            # Execute search
            search_params = {
                "search_text": search_text,
                "select": ["trace_number", "amount", "effective_date", "originator", "receiver", "page_number"],
                "top": top_count,
                "include_total_count": True
            }
            
            if filter_expr:
                search_params["filter"] = filter_expr
                
            if search_text and params.get("originator"):
                search_params["search_fields"] = ["originator"]
            
            # The ** unpacks the search_params dictionary into keyword arguments
            # For example, if search_params = {"search_text": "foo", "top": 10}
            # This is equivalent to: search_client.search(search_text="foo", top=10)
            results = self.search_client.search(**search_params)
            
            # Convert results to list
            result_list = [dict(result) for result in results]
            total_found = results.get_count() if hasattr(results, 'get_count') else len(result_list)
            
            logger.info(f"Search returned {len(result_list)} results out of {total_found} total matches")
            
            # Add metadata about the search
            if result_list:
                result_list[0]["_search_metadata"] = {
                    "total_matches": total_found,
                    "returned_count": len(result_list),
                    "query_params": params
                }
            
            return result_list
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def prepare_context(self, transactions: List[Dict]) -> str:
        """Prepare transaction data as context for the LLM"""
        if not transactions:
            return "No transactions found."
            
        # Handle count_all queries
        if len(transactions) == 1 and "total_count" in transactions[0]:
            return f"Total transactions in database: {transactions[0]['total_count']}"
        
        # Filter out metadata from first transaction if present
        clean_transactions = []
        for t in transactions:
            if "_search_metadata" in t:
                metadata = t.pop("_search_metadata")
                # Use metadata for summary if needed
            clean_transactions.append(t)
        
        # Format transactions as structured context
        context_parts = []
        context_parts.append(f"Found {len(clean_transactions)} transactions:\n")
        
        for i, t in enumerate(clean_transactions[:50], 1):  # Limit to first 50 for context
            context_parts.append(
                f"{i}. Trace: {t.get('trace_number', 'N/A')}, "
                f"Amount: ${t.get('amount', 0):.2f}, "
                f"Date: {t.get('effective_date', 'N/A')}, "
                f"From: {t.get('originator', 'N/A')}, "
                f"To: {t.get('receiver', 'N/A')}"
            )
        
        if len(clean_transactions) > 50:
            context_parts.append(f"\n... and {len(clean_transactions) - 50} more transactions")
            
        return "\n".join(context_parts)
    
    def generate_rag_response(self, question: str, transactions: List[Dict], params: Dict, conversation_id: str = None) -> str:
        """Generate RAG response using transaction context and EDI conversation memory"""
        try:
            # Prepare context from transactions
            context = self.prepare_context(transactions)
            
            # Get EDI conversation context if available
            conversation_context = ""
            if conversation_id:
                conversation_context = self.edi_memory.get_context(conversation_id, max_messages=5)
            
            # Handle special cases
            if not transactions:
                return "I couldn't find any transactions matching your query. Please check the criteria and try again."
            
            # Handle count queries
            if len(transactions) == 1 and "total_count" in transactions[0]:
                count = transactions[0]["total_count"]
                return f"I have **{count:,}** EDI transactions in the database."
            
            # Create system prompt for RAG response
            system_prompt = rag_response_prompt

            user_prompt = f"User's question: {question}\n\nPlease analyze the transaction data and provide a comprehensive answer."
            
            response = self.openai_client.chat.completions.create(
                model=os.getenv("SMALL_MODEL_NAME", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt.format(
                        conversation_context=conversation_context,
                        context=context
                    )},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            ai_response = response.choices[0].message.content.strip()
            logger.info(f"RAG response generated: {ai_response[:200]}...")
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error generating RAG response: {e}")
            return "I encountered an error while analyzing the transaction data. Please try again."
