"""Discover which catalog models are *currently* available via the free/hosted endpoint,
since `/v1/models` lists the FULL catalog (including paid models, deprecated ones,
or non-chat models) without indicating status.

Strategy (common approach used by community scripts for NIM): send a minimal
request to /v1/chat/completions and classify by response:

    200 with "choices" -> valid response: currently hosted/free
    429               -> exists and hosted, but rate limited
    404/401/403        -> not a chat model, removed, or unauthorized
    other/timeout     -> ambiguous (large model cold start, 400 schema error, etc.)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

import httpx

PROBE_PAYLOAD_EXTRA = {
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Respond only with OK."},
    ],
    "max_tokens": 8,
}


class Status(str, Enum):
    FREE = "free"          # responded 200 with valid body
    RATE_LIMITED = "rate_limited"  # 429 -> exists and hosted
    UNAVAILABLE = "unavailable"    # 404/401/403/500
    AMBIGUOUS = "ambiguous"        # timeout, 400, 422, etc.

    @property
    def is_usable(self) -> bool:
        return self in (Status.FREE, Status.RATE_LIMITED)


@dataclass
class ProbeResult:
    model_id: str
    status: Status
    http_status: int


async def _probe_one(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    base_url: str,
    model_id: str,
    sem: asyncio.Semaphore,
) -> ProbeResult:
    payload = {"model": model_id, **PROBE_PAYLOAD_EXTRA}
    async with sem:
        try:
            resp = await client.post(
                f"{base_url}/chat/completions", headers=headers, json=payload
            )
        except (httpx.TimeoutException, httpx.TransportError):
            return ProbeResult(model_id, Status.AMBIGUOUS, 0)

    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            return ProbeResult(model_id, Status.AMBIGUOUS, resp.status_code)
        if "choices" in body or "model" in body:
            return ProbeResult(model_id, Status.FREE, resp.status_code)
        return ProbeResult(model_id, Status.AMBIGUOUS, resp.status_code)

    if resp.status_code == 429:
        return ProbeResult(model_id, Status.RATE_LIMITED, resp.status_code)

    if resp.status_code in (401, 403, 404, 500):
        return ProbeResult(model_id, Status.UNAVAILABLE, resp.status_code)

    return ProbeResult(model_id, Status.AMBIGUOUS, resp.status_code)


async def probe_all(
    model_ids: list[str],
    api_key: str,
    base_url: str,
    concurrency: int = 10,
    timeout: float = 8.0,
    on_result=None,
) -> list[ProbeResult]:
    """Test all model_ids concurrently (limited by `concurrency`).

    `on_result`, if provided, is called for each result (useful for progress bar).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    sem = asyncio.Semaphore(concurrency)
    results: list[ProbeResult] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(_probe_one(client, headers, base_url, mid, sem))
            for mid in model_ids
        ]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            if on_result:
                on_result(result)

    # preserve original catalog order in final output
    order = {mid: i for i, mid in enumerate(model_ids)}
    results.sort(key=lambda r: order[r.model_id])
    return results
