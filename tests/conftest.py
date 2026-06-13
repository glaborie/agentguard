"""Shared fixtures and markers for the test suite."""

import warnings

import pytest
import requests

try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
    warnings.filterwarnings(
        "ignore",
        message=r".*allowed_objects.*",
        category=PendingDeprecationWarning,
        module=r"langgraph\.checkpoint\.base",
    )
except ImportError:
    warnings.filterwarnings(
        "ignore",
        message=r".*allowed_objects.*",
        category=PendingDeprecationWarning,
    )

try:
    from starlette.warnings import StarletteDeprecationWarning

    warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)
except ImportError:
    warnings.filterwarnings(
        "ignore",
        message=r".*starlette\.testclient.*httpx2.*",
        category=Warning,
    )


def _service_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires Docker stack running")


def pytest_collection_modifyitems(config, items):
    if not _service_reachable("http://localhost:4000/health/liveliness"):
        skip = pytest.mark.skip(reason="Docker stack not running")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
