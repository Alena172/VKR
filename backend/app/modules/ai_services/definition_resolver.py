from __future__ import annotations

import httpx


class DictionaryDefinitionResolver:
    def __init__(self, *, timeout_seconds: float = 2.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._cache: dict[str, str] = {}
        self._async_client: httpx.AsyncClient | None = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self._timeout_seconds)
        return self._async_client

    async def resolve(self, word: str, translation: str) -> str:
        key = word.lower().strip()
        if not key:
            return f"A word translated as {translation}."
        if key in self._cache:
            return self._cache[key]

        definition: str | None = None
        try:
            client = self._get_async_client()
            response = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{key}")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings", [])
                    if meanings and meanings[0].get("definitions"):
                        definition = meanings[0]["definitions"][0].get("definition")
        except Exception:
            definition = None

        if not definition:
            definition = f"A word that means '{translation}' in Russian."

        self._cache[key] = definition
        return definition
