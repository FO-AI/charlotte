from .chat import router as chat_router
from .edi import router as edi_router
from .alignrx import router as alignrx_router
from .health import router as health_router
from .sessions import router as sessions_router 
from .user_department import router as user_department_router
from .banking import router as banking_router
__all__ = ["chat_router", "edi_router", "alignrx_router", "health_router", "sessions_router", "user_department_router", "banking_router"]