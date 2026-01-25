from fastapi import APIRouter
from api.routes import chat_router, edi_router, alignrx_router, health_router

router = APIRouter()

router.include_router(chat_router)
router.include_router(edi_router)
router.include_router(alignrx_router)
router.include_router(health_router)

