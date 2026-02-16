from fastapi import APIRouter
from api.routes import chat_router, edi_router, alignrx_router, health_router, sessions_router, user_department_router, banking_router

router = APIRouter()

router.include_router(chat_router)
router.include_router(edi_router)
router.include_router(alignrx_router)
router.include_router(health_router)
router.include_router(sessions_router)
router.include_router(user_department_router)
router.include_router(banking_router)