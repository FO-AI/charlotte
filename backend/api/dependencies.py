'''
Dependencies for the backend - uses @lru_cache for lazy singleton initialization
'''
from functools import lru_cache
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import AzureOpenAI
from config import Settings, get_logger
from services.edi import EDIConversationMemory, EDIChatService
from services import BlobStorageClient, AzureClient, AzureCosmosClient
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

logger = get_logger(__name__)


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


@lru_cache()
def get_master_edi_blob_client() -> BlobStorageClient:
    """Lazy singleton for master EDI blob storage client"""
    settings = get_settings()
    return BlobStorageClient(
        connection_string=settings.azure_storage_connection_string,
        container_name=settings.azure_master_edi_container
    )


@lru_cache()
def get_alignrx_blob_client() -> BlobStorageClient:
    """Lazy singleton for AlignRx blob storage client"""
    settings = get_settings()
    return BlobStorageClient(
        connection_string=settings.azure_storage_connection_string,
        container_name=settings.azure_alignrx_reports_container
    )


@lru_cache()
def get_azure_client() -> AzureClient:
    """Lazy singleton for Azure AI client"""
    settings = get_settings()
    return AzureClient(
        endpoint=settings.azure_ai_project_endpoint,
        api_key=settings.azure_ai_project_api_key,
        index_name=settings.azure_ai_project_index_name
    )


@lru_cache()
def get_search_client() -> SearchClient:
    """Lazy singleton for Azure Search client"""
    settings = get_settings()
    try:
        endpoint = settings.azure_search_endpoint
        api_key = settings.azure_search_api_key
        index_name = settings.azure_master_search_index_name
        
        if endpoint and api_key:
            credential = AzureKeyCredential(api_key)
            return SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=credential
            )
    except Exception as e:
        logger.warning(f"Could not initialize Azure Search client: {e}")
        return None


@lru_cache()
def get_azure_openai_client() -> AzureOpenAI:
    """Lazy singleton for Azure OpenAI client"""
    settings = get_settings()
    return AzureOpenAI(
        api_key=settings.azure_openai_key,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_ai_resource_endpoint
    )


@lru_cache()
def get_cosmos_client() -> AzureCosmosClient:
    """Lazy singleton for Cosmos DB client"""
    return AzureCosmosClient()


def get_edi_memory() -> EDIConversationMemory:
    """EDI conversation memory - new instance per request for isolation"""
    return EDIConversationMemory()


def get_edi_chat_service() -> EDIChatService:
    """EDI chat service with injected dependencies"""
    return EDIChatService(
        edi_memory=get_edi_memory(),
        openai_client=get_azure_openai_client(),
        search_client=get_search_client()
    )
