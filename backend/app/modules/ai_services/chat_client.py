from __future__ import annotations

import httpx


class AIChatClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, int(max_retries))
        self._async_client: httpx.AsyncClient | None = None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def remote_enabled(self) -> bool:
        if self._provider == "openai_compatible":
            return bool(self._api_key)
        if self._provider == "ollama":
            return bool(self._base_url) and bool(self._model)
        return False

    def _build_chat_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._provider == "openai_compatible" and self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._async_client

    async def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str | None:
        if not self.remote_enabled():
            return None

        payload = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        client = self._get_async_client()
        url = f"{self._base_url}/chat/completions"
        headers = self._build_chat_headers()

        for _ in range(self._max_retries + 1):
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                ) or None
            except Exception:
                continue
        return None
