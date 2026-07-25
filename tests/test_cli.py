import json
from click.testing import CliRunner
import respx
import httpx

from nvb_cli.cli import main
import nvb_cli.config as config_module
from nvb_cli.probe import Status

BASE_URL = "https://integrate.api.nvidia.com/v1"


@respx.mock
def test_models_free_table(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    config_module.set_api_key("nvapi-testkey1234567890")

    # Mock catalog
    respx.get(f"{BASE_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "meta/llama-3.3-70b-instruct"}]})
    )
    # Mock chat probe
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    )

    runner = CliRunner()
    result = runner.invoke(main, ["models", "free", "--refresh"])
    assert result.exit_code == 0
    assert "meta/llama-3.3-70b-instruct" in result.output
    assert BASE_URL in result.output
    assert "Base URL" in result.output


@respx.mock
def test_models_free_json(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    config_module.set_api_key("nvapi-testkey1234567890")

    respx.get(f"{BASE_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "meta/llama-3.3-70b-instruct"}]})
    )
    respx.post(f"{BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    )

    runner = CliRunner()
    result = runner.invoke(main, ["models", "free", "--refresh", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["base_url"] == BASE_URL
    assert "meta/llama-3.3-70b-instruct" in data["free_or_hosted"]
