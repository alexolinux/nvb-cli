import httpx
import pytest
import respx

from nvb_cli.probe import Status, probe_all

BASE_URL = "https://integrate.api.nvidia.com/v1"


@pytest.mark.asyncio
@respx.mock
async def test_probe_all_classifies_statuses():
    respx.post(f"{BASE_URL}/chat/completions").mock(
        side_effect=lambda request: _fake_response(request)
    )

    results = await probe_all(
        model_ids=["free/model", "busy/model", "gone/model", "weird/model"],
        api_key="nvapi-test",
        base_url=BASE_URL,
        concurrency=4,
        timeout=2.0,
    )

    by_id = {r.model_id: r.status for r in results}
    assert by_id["free/model"] == Status.FREE
    assert by_id["busy/model"] == Status.RATE_LIMITED
    assert by_id["gone/model"] == Status.UNAVAILABLE
    assert by_id["weird/model"] == Status.AMBIGUOUS


def _fake_response(request: httpx.Request) -> httpx.Response:
    import json

    body = json.loads(request.content)
    model = body["model"]

    if model == "free/model":
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
    if model == "busy/model":
        return httpx.Response(429, json={"error": "rate limited"})
    if model == "gone/model":
        return httpx.Response(404, json={"error": "not found"})
    return httpx.Response(400, json={"error": "bad request"})
