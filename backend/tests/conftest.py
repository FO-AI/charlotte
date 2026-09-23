"""Shared fixtures for backend route tests. No real Azure access."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Fake settings before importing the app (settings = Settings() at import time).
_FAKE_URLS = (
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_AI_PROJECT_ENDPOINT",
    "AZURE_AI_RESOURCE_ENDPOINT",
)
_FAKE_PLACEHOLDERS = (
    "AZURE_SEARCH_API_KEY",
    "AZURE_SEARCH_INDEX_NAME",
    "AZURE_MASTER_SEARCH_INDEX",
    "AZURE_AD_TENANT_ID",
    "AZURE_AD_CLIENT_ID",
    "AZURE_AD_CLIENT_SECRET",
    "AZURE_AGENT_ID",
    "AZURE_OPENAI_KEY",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_STORAGE_ACCOUNT_NAME",
    "AZURE_STORAGE_KEY",
    "AZURE_ALIGNRX_REPORTS_CONTAINER",
    "AZURE_MASTER_EDI_CONTAINER",
)


def pytest_configure() -> None:
    for name in _FAKE_URLS:
        os.environ.setdefault(name, "https://ci.invalid")
    for name in _FAKE_PLACEHOLDERS:
        os.environ.setdefault(name, "ci-placeholder")
    os.environ.setdefault(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=https;AccountName=ci;AccountKey=Y2k=;EndpointSuffix=ci.invalid",
    )


@pytest.fixture
def app():
    import main

    return main.app


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user():
    return {
        "id": "u1",
        "email": "test@unc.edu",
        "name": "Test User",
        "department": "admin",
    }


@pytest.fixture
def override_auth(app, admin_user):
    """Bypass JWT/Cosmos by overriding get_current_user."""
    from utils.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: admin_user
    yield admin_user
    app.dependency_overrides.pop(get_current_user, None)
