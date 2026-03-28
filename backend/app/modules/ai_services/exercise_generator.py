from __future__ import annotations

import asyncio
import json
import random
import re
from collections import deque
from collections.abc import Awaitable, Callable

from app.modules.ai_services.contracts import (
    ExerciseSeed,
    GenerateExercisesRequest,
    GenerateExercisesResponse,
    GeneratedExerciseItem,
    TranslateGlossaryItem,
)
from app.modules.ai_services.definition_resolver import DictionaryDefinitionResolver
from app.modules.ai_services.translation_service import TranslationService


class ExerciseGenerator:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        max_retries: int,
        remote_enabled: Callable[[], bool],
        chat_complete_async: Callable[..., Awaitable[str | None]],
        chat_complete_sync: Callable[..., str | None],
        provider_unavailable_error: type[Exception],
        translation_service: TranslationService,
        definition_resolver: DictionaryDefinitionResolver,
        recent_sentences: dict[str, deque[str]],
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_retries = max_retries
        self._remote_enabled = remote_enabled
        self._chat_complete_async = chat_complete_async
        self._chat_complete_sync = chat_complete_sync
        self._provider_unavailable_error = provider_unavailable_error
        self._translation_service = translation_service
        self._definition_resolver = definition_resolver
        self._recent_sentences = recent_sentences

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
            scrambled[0], scrambled[-1] = scrambled[-1], scrambled[0]

        return [char.upper() for char in scrambled]

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
        if text.count(".") + text.count("!") + text.count("?") > 2:
            return False
        if not re.search(rf"\b{re.escape(target_word)}\b", text, flags=re.IGNORECASE):
            return False

        min_words, max_words = self._sentence_word_limits(cefr_level)
        words = re.findall(r"[A-Za-z']+", text)
        if len(words) < min_words or len(words) > max_words:
            return False

        disallowed_tokens = {"africa", "mars", "wizard", "dragon", "kingdom", "galaxy"}
        lowered = {token.lower() for token in words}
        return not bool(lowered.intersection(disallowed_tokens))

    def _sanitize_generated_sentence(self, text: str) -> str:
        candidate = text.strip().strip('"').strip("'")
        candidate = candidate.replace("**", "").replace("__", "").replace("`", "")
        return re.sub(r"\s+", " ", candidate).strip()

    def _generate_sentence_with_remote(self, word: str, cefr_level: str) -> str | None:
        history = self._recent_sentences.setdefault(word, deque(maxlen=8))
        for _ in range(self._max_retries + 2):
            content = self._chat_complete_sync(
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

    def _build_sentence_for_word(self, seed: ExerciseSeed, cefr_level: str | None = None) -> str:
        if not self._remote_enabled():
            raise self._provider_unavailable_error(
                "Sentence generation requires remote AI provider. "
                "Use AI_PROVIDER=ollama or set AI_PROVIDER=openai_compatible with AI_API_KEY."
            )

        word = seed.english_lemma.strip().lower()
        level = (cefr_level or "A2").upper()
        remote_sentence = self._generate_sentence_with_remote(word=word, cefr_level=level)
        if remote_sentence:
            return remote_sentence

        raise self._provider_unavailable_error(
            "Sentence generation request failed. Check AI_BASE_URL, AI_MODEL and provider availability."
        )

    def _build_ru_translation_of_sentence(self, sentence_en: str, seed: ExerciseSeed) -> str:
        if self._remote_enabled():
            content = self._chat_complete_sync(
                system_prompt="Переведи английское предложение на русский. Верни только перевод без комментариев.",
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

        translated = self._translation_service.heuristic_translate(
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

    def _build_sentence_translation_exercise(self, seed: ExerciseSeed, cefr_level: str | None = None) -> GeneratedExerciseItem:
        sentence_en = self._build_sentence_for_word(seed, cefr_level=cefr_level)
        sentence_ru = self._build_ru_translation_of_sentence(sentence_en, seed)
        return GeneratedExerciseItem(
            prompt=f"Translate sentence into Russian: {sentence_en}",
            answer=sentence_ru,
            exercise_type="sentence_translation_full",
            options=[],
        )

    async def _build_word_definition_match_exercise(
        self,
        seed: ExerciseSeed,
        pool: list[ExerciseSeed],
    ) -> GeneratedExerciseItem:
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
            return self._build_sentence_translation_exercise(seed)

        pairs = []
        for item in selected_words:
            pairs.append(
                {
                    "word": item.english_lemma.strip().lower(),
                    "definition": await self._definition_resolver.resolve(item.english_lemma, item.russian_translation),
                }
            )
        definitions = [pair["definition"] for pair in pairs]
        random.Random("|".join(pair["word"] for pair in pairs)).shuffle(definitions)
        prompt_words = " - ".join([f"{idx}. {pair['word']}" for idx, pair in enumerate(pairs, start=1)])
        return GeneratedExerciseItem(
            prompt=f"Match each word with its definition: {prompt_words}",
            answer=json.dumps(pairs, ensure_ascii=False),
            exercise_type="word_definition_match",
            options=definitions,
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

    async def _fallback_generate_exercises(self, payload: GenerateExercisesRequest) -> GenerateExercisesResponse:
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
                result.append(await self._build_word_definition_match_exercise(seed, rotated_pool))
            else:
                result.append(self._build_sentence_translation_exercise(seed, cefr_level=payload.cefr_level))

        level_note = f" CEFR={payload.cefr_level}." if payload.cefr_level else ""
        provider_note = (
            f"remote_sentence_pipeline:{self._provider}/{self._model}{level_note}"
            if payload.mode == "sentence_translation_full"
            else f"local_heuristic exercise_generation.{level_note}"
        )
        return GenerateExercisesResponse(exercises=result, provider_note=provider_note)

    def _parse_generated_exercises(self, raw_content: str, size: int) -> list[GeneratedExerciseItem]:
        payload = self._extract_json_payload(raw_content)
        if payload is None:
            return []

        exercises_raw = payload.get("exercises", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
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

    async def generate_exercises_async(self, payload: GenerateExercisesRequest) -> GenerateExercisesResponse:
        if payload.mode in {"sentence_translation_full", "word_definition_match"}:
            return await self._fallback_generate_exercises(payload)

        seeds_with_context = [
            {"word": seed.english_lemma, "translation": seed.russian_translation}
            for seed in payload.seeds
        ]
        content = await self._chat_complete_async(
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
                        parsed.append(self._build_sentence_translation_exercise(seed, cefr_level=payload.cefr_level))
                        seed_idx += 1
                return GenerateExercisesResponse(
                    exercises=parsed,
                    provider_note=f"remote:{self._provider}/{self._model}",
                )
        return await self._fallback_generate_exercises(payload)

    async def generate_exercises_batch(
        self,
        batches: list[GenerateExercisesRequest],
    ) -> list[GenerateExercisesResponse]:
        results = await asyncio.gather(
            *(self.generate_exercises_async(batch) for batch in batches),
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, GenerateExercisesResponse)]
