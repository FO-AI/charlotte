from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
load_dotenv()

class Settings(BaseSettings):
    AZURE_SEARCH_ENDPOINT: str = os.getenv("AZURE_SEARCH_ENDPOINT")
    AZURE_SEARCH_API_KEY: str = os.getenv("AZURE_SEARCH_API_KEY")
    AZURE_SEARCH_INDEX_NAME: str = os.getenv("AZURE_SEARCH_INDEX_NAME")
    AZURE_AI_PROJECT_ENDPOINT: str = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    AZURE_AD_TENANT_ID: str = os.getenv("AZURE_AD_TENANT_ID")
    AZURE_AD_CLIENT_ID: str = os.getenv("AZURE_AD_CLIENT_ID")
    AZURE_AD_CLIENT_SECRET: str = os.getenv("AZURE_AD_CLIENT_SECRET")
    AZURE_AGENT_ID: str = os.getenv("AZURE_AGENT_ID")
    AZURE_OPENAI_KEY: str = os.getenv("AZURE_OPENAI_KEY")
    AZURE_AI_RESOURCE_ENDPOINT: str = os.getenv("AZURE_AI_RESOURCE_ENDPOINT")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()