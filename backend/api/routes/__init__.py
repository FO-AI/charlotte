from .chat import router as chat_router
from .edi import router as edi_router
from .alignrx import router as alignrx_router
from .health import router as health_router

__all__ = ["chat_router", "edi_router", "alignrx_router", "health_router"]