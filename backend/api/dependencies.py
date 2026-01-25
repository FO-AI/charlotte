'''
Dependencies for the backend
'''
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from db import get_db
from clients.email_client import EmailClient
from clients.azure_ai_client import AzureAIClient
from openai import AzureOpenAI
from config.settings import settings
from azure_services.azure_edi_search_client import EDISearchClient
from azure_services.azure_cosmos_client import AzureCosmosClient
from azure_services.azure_client import AzureClient
security = HTTPBearer()

azure_openai_client = AzureOpenAI(
    api_key=settings.AZURE_OPENAI_KEY,
    api_version=settings.AZURE_OPENAI_API_VERSION,
    azure_endpoint=settings.AZURE_AI_RESOURCE_ENDPOINT
)


def get_edi_search_client():
    return EDISearchClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT,
        api_key=settings.AZURE_SEARCH_API_KEY,
        index_name=settings.AZURE_SEARCH_INDEX_NAME
    )

def get_azure_client():
    return AzureClient(
        endpoint=settings.AZURE_AI_PROJECT_ENDPOINT,
        api_key=settings.AZURE_AI_PROJECT_API_KEY,
        index_name=settings.AZURE_AI_PROJECT_INDEX_NAME
    )

def get_cosmos_client():
    return AzureCosmosClient()