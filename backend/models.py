from pydantic import BaseModel
from typing import List, Optional


# Define request and response models
class Message(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    messages: Optional[List[Message]] = None
    mode: Optional[str] = None

class Source(BaseModel):
    document_name: str
    text_snippet: Optional[str] = None

class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    conversation_id: str

# EDI-specific models
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
