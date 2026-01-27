from fastapi import HTTPException, Depends
from typing import Dict
'''
This script is used to check if the user has the required permissions to access the resource.

'''

from utils.auth import get_current_user
from services.azure_services import AzureCosmosClient
from config import get_logger
logger = get_logger(__name__)


def load_access_config( cosmos_client: AzureCosmosClient ) -> Dict:
    """Load access control document from Cosmos DB"""
    try:
        query = "SELECT * FROM c WHERE c.id = 'access-control'"
        items = list(cosmos_client.container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        if items:
            config = items[0]
            logger.debug("✅ Loaded access config from Cosmos DB")
            return config
        else:
            logger.debug("❌ access-control document not found")
            raise Exception("Access config not found")
    except Exception as e:
        logger.error(f"Error loading access config: {e}")
        raise


def check_accounting_permissions(user: Dict = Depends(get_current_user)):
    if not user.get("department") == "accounting":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user

def check_banking_permissions(user: Dict = Depends(get_current_user)):
    if not user.get("department") == "banking":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user

def check_admin_permissions(user: Dict = Depends(get_current_user)):
    if not user.get("department") == "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user

def check_accounting_or_admin_permissions(user: Dict = Depends(get_current_user)):
    """Check if user has accounting OR admin permissions"""
    if not (user.get("department") == "accounting" or user.get("department") == "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Requires accounting or admin permissions")
    return user

def check_banking_or_admin_permissions(user: Dict = Depends(get_current_user)):
    """Check if user has banking OR admin permissions"""

    if not (user.get("department") == "banking" or user.get("department") == "admin"):
        raise HTTPException(status_code=403, detail="Forbidden: Requires banking or admin permissions")
    return user
