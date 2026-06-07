import os

import pytest


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch, request):
    """Point LIT_CACHE_DIR at a fresh temp dir for every test (no shared state)."""
    monkeypatch.setenv("LIT_CACHE_DIR", str(tmp_path))
    # Strip the token for offline tests so they can't accidentally hit the network,
    # but keep it for integration tests, which need a live ADS connection.
    if request.node.get_closest_marker("integration") is None:
        monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    yield tmp_path
