from __future__ import annotations

import asyncio
import json
import re
from collections import deque

from app.core.config import get_settings
from app.modules.ai_services.chat_client import AIChatClient
from app.modules.ai_services.contracts import (
    AIStatusResponse,
    ExplainErrorRequest,
    ExplainErrorResponse,
    GenerateExercisesRequest,
    GenerateExercisesResponse,
    TranslateWithContextRequest,
)
from app.modules.ai_services.definition_resolver import DictionaryDefinitionResolver
from app.modules.ai_services.exercise_generator import ExerciseGenerator
from app.modules.ai_services.translation_service import TranslationService


class TranslationProviderUnavailableError(RuntimeError):
    pass


class AIService:
    """AI facade.

    Current implementation is deterministic and local.
    Keep public methods stable for future LLM provider integration.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._provider = settings.ai_provider.strip().lower()
        self._model = settings.ai_model
        self._timeout_seconds = settings.ai_timeout_seconds
        self._max_retries = max(0, int(settings.ai_max_retries))
        self._translation_strict_remote = bool(settings.translation_strict_remote)
        self._chat_client = AIChatClient(
            provider=self._provider,
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=self._max_retries,
        )
        self._definition_resolver = DictionaryDefinitionResolver()
        self._recent_sentences: dict[str, deque[str]] = {}
        self._translation_service = TranslationService(
            provider=self._provider,
            model=self._model,
            translation_strict_remote=self._translation_strict_remote,
            remote_enabled=self._remote_enabled,
            chat_complete_async=self._chat_completion_async,
            provider_unavailable_error=TranslationProviderUnavailableError,
        )
        self._exercise_generator = ExerciseGenerator(
            provider=self._provider,
            model=self._model,
            max_retries=self._max_retries,
            remote_enabled=self._remote_enabled,
            chat_complete_async=self._chat_completion_async,
            chat_complete_sync=self._chat_completion,
            provider_unavailable_error=TranslationProviderUnavailableError,
            translation_service=self._translation_service,
            definition_resolver=self._definition_resolver,
            recent_sentences=self._recent_sentences,
        )

    def _remote_enabled(self) -> bool:
        return self._chat_client.remote_enabled()

    def is_remote_enabled(self) -> bool:
        return self._remote_enabled()

    def _run_sync(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError("Synchronous AIService methods cannot be called from an active event loop")

    def _chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str | None:
        return self._run_sync(
            self._chat_completion_async(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

    async def _chat_completion_async(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str | None:
        return await self._chat_client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def get_status(self) -> AIStatusResponse:
        return AIStatusResponse(
            provider=self._provider,
            model=self._model,
            remote_enabled=self._remote_enabled(),
            base_url=self._chat_client.base_url,
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
        )

    def _fallback_explain_error(self) -> ExplainErrorResponse:
        return ExplainErrorResponse(
            explanation_ru=(
                "Ответ отличается от ожидаемого. Проверь форму слова, порядок слов "
                "и значение в контексте предложения."
            )
        )

    def _fallback_improvement_hint(self) -> ExplainErrorResponse:
        return ExplainErrorResponse(
            explanation_ru=(
                "Перевод засчитан как верный. Можно улучшить стиль: выбрать более нейтральную "
                "формулировку и терминологию ближе к учебному контексту."
            )
        )

    def explain_error(self, payload: ExplainErrorRequest) -> ExplainErrorResponse:
        return self._run_sync(self.explain_error_async(payload))

    async def explain_error_async(self, payload: ExplainErrorRequest) -> ExplainErrorResponse:
        content = await self._chat_completion_async(
            system_prompt=(
                "Ты преподаватель английского для русскоязычных пользователей. "
                "Давай короткое и понятное объяснение ошибки на русском."
            ),
            user_prompt=(
                f"Задание: {payload.english_prompt}\n"
                f"Ожидался ответ: {payload.expected_answer}\n"
                f"Ответ пользователя: {payload.user_answer}\n"
                "Сформулируй объяснение ошибки в 1-2 предложениях."
            ),
            temperature=0.1,
            max_tokens=180,
        )
        if content:
            return ExplainErrorResponse(explanation_ru=content)
        return self._fallback_explain_error()

    def suggest_improvement(self, payload: ExplainErrorRequest) -> ExplainErrorResponse:
        return self._run_sync(self.suggest_improvement_async(payload))

    async def suggest_improvement_async(self, payload: ExplainErrorRequest) -> ExplainErrorResponse:
        content = await self._chat_completion_async(
            system_prompt=(
                "Ты преподаватель английского для русскоязычных пользователей. "
                "Ответ пользователя уже считается правильным. "
                "Дай мягкую и краткую рекомендацию по стилю перевода на русском, без слова 'ошибка'."
            ),
            user_prompt=(
                f"Задание: {payload.english_prompt}\n"
                f"Ожидаемый вариант: {payload.expected_answer}\n"
                f"Вариант пользователя: {payload.user_answer}\n"
                "Сформулируй рекомендацию в 1-2 предложениях."
            ),
            temperature=0.1,
            max_tokens=180,
        )
        if content:
            return ExplainErrorResponse(explanation_ru=content)
        return self._fallback_improvement_hint()

    def is_translation_semantically_correct(
        self,
        *,
        english_prompt: str,
        expected_answer: str,
        user_answer: str,
    ) -> bool:
        return self._run_sync(
            self.is_translation_semantically_correct_async(
                english_prompt=english_prompt,
                expected_answer=expected_answer,
                user_answer=user_answer,
            )
        )

    async def is_translation_semantically_correct_async(
        self,
        *,
        english_prompt: str,
        expected_answer: str,
        user_answer: str,
    ) -> bool:
        content = await self._chat_completion_async(
            system_prompt=(
                "Ты проверяешь переводы с английского на русский. "
                "Если пользовательский перевод передает тот же основной смысл, считай его правильным, "
                "даже если стиль неидеален или слова отличаются. "
                "Незначительные стилистические огрехи не делают ответ неправильным. "
                "Верни только JSON: {\"equivalent\": true|false}."
            ),
            user_prompt=(
                f"Исходное задание: {english_prompt}\n"
                f"Эталонный перевод: {expected_answer}\n"
                f"Перевод пользователя: {user_answer}\n"
                "Сравни смысл."
            ),
            temperature=0.0,
            max_tokens=60,
        )
        if content:
            payload = self._extract_json_payload(content)
            if isinstance(payload, dict) and isinstance(payload.get("equivalent"), bool):
                return payload["equivalent"]
            lowered = content.lower()
            if "true" in lowered:
                return True
            if "false" in lowered:
                return False
        return False

    def _fallback_context_definition(
        self,
        *,
        english_lemma: str,
        russian_translation: str,
        source_sentence: str | None,
    ) -> str:
        if source_sentence:
            return (
                f"In this context, '{english_lemma}' means '{russian_translation}' in Russian. "
                f"Example context: {source_sentence.strip()}"
            )
        return (
            f"'{english_lemma}' means '{russian_translation}' in Russian in the intended learning context."
        )

    def generate_context_definition(
        self,
        *,
        english_lemma: str,
        russian_translation: str,
        source_sentence: str | None,
        cefr_level: str | None = None,
    ) -> str:
        return self._run_sync(
            self.generate_context_definition_async(
                english_lemma=english_lemma,
                russian_translation=russian_translation,
                source_sentence=source_sentence,
                cefr_level=cefr_level,
            )
        )

    async def generate_context_definition_async(
        self,
        *,
        english_lemma: str,
        russian_translation: str,
        source_sentence: str | None,
        cefr_level: str | None = None,
    ) -> str:
        content = await self._chat_completion_async(
            system_prompt=(
                "You are an English lexicography assistant. "
                "Write a complete and precise definition of the English word sense from the context. "
                "Write in English only, 1-2 sentences, concise and clear."
            ),
            user_prompt=(
                f"Word: {english_lemma}\n"
                f"Russian translation: {russian_translation}\n"
                f"Context: {source_sentence or 'not provided'}\n"
                f"CEFR: {cefr_level or 'unknown'}\n"
                "Return only the English definition for this sense."
            ),
            temperature=0.1,
            max_tokens=220,
        )
        if content:
            cleaned = content.strip().strip('"')
            if len(cleaned) >= 20:
                return cleaned
        return self._fallback_context_definition(
            english_lemma=english_lemma,
            russian_translation=russian_translation,
            source_sentence=source_sentence,
        )

    def translate_with_context(
        self,
        payload: TranslateWithContextRequest,
    ) -> TranslateWithContextResponse:
        return self._run_sync(self.translate_with_context_async(payload))

    async def translate_with_context_async(
        self,
        payload: TranslateWithContextRequest,
    ) -> TranslateWithContextResponse:
        return await self._translation_service.translate_with_context_async(payload)

    def _extract_json_payload(self, raw: str) -> dict | list | None:
        text = raw.strip()
        if not text:
            return None

        try:
            return json.loads(text)
        except Exception:
            pass

        fenced = re.search(r"```json\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except Exception:
                return None
        return None

    def generate_exercises(
        self,
        payload: GenerateExercisesRequest,
    ) -> GenerateExercisesResponse:
        return self._run_sync(self.generate_exercises_async(payload))

    async def generate_exercises_async(
        self,
        payload: GenerateExercisesRequest,
    ) -> GenerateExercisesResponse:
        return await self._exercise_generator.generate_exercises_async(payload)

    async def generate_exercises_batch(
        self,
        batches: list[GenerateExercisesRequest],
    ) -> list[GenerateExercisesResponse]:
        return await self._exercise_generator.generate_exercises_batch(batches)


ai_service = AIService()
