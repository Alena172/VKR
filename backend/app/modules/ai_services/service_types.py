from __future__ import annotations

from typing import Protocol


class TranslationProviderUnavailableErrorLike(Protocol):
    def __call__(self, message: str) -> Exception: ...
