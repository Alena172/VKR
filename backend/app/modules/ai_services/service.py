from __future__ import annotations

import asyncio
import json
import random
import re
import secrets
from collections import Counter, deque

import httpx

from app.core.config import get_settings
from app.modules.ai_services.contracts import (
    AIStatusResponse,
    ExplainErrorRequest,
    ExplainErrorResponse,
    GenerateExercisesRequest,
    GenerateExercisesResponse,
    GeneratedExerciseItem,
    TranslateWithContextRequest,
    TranslateWithContextResponse,
    TranslateGlossaryItem,
)


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
        self._base_url = settings.ai_base_url.rstrip("/")
        self._api_key = settings.ai_api_key
        self._model = settings.ai_model
        self._timeout_seconds = settings.ai_timeout_seconds
        self._max_retries = max(0, int(settings.ai_max_retries))
        self._translation_strict_remote = bool(settings.translation_strict_remote)
        self._async_client: httpx.AsyncClient | None = None
        self._definition_cache: dict[str, str] = {}
        self._recent_sentences: dict[str, deque[str]] = {}

    def _remote_enabled(self) -> bool:
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

    def is_remote_enabled(self) -> bool:
        return self._remote_enabled()

    def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client for AI requests."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._async_client

    def _chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str | None:
        if not self._remote_enabled():
            return None

        url = f"{self._base_url}/chat/completions"
        headers = self._build_chat_headers()
        payload = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        attempts = self._max_retries + 1
        for _ in range(attempts):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
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

    async def _chat_completion_async(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> str | None:
        """Async version of chat completion."""
        if not self._remote_enabled():
            return None

        url = f"{self._base_url}/chat/completions"
        headers = self._build_chat_headers()
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
        attempts = self._max_retries + 1
        
        for _ in range(attempts):
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

    def get_status(self) -> AIStatusResponse:
        return AIStatusResponse(
            provider=self._provider,
            model=self._model,
            remote_enabled=self._remote_enabled(),
            base_url=self._base_url,
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
        content = self._chat_completion(
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
        content = self._chat_completion(
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
        content = self._chat_completion(
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
        content = self._chat_completion(
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

    def _fallback_translate_with_context(
        self,
        payload: TranslateWithContextRequest,
    ) -> TranslateWithContextResponse:
        translated = self._heuristic_translate(
            payload.text,
            payload.source_context,
            payload.glossary,
        )
        level_note = f" CEFR={payload.cefr_level}." if payload.cefr_level else ""
        context_note = " Context applied." if payload.source_context else ""
        return TranslateWithContextResponse(
            translated_text=translated,
            provider_note=f"local_heuristic EN->RU.{context_note}{level_note}",
        )

    def _tokenize(self, text: str) -> list[str]:
        return [part for part in re.split(r"[^a-zA-Z']+", text.lower()) if part]

    def _normalize_english_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return normalized

    def _normalize_token(self, token: str) -> str:
        irregular = {
            "children": "child",
            "men": "man",
            "women": "woman",
            "mice": "mouse",
            "went": "go",
            "gone": "go",
            "seen": "see",
            "saw": "see",
            "done": "do",
            "did": "do",
            "was": "be",
            "were": "be",
            "is": "be",
            "are": "be",
            "am": "be",
            "has": "have",
            "had": "have",
        }
        if token in irregular:
            return irregular[token]
        if token.endswith("ies") and len(token) > 3:
            return token[:-3] + "y"
        if token.endswith("ing") and len(token) > 5:
            stem = token[:-3]
            if len(stem) >= 2 and stem[-1] == stem[-2]:
                stem = stem[:-1]
            return stem
        if token.endswith("ed") and len(token) > 4:
            stem = token[:-2]
            if stem.endswith("i"):
                stem = stem[:-1] + "y"
            return stem
        if token.endswith("es") and len(token) > 4:
            return token[:-2]
        if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
            return token[:-1]
        return token

    def _resolve_glossary_translation(
        self,
        text: str,
        context: str | None,
        glossary: list[TranslateGlossaryItem],
    ) -> str | None:
        if not glossary:
            return None

        text_normalized = self._normalize_english_text(text)
        context_tokens = set(self._tokenize(context or ""))
        text_tokens = self._tokenize(text_normalized)
        normalized_text_tokens = {self._normalize_token(token) for token in text_tokens}

        exact_matches: list[TranslateGlossaryItem] = []
        token_matches: list[tuple[int, TranslateGlossaryItem]] = []

        for item in glossary:
            term = self._normalize_english_text(item.english_term)
            if not term:
                continue
            if term == text_normalized:
                exact_matches.append(item)
                continue

            term_tokens = self._tokenize(term)
            term_norm_tokens = {self._normalize_token(token) for token in term_tokens}
            if len(term_norm_tokens) == 1 and term_norm_tokens.intersection(normalized_text_tokens):
                score = 0
                source_tokens = set(self._tokenize(item.source_sentence or ""))
                if context_tokens and source_tokens:
                    score = len(context_tokens.intersection(source_tokens))
                token_matches.append((score, item))

        if exact_matches:
            if len(exact_matches) == 1:
                return exact_matches[0].russian_translation
            scored = sorted(
                exact_matches,
                key=lambda row: len(context_tokens.intersection(set(self._tokenize(row.source_sentence or "")))),
                reverse=True,
            )
            return scored[0].russian_translation

        if token_matches:
            token_matches.sort(key=lambda pair: pair[0], reverse=True)
            return token_matches[0][1].russian_translation

        return None

    def _pick_contextual_translation(
        self,
        text: str,
        context: str | None,
        glossary: list[TranslateGlossaryItem] | None = None,
    ) -> str | None:
        glossary_translation = self._resolve_glossary_translation(text, context, glossary or [])
        if glossary_translation:
            return glossary_translation

        direct_map = {
            "apple": "яблоко",
            "pear": "груша",
            "through": "через",
            "book": "книга",
            "language": "язык",
            "word": "слово",
            "sentence": "предложение",
            "learn": "изучать",
            "study": "учиться",
            "speak": "говорить",
            "read": "читать",
            "write": "писать",
            "practice": "практиковать",
            "translate": "переводить",
            "hello": "привет",
            "world": "мир",
            "good": "хороший",
            "bad": "плохой",
            "small": "маленький",
            "big": "большой",
            "fast": "быстрый",
            "slow": "медленный",
            "home": "дом",
            "school": "школа",
            "work": "работа",
            "friend": "друг",
            "time": "время",
            "day": "день",
            "night": "ночь",
            "today": "сегодня",
            "tomorrow": "завтра",
            "yesterday": "вчера",
        }
        ambiguous_map = {
            "right": {
                "left": "право",
                "correct": "правильный",
                "answer": "правильный",
            },
            "light": {
                "lamp": "свет",
                "dark": "свет",
                "weight": "легкий",
            },
            "book": {
                "read": "книга",
                "page": "книга",
                "ticket": "забронировать",
                "hotel": "забронировать",
            },
            "watch": {
                "movie": "смотреть",
                "video": "смотреть",
                "time": "часы",
            },
        }
        phrase_map = {
            "look up": "искать",
            "find out": "выяснить",
            "turn on": "включить",
            "turn off": "выключить",
            "go on": "продолжать",
            "pick up": "подбирать",
        }

        lowered = text.strip().lower()
        for phrase, translated in phrase_map.items():
            if lowered == phrase:
                return translated

        tokens = self._tokenize(lowered)
        if not tokens:
            return None
        norm_tokens = [self._normalize_token(token) for token in tokens]
        key = norm_tokens[0] if len(norm_tokens) == 1 else " ".join(norm_tokens)
        if key in direct_map:
            return direct_map[key]

        if len(norm_tokens) == 1 and norm_tokens[0] in ambiguous_map:
            context_tokens = set(self._tokenize(context or ""))
            variants = ambiguous_map[norm_tokens[0]]
            for trigger, translated in variants.items():
                if trigger in context_tokens:
                    return translated
        return None

    def _heuristic_translate(
        self,
        text: str,
        context: str | None,
        glossary: list[TranslateGlossaryItem] | None = None,
    ) -> str:
        picked = self._pick_contextual_translation(text, context, glossary)
        if picked:
            return picked

        tokens = self._tokenize(text)
        if not tokens:
            return text.strip() or "перевод не найден"
        normalized = [self._normalize_token(token) for token in tokens]
        counts = Counter(normalized)
        if len(counts) == 1:
            only = next(iter(counts))
            fallback = self._pick_contextual_translation(only, context, glossary)
            if fallback:
                return fallback
            return only
        mapped = [self._pick_contextual_translation(token, context, glossary) or token for token in normalized]
        return " ".join(mapped)

    def translate_with_context(
        self,
        payload: TranslateWithContextRequest,
    ) -> TranslateWithContextResponse:
        if self._translation_strict_remote and not self._remote_enabled():
            raise TranslationProviderUnavailableError(
                "Translation provider is unavailable. "
                "Use AI_PROVIDER=ollama or set AI_PROVIDER=openai_compatible with AI_API_KEY."
            )

        glossary_json = json.dumps(
            [
                {
                    "english_term": item.english_term,
                    "russian_translation": item.russian_translation,
                    "source_sentence": item.source_sentence,
                }
                for item in payload.glossary[:200]
            ],
            ensure_ascii=False,
        )
        content = self._chat_completion(
            system_prompt=(
                "Ты переводчик EN->RU для русскоязычного студента английского. "
                "Всегда учитывай контекст и пользовательский глоссарий. "
                "Если термин есть в глоссарии и подходит по контексту, используй перевод из глоссария. "
                "Верни только итоговый перевод на русском без комментариев. "
                "Если входной текст это одно слово или короткая фраза, верни только перевод этого слова/фразы, "
                "а не полное предложение."
            ),
            user_prompt=(
                f"Текст: {payload.text}\n"
                f"Уровень CEFR: {payload.cefr_level or 'unknown'}\n"
                f"Контекст: {payload.source_context or 'none'}\n"
                f"Глоссарий пользователя (JSON): {glossary_json}\n"
                "Формат ответа: только перевод, без пояснений и без исходного текста."
            ),
            temperature=0.0,
            max_tokens=220,
        )
        if content:
            return TranslateWithContextResponse(
                translated_text=content.strip().strip('"'),
                provider_note=f"remote:{self._provider}/{self._model};glossary={len(payload.glossary)}",
            )
        if self._translation_strict_remote:
            raise TranslationProviderUnavailableError(
                "Translation provider request failed. Check AI_BASE_URL, AI_MODEL, AI_API_KEY and provider availability."
            )
        return self._fallback_translate_with_context(payload)

    async def translate_with_context_async(
        self,
        payload: TranslateWithContextRequest,
    ) -> TranslateWithContextResponse:
        """Async version of translate_with_context."""
        if self._translation_strict_remote and not self._remote_enabled():
            raise TranslationProviderUnavailableError(
                "Translation provider is unavailable. "
                "Use AI_PROVIDER=ollama or set AI_PROVIDER=openai_compatible with AI_API_KEY."
            )

        glossary_json = json.dumps(
            [
                {
                    "english_term": item.english_term,
                    "russian_translation": item.russian_translation,
                    "source_sentence": item.source_sentence,
                }
                for item in payload.glossary[:200]
            ],
            ensure_ascii=False,
        )
        content = await self._chat_completion_async(
            system_prompt=(
                "Ты переводчик EN->RU для русскоязычного студента английского. "
                "Всегда учитывай контекст и пользовательский глоссарий. "
                "Если термин есть в глоссарии и подходит по контексту, используй перевод из глоссария. "
                "Верни только итоговый перевод на русском без комментариев. "
                "Если входной текст это одно слово или короткая фраза, верни только перевод этого слова/фразы, "
                "а не полное предложение."
            ),
            user_prompt=(
                f"Текст: {payload.text}\n"
                f"Уровень CEFR: {payload.cefr_level or 'unknown'}\n"
                f"Контекст: {payload.source_context or 'none'}\n"
                f"Глоссарий пользователя (JSON): {glossary_json}\n"
                "Формат ответа: только перевод, без пояснений и без исходного текста."
            ),
            temperature=0.0,
            max_tokens=220,
        )
        if content:
            return TranslateWithContextResponse(
                translated_text=content.strip().strip('"'),
                provider_note=f"remote:{self._provider}/{self._model};glossary={len(payload.glossary)}",
            )
        if self._translation_strict_remote:
            raise TranslationProviderUnavailableError(
                "Translation provider request failed. Check AI_BASE_URL, AI_MODEL, AI_API_KEY and provider availability."
            )
        return self._fallback_translate_with_context(payload)

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

    def _is_word_scramble_suitable(self, word: str) -> bool:
        clean_word = word.strip().lower()
        if len(clean_word) < 3 or len(clean_word) > 15:
            return False
        return clean_word.isalpha()

    def _build_word_scramble_letters(self, answer: str) -> list[str]:
        clean = answer.strip().lower()
        if not self._is_word_scramble_suitable(clean):
            return []

        letters = list(clean)
        scrambled = letters.copy()
        seeded_random = random.Random(clean)

        for _ in range(10):
            seeded_random.shuffle(scrambled)
            if scrambled != letters:
                break

        if scrambled == letters and len(scrambled) >= 2:
            i, j = 0, len(scrambled) - 1
            scrambled[i], scrambled[j] = scrambled[j], scrambled[i]

        return [char.upper() for char in scrambled]

    def _build_sentence_for_word(self, seed: ExerciseSeed, cefr_level: str | None = None) -> str:
        # Sentence generation is remote-only (no local templates/fallback).
        if not self._remote_enabled():
            raise TranslationProviderUnavailableError(
                "Sentence generation requires remote AI provider. "
                "Use AI_PROVIDER=ollama or set AI_PROVIDER=openai_compatible with AI_API_KEY."
            )

        word = seed.english_lemma.strip().lower()
        level = (cefr_level or "A2").upper()
        remote_sentence = self._generate_sentence_with_remote(word=word, cefr_level=level)
        if remote_sentence:
            return remote_sentence

        raise TranslationProviderUnavailableError(
            "Sentence generation request failed. "
            "Check AI_BASE_URL, AI_MODEL and provider availability."
        )

    def _sentence_word_limits(self, cefr_level: str) -> tuple[int, int]:
        if cefr_level in {"A1", "A2"}:
            return (6, 18)
        if cefr_level in {"B1", "B2"}:
            return (8, 24)
        return (10, 28)

    def _is_sentence_suitable(self, sentence: str, target_word: str, cefr_level: str) -> bool:
        text = re.sub(r"\s+", " ", sentence.strip())
        if not text:
            return False
        # Single sentence, no list-like output.
        if text.count(".") + text.count("!") + text.count("?") > 2:
            return False
        # Must include target word (case-insensitive, whole token or quoted token).
        if not re.search(rf"\b{re.escape(target_word)}\b", text, flags=re.IGNORECASE):
            return False

        min_words, max_words = self._sentence_word_limits(cefr_level)
        words = re.findall(r"[A-Za-z']+", text)
        if len(words) < min_words or len(words) > max_words:
            return False

        # Avoid exotic proper nouns and niche narratives for training baseline.
        disallowed_tokens = {"africa", "mars", "wizard", "dragon", "kingdom", "galaxy"}
        lowered = {token.lower() for token in words}
        if lowered.intersection(disallowed_tokens):
            return False
        return True

    def _generate_sentence_with_remote(self, word: str, cefr_level: str) -> str | None:
        history = self._recent_sentences.setdefault(word, deque(maxlen=8))
        for _ in range(self._max_retries + 2):
            content = self._chat_completion(
                system_prompt=(
                    "You are an English teacher. Generate one natural, high-frequency, grammatically correct "
                    "English sentence for a Russian-speaking learner. "
                    "Use plain modern spoken/written English and avoid bookish phrasing."
                ),
                user_prompt=(
                    f"Target word: {word}\n"
                    f"CEFR level: {cefr_level}\n"
                    f"Avoid repeating these recent sentences: {json.dumps(list(history), ensure_ascii=False)}\n"
                    "Constraints:\n"
                    "- one sentence only\n"
                    "- everyday context (home, study, work, shopping, transport)\n"
                    "- avoid fantasy, rare names, unusual locations\n"
                    "- include the target word exactly once\n"
                    "- prefer short natural collocations used by natives\n"
                    "- avoid stiff phrases like 'during the quiet hours' and similar literary wording\n"
                    "- do not use markdown, quotes, bullets, numbering\n"
                    "- output sentence only"
                ),
                temperature=0.2,
                max_tokens=80,
            )
            if not content:
                continue
            candidate = self._sanitize_generated_sentence(content)
            if self._is_sentence_suitable(candidate, word, cefr_level) and candidate not in history:
                history.append(candidate)
                return candidate
        return None

    def _sanitize_generated_sentence(self, text: str) -> str:
        candidate = text.strip().strip('"').strip("'")
        candidate = candidate.replace("**", "").replace("__", "").replace("`", "")
        candidate = re.sub(r"\s+", " ", candidate).strip()
        return candidate

    def _build_ru_translation_of_sentence(self, sentence_en: str, seed: ExerciseSeed) -> str:
        if self._remote_enabled():
            content = self._chat_completion(
                system_prompt=(
                    "Переведи английское предложение на русский. "
                    "Верни только перевод без комментариев."
                ),
                user_prompt=(
                    f"Предложение: {sentence_en}\n"
                    f"Ключевое слово: {seed.english_lemma}\n"
                    f"Желаемый перевод ключевого слова: {seed.russian_translation}"
                ),
                temperature=0.0,
                max_tokens=140,
            )
            if content:
                return content.strip().strip('"')
        # Local fallback: translate sentence token-by-token and force glossary mapping
        # for the target lemma to avoid technical placeholders in the UI/tests.
        translated = self._heuristic_translate(
            sentence_en,
            sentence_en,
            [
                TranslateGlossaryItem(
                    english_term=seed.english_lemma,
                    russian_translation=seed.russian_translation,
                    source_sentence=seed.source_sentence,
                )
            ],
        )
        return translated or seed.russian_translation

    def _get_word_definition(self, word: str, translation: str) -> str:
        key = word.lower().strip()
        if not key:
            return f"A word translated as {translation}."
        if key in self._definition_cache:
            return self._definition_cache[key]

        definition: str | None = None
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{key}")
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

        self._definition_cache[key] = definition
        return definition

    def _build_word_definition_match_exercise(self, seed: ExerciseSeed, pool: list[ExerciseSeed]) -> GeneratedExerciseItem:
        selected_words: list[ExerciseSeed] = []
        seen: set[str] = set()
        for candidate in [seed] + pool:
            key = candidate.english_lemma.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            selected_words.append(candidate)
            if len(selected_words) == 4:
                break

        if len(selected_words) < 4:
            # Caller should guarantee minimum vocabulary, but keep safe fallback.
            return self._build_sentence_translation_exercise(seed)

        pairs = [
            {
                "word": item.english_lemma.strip().lower(),
                "definition": self._get_word_definition(item.english_lemma, item.russian_translation),
            }
            for item in selected_words
        ]
        definitions = [pair["definition"] for pair in pairs]
        random.Random("|".join(pair["word"] for pair in pairs)).shuffle(definitions)
        prompt_words = " - ".join([f"{idx}. {pair['word']}" for idx, pair in enumerate(pairs, start=1)])
        return GeneratedExerciseItem(
            prompt=f"Match each word with its definition: {prompt_words}",
            answer=json.dumps(pairs, ensure_ascii=False),
            exercise_type="word_definition_match",
            options=definitions,
        )

    def _build_sentence_translation_exercise(self, seed: ExerciseSeed, cefr_level: str | None = None) -> GeneratedExerciseItem:
        sentence_en = self._build_sentence_for_word(seed, cefr_level=cefr_level)
        sentence_ru = self._build_ru_translation_of_sentence(sentence_en, seed)
        return GeneratedExerciseItem(
            prompt=f"Translate sentence into Russian: {sentence_en}",
            answer=sentence_ru,
            exercise_type="sentence_translation_full",
            options=[],
        )

    def _build_word_scramble_exercise(self, seed: ExerciseSeed, cefr_level: str | None = None) -> GeneratedExerciseItem:
        letters = self._build_word_scramble_letters(seed.english_lemma)
        if not letters:
            return self._build_sentence_translation_exercise(seed, cefr_level=cefr_level)
        return GeneratedExerciseItem(
            prompt=f"Assemble the word from letters. Translation hint: {seed.russian_translation}",
            answer=seed.english_lemma,
            exercise_type="word_scramble",
            options=letters,
        )

    def _fallback_generate_exercises(
        self,
        payload: GenerateExercisesRequest,
    ) -> GenerateExercisesResponse:
        result: list[GeneratedExerciseItem] = []
        seeds = payload.seeds[:]
        if not seeds:
            return GenerateExercisesResponse(
                exercises=[],
                provider_note="local_heuristic exercise_generation.empty_vocabulary",
            )

        idx = 0
        while len(result) < payload.size:
            seed = seeds[idx % len(seeds)]
            idx += 1
            if payload.mode == "word_scramble":
                result.append(self._build_word_scramble_exercise(seed, cefr_level=payload.cefr_level))
            elif payload.mode == "word_definition_match":
                start = (idx - 1) % len(seeds)
                rotated_pool = seeds[start:] + seeds[:start]
                result.append(self._build_word_definition_match_exercise(seed, rotated_pool))
            else:
                result.append(self._build_sentence_translation_exercise(seed, cefr_level=payload.cefr_level))

        level_note = f" CEFR={payload.cefr_level}." if payload.cefr_level else ""
        if payload.mode == "sentence_translation_full":
            provider_note = f"remote_sentence_pipeline:{self._provider}/{self._model}{level_note}"
        else:
            provider_note = f"local_heuristic exercise_generation.{level_note}"
        return GenerateExercisesResponse(
            exercises=result,
            provider_note=provider_note,
        )

    def _parse_generated_exercises(
        self,
        raw_content: str,
        size: int,
    ) -> list[GeneratedExerciseItem]:
        payload = self._extract_json_payload(raw_content)
        if payload is None:
            return []

        if isinstance(payload, dict):
            exercises_raw = payload.get("exercises", [])
        elif isinstance(payload, list):
            exercises_raw = payload
        else:
            exercises_raw = []

        parsed: list[GeneratedExerciseItem] = []
        for item in exercises_raw:
            if not isinstance(item, dict):
                continue
            prompt = str(item.get("prompt", "")).strip()
            answer = str(item.get("answer", "")).strip()
            exercise_type = str(item.get("exercise_type", "translation")).strip() or "translation"
            raw_options = item.get("options", [])
            options = [str(opt).strip() for opt in raw_options if str(opt).strip()] if isinstance(raw_options, list) else []
            if not prompt or not answer:
                continue
            if exercise_type in {"gap_fill", "assemble_word"}:
                exercise_type = "word_scramble"
                if not options:
                    options = self._build_word_scramble_letters(answer)
            if exercise_type in {"multiple_choice", "definition_match"}:
                exercise_type = "word_definition_match"
            if exercise_type in {"translation", "en_to_ru", "ru_to_en"}:
                exercise_type = "sentence_translation_full"
            if exercise_type == "word_definition_match":
                # We only support single-word definition match in current UI.
                # Reject multi-word matching payloads from remote AI and fallback to local generation.
                has_numbered_list = bool(re.search(r"\b1\.\s", prompt)) or bool(re.search(r"\b2\.\s", prompt))
                has_many_dash_fragments = prompt.count(" - ") >= 2
                if has_numbered_list or has_many_dash_fragments:
                    continue
                if not options or answer not in options:
                    continue
            if exercise_type == "word_scramble":
                normalized_answer = answer.strip().lower()
                valid_letter_options = (
                    len(options) == len(normalized_answer)
                    and all(len(opt) == 1 and opt.isalpha() for opt in options)
                )
                if not valid_letter_options:
                    options = self._build_word_scramble_letters(normalized_answer)
            parsed.append(
                GeneratedExerciseItem(
                    prompt=prompt,
                    answer=answer,
                    exercise_type=exercise_type,
                    options=options,
                )
            )
            if len(parsed) >= size:
                break
        return parsed

    def generate_exercises(
        self,
        payload: GenerateExercisesRequest,
    ) -> GenerateExercisesResponse:
        # Sentence translation uses dedicated generation pipeline for reliability
        # and strict CEFR/context constraints.
        if payload.mode == "sentence_translation_full":
            return self._fallback_generate_exercises(payload)

        # For definition match we use deterministic local generation to keep strict 4x4 matching UX.
        if payload.mode == "word_definition_match":
            return self._fallback_generate_exercises(payload)

        seeds_with_context = [
            {
                "word": seed.english_lemma,
                "translation": seed.russian_translation,
            }
            for seed in payload.seeds
        ]

        content = self._chat_completion(
            system_prompt=(
                "Ты продвинутый AI-тьютор. Твоя задача создавать уникальные упражнения. "
                "Создавай новые предложения, не копируя предложения из пользовательского контекста. "
                "Никогда не повторяй одно и то же задание дважды. "
                "Типы задач ТОЛЬКО: sentence_translation_full, word_definition_match, word_scramble. "
                "word_scramble: буквы слова в options, answer = исходное слово. "
                "word_definition_match: prompt с словом, options = определения, answer = верное определение. "
                "sentence_translation_full: prompt с английским предложением, answer = русский перевод. "
                "Верни только JSON."
            ),
            user_prompt=(
                f"Сгенерируй {payload.size} заданий для уровня {payload.cefr_level}. "
                f"Слова пользователя: {json.dumps(seeds_with_context, ensure_ascii=False)}. "
                f"Требуемый тип: {payload.mode}. "
                "Верни JSON в формате: "
                "{\"exercises\":[{\"prompt\":\"...\",\"answer\":\"...\",\"exercise_type\":\"...\",\"options\":[\"...\"]}]}"
            ),
            temperature=0.3,
            max_tokens=140 if payload.size <= 1 else min(500, 120 * payload.size),
        )
        if content:
            parsed = self._parse_generated_exercises(content, payload.size)
            if parsed:
                if payload.seeds:
                    seed_idx = 0
                    while len(parsed) < payload.size:
                        seed = payload.seeds[seed_idx % len(payload.seeds)]
                        parsed.append(
                            self._build_sentence_translation_exercise(seed, cefr_level=payload.cefr_level)
                        )
                        seed_idx += 1
                return GenerateExercisesResponse(
                    exercises=parsed,
                    provider_note=f"remote:{self._provider}/{self._model}",
                )

        return self._fallback_generate_exercises(payload)

    async def generate_exercises_async(
        self,
        payload: GenerateExercisesRequest,
    ) -> GenerateExercisesResponse:
        """Async version of generate_exercises."""
        # Sentence translation uses dedicated generation pipeline for reliability.
        if payload.mode == "sentence_translation_full":
            return self._fallback_generate_exercises(payload)

        if payload.mode == "word_definition_match":
            return self._fallback_generate_exercises(payload)

        seeds_with_context = [
            {
                "word": seed.english_lemma,
                "translation": seed.russian_translation,
            }
            for seed in payload.seeds
        ]

        content = await self._chat_completion_async(
            system_prompt=(
                "Ты продвинутый AI-тьютор. Твоя задача создавать уникальные упражнения. "
                "Создавай новые предложения, не копируя предложения из пользовательского контекста. "
                "Никогда не повторяй одно и то же задание дважды. "
                "Типы задач ТОЛЬКО: sentence_translation_full, word_definition_match, word_scramble. "
                "Верни только JSON."
            ),
            user_prompt=(
                f"Сгенерируй {payload.size} заданий для уровня {payload.cefr_level}. "
                f"Слова пользователя: {json.dumps(seeds_with_context, ensure_ascii=False)}. "
                f"Требуемый тип: {payload.mode}. "
                "Верни JSON в формате: "
                "{\"exercises\":[{\"prompt\":\"...\",\"answer\":\"...\",\"exercise_type\":\"...\",\"options\":[\"...\"]}]}"
            ),
            temperature=0.3,
            max_tokens=140 if payload.size <= 1 else min(500, 120 * payload.size),
        )
        if content:
            parsed = self._parse_generated_exercises(content, payload.size)
            if parsed:
                if payload.seeds:
                    seed_idx = 0
                    while len(parsed) < payload.size:
                        seed = payload.seeds[seed_idx % len(payload.seeds)]
                        parsed.append(
                            self._build_sentence_translation_exercise(seed, cefr_level=payload.cefr_level)
                        )
                        seed_idx += 1
                return GenerateExercisesResponse(
                    exercises=parsed,
                    provider_note=f"remote:{self._provider}/{self._model}",
                )

        return self._fallback_generate_exercises(payload)

    async def generate_exercises_batch(
        self,
        batches: list[GenerateExercisesRequest],
    ) -> list[GenerateExercisesResponse]:
        """Generate multiple exercise batches in parallel."""
        tasks = [self.generate_exercises_async(batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, GenerateExercisesResponse)]


ai_service = AIService()
