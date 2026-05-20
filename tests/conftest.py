"""Shared fixtures and markers for the test suite."""

import pytest
import requests


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
