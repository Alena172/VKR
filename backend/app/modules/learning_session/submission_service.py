from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re

from sqlalchemy.orm import Session

from app.modules.ai_services.contracts import ExplainErrorRequest
from app.modules.ai_services.service import ai_service
from app.modules.context_memory.repository import context_repository
from app.modules.learning_graph.repository import learning_graph_repository
from app.modules.learning_session.evaluation import is_answer_correct, normalize_answer
from app.modules.learning_session.repository import AnswerPersistPayload, learning_session_repository
from app.modules.learning_session.schemas import (
    SessionAnswer,
    SessionAnswerFeedback,
    SessionSubmitResponse,
)

_WORD_RE = re.compile(r"^[a-z][a-z'-]{0,48}$")


def _normalize_word_candidate(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower().strip(" \t\n\r\"'`.,!?;:()[]{}")
    if not candidate or not _WORD_RE.fullmatch(candidate):
        return None
    return candidate


def _extract_progress_word(
    *,
    prompt: str | None,
    expected_answer: str | None,
    vocabulary_words: set[str],
) -> str | None:
    normalized_answer = _normalize_word_candidate(expected_answer)
    if normalized_answer and (not vocabulary_words or normalized_answer in vocabulary_words):
        return normalized_answer

    if not prompt:
        return None

    after_colon = prompt.split(":", maxsplit=1)[-1]
    normalized_prompt_word = _normalize_word_candidate(after_colon)
    if normalized_prompt_word and (not vocabulary_words or normalized_prompt_word in vocabulary_words):
        return normalized_prompt_word

    return None


@dataclass
class EvaluatedAnswer:
    exercise_id: int
    prompt: str | None
    expected_answer: str | None
    user_answer: str
    is_correct: bool
    explanation_ru: str | None
    progress_word: str | None
    add_to_difficult_words: bool
    incorrect_feedback: SessionAnswerFeedback | None
    advice_feedback: SessionAnswerFeedback | None


class LearningSessionSubmissionService:
    async def evaluate_answers(self, answers: list[SessionAnswer]) -> list[EvaluatedAnswer]:
        if not answers:
            return []

        semaphore = asyncio.Semaphore(4)

        async def evaluate_with_limit(answer: SessionAnswer) -> EvaluatedAnswer:
            async with semaphore:
                return await self._evaluate_answer(answer)

        return await asyncio.gather(*(evaluate_with_limit(answer) for answer in answers))

    async def _evaluate_answer(self, answer: SessionAnswer) -> EvaluatedAnswer:
        evaluated_is_correct = is_answer_correct(answer.expected_answer, answer.user_answer)
        explanation_ru: str | None = None
        advice_feedback: SessionAnswerFeedback | None = None
        incorrect_feedback: SessionAnswerFeedback | None = None
        normalized_expected = normalize_answer(answer.expected_answer)
        normalized_user = normalize_answer(answer.user_answer)
        advice_added = False

        if (
            not evaluated_is_correct
            and answer.prompt
            and answer.expected_answer
            and len(normalized_expected.split()) >= 5
        ):
            semantic_ok = await ai_service.is_translation_semantically_correct_async(
                english_prompt=answer.prompt,
                expected_answer=answer.expected_answer,
                user_answer=answer.user_answer,
            )
            if semantic_ok:
                evaluated_is_correct = True
                ai_hint = await ai_service.suggest_improvement_async(
                    ExplainErrorRequest(
                        english_prompt=answer.prompt,
                        user_answer=answer.user_answer,
                        expected_answer=answer.expected_answer,
                    )
                )
                explanation_ru = ai_hint.explanation_ru
                advice_feedback = SessionAnswerFeedback(
                    exercise_id=answer.exercise_id,
                    explanation_ru=explanation_ru,
                )
                advice_added = True

        if not evaluated_is_correct and answer.prompt and answer.expected_answer:
            ai_explanation = await ai_service.explain_error_async(
                ExplainErrorRequest(
                    english_prompt=answer.prompt,
                    user_answer=answer.user_answer,
                    expected_answer=answer.expected_answer,
                )
            )
            explanation_ru = ai_explanation.explanation_ru
            incorrect_feedback = SessionAnswerFeedback(
                exercise_id=answer.exercise_id,
                explanation_ru=explanation_ru,
            )
        elif (
            evaluated_is_correct
            and answer.prompt
            and answer.expected_answer
            and normalized_expected
            and normalized_expected != normalized_user
            and not advice_added
        ):
            ai_hint = await ai_service.suggest_improvement_async(
                ExplainErrorRequest(
                    english_prompt=answer.prompt,
                    user_answer=answer.user_answer,
                    expected_answer=answer.expected_answer,
                )
            )
            explanation_ru = ai_hint.explanation_ru
            advice_feedback = SessionAnswerFeedback(
                exercise_id=answer.exercise_id,
                explanation_ru=explanation_ru,
            )

        progress_word = _extract_progress_word(
            prompt=answer.prompt,
            expected_answer=answer.expected_answer,
            vocabulary_words=set(),
        )

        return EvaluatedAnswer(
            exercise_id=answer.exercise_id,
            prompt=answer.prompt,
            expected_answer=answer.expected_answer,
            user_answer=answer.user_answer,
            is_correct=evaluated_is_correct,
            explanation_ru=explanation_ru,
            progress_word=progress_word,
            add_to_difficult_words=bool(progress_word and not evaluated_is_correct),
            incorrect_feedback=incorrect_feedback,
            advice_feedback=advice_feedback,
        )

    def collect_feedback(
        self,
        evaluated_answers: list[EvaluatedAnswer],
    ) -> tuple[list[SessionAnswerFeedback], list[SessionAnswerFeedback]]:
        incorrect_feedback = [
            item.incorrect_feedback
            for item in evaluated_answers
            if item.incorrect_feedback is not None
        ]
        advice_feedback = [
            item.advice_feedback
            for item in evaluated_answers
            if item.advice_feedback is not None
        ]
        return incorrect_feedback, advice_feedback

    def update_progress(
        self,
        *,
        db: Session,
        user_id: int,
        user_cefr_level: str | None,
        evaluated_answers: list[EvaluatedAnswer],
    ) -> list[str]:
        difficult_words_to_add: list[str] = []

        for item in evaluated_answers:
            if item.progress_word:
                context_repository.update_word_progress(
                    db,
                    user_id=user_id,
                    word=item.progress_word,
                    is_correct=item.is_correct,
                )

            if item.add_to_difficult_words and item.progress_word:
                difficult_words_to_add.append(item.progress_word)
                learning_graph_repository.add_mistake_event(
                    db,
                    user_id=user_id,
                    english_lemma=item.progress_word,
                    prompt=item.prompt,
                    expected_answer=item.expected_answer,
                    user_answer=item.user_answer,
                )

        context_repository.add_difficult_words(
            db,
            user_id=user_id,
            words=difficult_words_to_add,
            default_cefr_level=user_cefr_level,
            auto_commit=False,
        )
        return difficult_words_to_add

    def persist_session(
        self,
        *,
        db: Session,
        user_id: int,
        evaluated_answers: list[EvaluatedAnswer],
    ):
        total = len(evaluated_answers)
        correct = sum(1 for item in evaluated_answers if item.is_correct)
        return learning_session_repository.create_with_answers(
            db,
            user_id=user_id,
            total=total,
            correct=correct,
            accuracy=round((correct / total), 4) if total else 0.0,
            answers=[
                AnswerPersistPayload(
                    exercise_id=item.exercise_id,
                    prompt=item.prompt,
                    expected_answer=item.expected_answer,
                    user_answer=item.user_answer,
                    is_correct=item.is_correct,
                    explanation_ru=item.explanation_ru,
                )
                for item in evaluated_answers
            ],
            auto_commit=False,
        )

    async def submit(
        self,
        *,
        db: Session,
        user_id: int,
        user_cefr_level: str | None,
        answers: list[SessionAnswer],
    ) -> SessionSubmitResponse:
        try:
            evaluated_answers = await self.evaluate_answers(answers)
            incorrect_feedback, advice_feedback = self.collect_feedback(evaluated_answers)
            self.update_progress(
                db=db,
                user_id=user_id,
                user_cefr_level=user_cefr_level,
                evaluated_answers=evaluated_answers,
            )
            session_row = self.persist_session(
                db=db,
                user_id=user_id,
                evaluated_answers=evaluated_answers,
            )
            db.commit()
            db.refresh(session_row)
            return SessionSubmitResponse(
                session=session_row,
                incorrect_feedback=incorrect_feedback,
                advice_feedback=advice_feedback,
            )
        except Exception:
            db.rollback()
            raise


learning_session_submission_service = LearningSessionSubmissionService()
