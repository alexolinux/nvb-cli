import importlib

import nvb_cli.config as config_module


def test_set_and_get_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv(config_module.ENV_VAR, raising=False)
    importlib.reload(config_module)

    config_module.set_api_key("nvapi-abc123")
    assert config_module.get_api_key() == "nvapi-abc123"


def test_env_var_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    importlib.reload(config_module)

    config_module.set_api_key("nvapi-from-file")
    monkeypatch.setenv(config_module.ENV_VAR, "nvapi-from-env")
    assert config_module.get_api_key() == "nvapi-from-env"


def test_mask_key():
    masked = config_module.mask_key("nvapi-1234567890abcdef")
    assert masked.startswith("nvapi-1")
    assert masked.endswith("cdef")
    assert "1234567890ab" not in masked
