from pydantic import BaseModel
class AlignRxAnalysisRequest(BaseModel):
    start: str
    end: str
