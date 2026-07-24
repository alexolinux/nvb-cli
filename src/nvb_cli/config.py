"""Read/write local configuration (~/.config/nvb-cli/config.toml).

API key precedence:
    1. Environment variable NVIDIA_API_KEY
    2. Saved config file via `nvb auth set`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import tomli_w
from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

APP_NAME = "nvb-cli"
ENV_VAR = "NVIDIA_API_KEY"
BASE_URL_ENV_VAR = "NVB_BASE_URL"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"


def config_dir() -> Path:
    d = Path(user_config_dir(APP_NAME))
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return config_dir() / "config.toml"


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def save_config(data: dict) -> None:
    path = config_file()
    with path.open("wb") as f:
        tomli_w.dump(data, f)
    # Sensitive key: restrict file permissions (best-effort, no-op on Windows)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_api_key() -> str | None:
    env_key = os.environ.get(ENV_VAR)
    if env_key:
        return env_key.strip()
    return load_config().get("api_key")


def set_api_key(key: str) -> None:
    data = load_config()
    data["api_key"] = key.strip()
    save_config(data)


def clear_api_key() -> None:
    data = load_config()
    data.pop("api_key", None)
    save_config(data)


def get_base_url() -> str:
    return os.environ.get(BASE_URL_ENV_VAR) or load_config().get("base_url", DEFAULT_BASE_URL)


def mask_key(key: str) -> str:
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:7]}{'*' * (len(key) - 11)}{key[-4:]}"
