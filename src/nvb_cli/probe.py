"""Descobre quais modelos do catálogo estão *atualmente* disponíveis via endpoint
free/hosted, já que `/v1/models` lista TODO o catálogo (incluindo modelos pagos,
retirados, ou que não são de chat) sem sinalizar isso.

Estratégia (mesma ideia usada por scripts da comunidade para o NIM): mandar uma
requisição mínima para /v1/chat/completions e classificar pela resposta:

    200 com "choices" -> respondeu de verdade: hospedado/free agora
    429               -> existe e está hospedado, só bateu rate limit
    404/401/403        -> não é um modelo de chat, foi removido, ou sem permissão
    outros/timeout      -> ambíguo (modelo grande "esfriado", 400 de schema, etc.)
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
    FREE = "free"          # respondeu 200 com corpo válido
    RATE_LIMITED = "rate_limited"  # 429 -> existe e está hospedado
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
    """Testa todos os model_ids concorrentemente (limitado por `concurrency`).

    `on_result`, se fornecido, é chamado a cada resultado (útil para barra de progresso).
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

    # mantém a ordem original do catálogo na saída final
    order = {mid: i for i, mid in enumerate(model_ids)}
    results.sort(key=lambda r: order[r.model_id])
    return results
