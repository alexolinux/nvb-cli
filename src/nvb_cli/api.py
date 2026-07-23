"""Cliente para a API OpenAI-compatible do NVIDIA Build (NIM).

Base URL: https://integrate.api.nvidia.com/v1
Docs: https://docs.api.nvidia.com/nim/docs/api-quickstart

Endpoints usados:
    GET  /v1/models            -> catálogo completo (não distingue free/pago)
    POST /v1/chat/completions  -> chat, com suporte a streaming (SSE)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

USER_AGENT = "nvb-cli/0.1.0 (+https://github.com/SEU_USUARIO/nvb-cli)"


class ApiError(RuntimeError):
    def __init__(self, status_code: int, message: str, body: str = ""):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")


class NvidiaClient:
    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0):
        if not api_key:
            raise ValueError("api_key vazio: rode `nvb auth set <SUA_CHAVE>` primeiro")
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        self._timeout = timeout

    # -- catálogo -----------------------------------------------------
    def list_models(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self.base_url}/models", headers=self._headers)
        if resp.status_code != 200:
            raise ApiError(resp.status_code, "falha ao listar modelos", resp.text)
        data = resp.json()
        models = data.get("data", [])
        # id, owned_by, created — nem todo modelo do catálogo aceita /chat/completions
        return sorted(models, key=lambda m: m.get("id", ""))

    # -- chat (resposta completa) --------------------------------------
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions", headers=self._headers, json=payload
            )
        if resp.status_code != 200:
            raise ApiError(resp.status_code, "falha na chamada de chat", resp.text)
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    # -- chat em streaming (SSE) ----------------------------------------
    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        with httpx.Client(timeout=self._timeout) as client, client.stream(
            "POST", f"{self.base_url}/chat/completions", headers=self._headers, json=payload
        ) as resp:
            if resp.status_code != 200:
                body = resp.read().decode(errors="replace")
                raise ApiError(resp.status_code, "falha na chamada de chat (stream)", body)

            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[len("data:") :].strip()
                if chunk == "[DONE]":
                    break
                try:
                    event = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = event.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield text
