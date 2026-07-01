from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
from typing import Optional
load_dotenv()

class Settings(BaseSettings):
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY")
    azure_search_index_name: str = os.getenv("AZURE_SEARCH_INDEX_NAME")
    azure_master_search_index_name: str = os.getenv("AZURE_MASTER_SEARCH_INDEX")
    azure_ai_project_endpoint: str = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    azure_ad_tenant_id: str = os.getenv("AZURE_AD_TENANT_ID")
    azure_ad_client_id: str = os.getenv("AZURE_AD_CLIENT_ID")
    azure_ad_client_secret: str = os.getenv("AZURE_AD_CLIENT_SECRET")
    azure_agent_id: str = os.getenv("AZURE_AGENT_ID")
    azure_openai_key: str = os.getenv("AZURE_OPENAI_KEY")
    azure_ai_resource_endpoint: str = os.getenv("AZURE_AI_RESOURCE_ENDPOINT")
    azure_openai_model: str = "gpt-5-chat"

    azure_storage_container_name: str = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    azure_storage_connection_string: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    azure_storage_account_name: str = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    azure_storage_key: str = os.getenv("AZURE_STORAGE_KEY")
    azure_alignrx_reports_container: str = os.getenv("AZURE_ALIGNRX_REPORTS_CONTAINER")
    azure_master_edi_container: str = os.getenv("AZURE_MASTER_EDI_CONTAINER")

    azure_cosmos_connection_string: Optional[str] = os.getenv("AZURE_COSMOS_CONNECTION_STRING")
    azure_cosmos_database: Optional[str] = os.getenv("AZURE_COSMOS_DATABASE")
    azure_cosmos_container: Optional[str] = os.getenv("AZURE_COSMOS_CONTAINER")
    azure_cosmos_partition_key: Optional[str] = os.getenv("AZURE_COSMOS_PARTITION_KEY")

    azure_di_endpoint: Optional[str] = os.getenv("AZURE_DI_ENDPOINT")
    azure_di_key: Optional[str] = os.getenv("AZURE_DI_KEY")
    azure_di_model_id: str = os.getenv("AZURE_DI_MODEL_ID", "prebuilt-check.us")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
