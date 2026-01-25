from pydantic import BaseModel
from typing import List, Optional
from .chat import Message


class EDIQuery(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    messages: Optional[List[Message]] = None


class TransactionResult(BaseModel):
    trace_number: str
    amount: float
    effective_date: str
    originator: str
    receiver: str
    page_number: Optional[str] = None

class EDIResponse(BaseModel):
    answer: str
    transactions: List[TransactionResult]
    query_type: str
    search_performed: bool


class EDIAnalysisRequest(BaseModel):
    start: str  # YYYY-MM-DD
    end: str    # YYYY-MM-DD
    mode: str