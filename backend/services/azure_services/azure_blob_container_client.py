'''
Azure Blob Container Client
This module provides a client for interacting with Azure Blob Storage containers.
'''

from azure.storage.blob import BlobServiceClient  # pyright: ignore[reportMissingImports]
from config.logging import get_logger
from config.settings import Settings

logger = get_logger(__name__)
settings = Settings()


class BlobStorageClient:
    def __init__(self, connection_string: str, container_name: str):
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        # Ensure the container exists
        try:
            if not self.container_client.exists():
                self.blob_service_client.create_container(container_name)
        except Exception:
            # If exists() is not available or raises due to permissions, best-effort get properties
            # This will raise if the container truly does not exist
            self.container_client.get_container_properties()
    
    def list_blobs(self, include_metadata=False):
        """List blobs in the container. Set include_metadata=True to include blob metadata."""
        if include_metadata:
            return self.container_client.list_blobs(include=['metadata'])
        return self.container_client.list_blobs()
    
    def upload_blob(self, blob_name: str, data: bytes, overwrite: bool = True):
        self.container_client.upload_blob(name=blob_name, data=data, overwrite=overwrite)
    
    def download_blob(self, blob_name: str):
        return self.container_client.download_blob(blob_name)

    def download_blob_bytes(self, blob_name: str) -> bytes:
        downloader = self.download_blob(blob_name)
        return downloader.readall()

    def get_container_client(self, container_name: str = None):
        """Return a container client; if name not provided, return the default one."""
        if container_name and container_name != self.container_name:
            return self.blob_service_client.get_container_client(container_name)
        return self.container_client
    
    def get_blob_properties(self, blob_name: str):
        """Get properties of a specific blob"""
        blob_client = self.container_client.get_blob_client(blob_name)
        return blob_client.get_blob_properties()
    
    def get_blob_url(self, blob_name: str):
        """Get the URL for a specific blob"""
        blob_client = self.container_client.get_blob_client(blob_name)
        return blob_client.url

    
    def set_blob_metadata(self, blob_name: str, metadata: dict) -> bool:
        """Set the metadata for a specific blob"""
        blob_client = self.container_client.get_blob_client(blob_name)
        try:
            blob_client.set_blob_metadata(metadata)
            return True
        except Exception as e:
            logger.error(f"Error setting blob metadata: {e}")
            return False
    
    def get_blob_metadata(self, blob_name: str):
        """Get the metadata for a specific blob"""
        blob_client = self.container_client.get_blob_client(blob_name)
        try:
            properties = blob_client.get_blob_properties()
            return properties.metadata if properties.metadata else {}
        except Exception as e:
            logger.error(f"Error getting blob metadata: {e}")
            return {}

def main():
    connection_string = settings.azure_storage_connection_string
    container_name = settings.azure_storage_container_name
    if not connection_string or not container_name:
        logger.error("Missing AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_CONTAINER_NAME environment variables")
        return

    logger.info("Environment OK: using provided Azure Storage settings.")
    try:
        client = AzureBlobContainerClient(connection_string, container_name)
        logger.info(f"Connected to container '{container_name}'.")
    except Exception as exc:
        logger.error(f"Failed to create container client: {exc}")
        return
    try:
        logger.info(f"Listing blobs in container '{container_name}'...")
        count = 0
        for blob in client.list_blobs():
            logger.info(f"- {blob.name}")
            count += 1
        if count == 0:
            logger.info("No blobs found.")
        else:
            logger.info(f"Total blobs: {count}")
    except Exception as exc:
        logger.error(f"Failed to list blobs: {exc}")

if __name__ == "__main__":
    main()