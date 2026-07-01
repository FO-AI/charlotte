import logging
import os
from typing import Optional

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv
from openai import AzureOpenAI

from config.settings import settings

load_dotenv()

logger = logging.getLogger(__name__)


class AzureClient:
    """Azure client wrapper for AI Projects, OpenAI, and Document Intelligence."""

    def __init__(self):
        self.project_endpoint = settings.azure_ai_project_endpoint
        self.di_endpoint = settings.azure_di_endpoint
        self.di_key = settings.azure_di_key
        self.di_model_id = settings.azure_di_model_id
        self.tenant_id = settings.azure_ad_tenant_id
        self.client_id = settings.azure_ad_client_id
        self.client_secret = settings.azure_ad_client_secret
        self.agent_id = settings.azure_agent_id

        self.project_client = self.setup_azure_client()
        self.agent = self.get_agent()
        self.llm = self.get_llm()
        self.document_intelligence_client: Optional[DocumentIntelligenceClient] = None
        self.document_intelligence_client = self.get_di()

    def setup_azure_client(self):
        """Setup Azure AI project client."""
        missing_vars = []
        if not self.project_endpoint:
            missing_vars.append("AZURE_AI_PROJECT_ENDPOINT")
        if not self.tenant_id:
            missing_vars.append("AZURE_AD_TENANT_ID")
        if not self.client_id:
            missing_vars.append("AZURE_AD_CLIENT_ID")
        if not self.client_secret:
            missing_vars.append("AZURE_AD_CLIENT_SECRET")

        if missing_vars:
            error_msg = f"Missing required Azure environment variables: {', '.join(missing_vars)}"
            logger.error("ERROR: %s", error_msg)
            raise ValueError(error_msg)

        try:
            credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            self.project_client = AIProjectClient(
                credential=credential,
                endpoint=self.project_endpoint,
            )
            logger.info("Azure project client setup successfully")
            return self.project_client
        except Exception as exc:
            error_msg = f"Failed to create Azure client: {exc}"
            logger.error("ERROR: %s", error_msg)
            raise Exception(error_msg) from exc

    def get_llm(self):
        return AzureOpenAI(
            api_version="2024-12-01-preview",
            api_key=settings.azure_openai_key or os.getenv("AZURE_OPENAI_KEY"),
            azure_endpoint=settings.azure_ai_resource_endpoint or os.getenv("AZURE_AI_RESOURCE_ENDPOINT"),
        )

    def get_di(self) -> Optional[DocumentIntelligenceClient]:
        """Get (or lazily initialize) the Document Intelligence client."""
        if self.document_intelligence_client is not None:
            return self.document_intelligence_client

        if not self.di_endpoint or not self.di_key:
            logger.warning(
                "Document Intelligence client is not configured (missing AZURE_DI_ENDPOINT or AZURE_DI_KEY)."
            )
            return None

        try:
            self.document_intelligence_client = DocumentIntelligenceClient(
                endpoint=self.di_endpoint,
                credential=AzureKeyCredential(self.di_key),
            )
            logger.info("Document Intelligence client setup successfully")
        except Exception as exc:
            logger.error("Failed to initialize Document Intelligence client: %s", exc)
            self.document_intelligence_client = None

        return self.document_intelligence_client

    def get_agent(self):
        """Get the configured Azure AI agent."""
        agent_id = self.agent_id
        if not agent_id:
            error_msg = "AZURE_AGENT_ID is not set"
            logger.error("ERROR: %s", error_msg)
            raise ValueError(error_msg)

        try:
            agent = self.project_client.agents.get_agent(agent_id)
            logger.info("Agent %s retrieved successfully", agent_id)
            return agent
        except Exception as exc:
            error_msg = f"Failed to get agent: {exc}"
            logger.error("ERROR: %s", error_msg)
            raise Exception(error_msg) from exc
