from pydantic import BaseModel
from typing import List, Optional


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