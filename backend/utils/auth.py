from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_logger
from typing import Optional, Dict
import base64
import json
logger = get_logger(__name__)

# Lazy access config - will be loaded on first use
_access_config_cache: Optional[Dict] = None


def _get_access_config() -> Dict:
    """Lazy loader for access config to avoid circular imports"""
    global _access_config_cache
    if _access_config_cache is None:
        # Import inside function to avoid circular imports at module load time
        from api.dependencies import get_access_config

        _access_config_cache = get_access_config()
        logger.debug(f"Access config loaded: {_access_config_cache}")
    return _access_config_cache

# Security scheme
security = HTTPBearer()

def validate_jwt_token(token: str) -> Dict:
    """
    Simple JWT token validation - extracts user info from token payload
    Note: This does NOT verify token signature (Azure AD handles that)
    """
    try:
        # Split JWT token into parts
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")
        
        # Decode payload (add padding if needed)
        payload_encoded = parts[1]
        payload_encoded += '=' * (4 - len(payload_encoded) % 4)
        payload_decoded = base64.urlsafe_b64decode(payload_encoded)
        payload = json.loads(payload_decoded)
        
        # Extract user information from token
        # Try multiple fields for email as different tokens may have email in different fields
        email = (payload.get("email") or 
                payload.get("preferred_username") or 
                payload.get("upn") or 
                payload.get("unique_name"))
        

        # Get access config lazily to avoid circular imports
        access_config = _get_access_config()
        department = access_config.get('emails', {}).get(email.lower()) if email else None
        
        user_info = {
            "id": payload.get("oid") or payload.get("sub"),
            "email": email,
            "name": payload.get("name"),
            "given_name": payload.get("given_name"),
            "family_name": payload.get("family_name"),
            "job_title": payload.get("jobTitle"),
            "tenant_id": payload.get("tid"),
            "department": department
        }
        return user_info
        
    except Exception as e:
        logger.error(f"JWT validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user from JWT token"""
    try:
        user_info = validate_jwt_token(credentials.credentials)
        
        if not user_info.get("id"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Optional dependency that doesn't raise error if no auth provided"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

# Utility functions for auth checking/ do not need require unc email since we are using Azure AD
