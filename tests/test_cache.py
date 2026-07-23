import importlib
import time

import nvb_cli.cache as cache_module


def test_save_and_load(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    importlib.reload(cache_module)

    cache_module.save({"meta/llama-3.1-8b-instruct": "free"}, base_url="https://example.test")
    data = cache_module.load(ttl_seconds=3600)

    assert data is not None
    assert data["results"]["meta/llama-3.1-8b-instruct"] == "free"


def test_expired_cache_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    importlib.reload(cache_module)

    cache_module.save({"m": "free"}, base_url="https://example.test")
    # TTL negativo == já expirado no mesmo instante
    assert cache_module.load(ttl_seconds=-1) is None


def test_clear(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    importlib.reload(cache_module)

    cache_module.save({"m": "free"}, base_url="https://example.test")
    cache_module.clear()
    assert cache_module.load(ttl_seconds=3600) is None
