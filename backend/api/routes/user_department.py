'''

This route send the user's department to the client.

'''

from fastapi import APIRouter, Depends
from utils.auth import get_current_user
from typing import Dict

router = APIRouter(tags=["user_department"])

@router.get("/auth/user-department")
async def get_user_department(user: Dict = Depends(get_current_user)):
    """Get the user's department from the authenticated user"""
    return {"department": user.get("department")}