from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import VocabularyItemModel
from app.modules.vocabulary.schemas import VocabularyItemCreate


class VocabularyRepository:
    def list_items(self, db: Session, user_id: int | None) -> list[VocabularyItemModel]:
        stmt = select(VocabularyItemModel)
        if user_id is not None:
            stmt = stmt.where(VocabularyItemModel.user_id == user_id)
        stmt = stmt.order_by(VocabularyItemModel.id.desc())
        return list(db.scalars(stmt))

    def create(
        self,
        db: Session,
        payload: VocabularyItemCreate,
        *,
        auto_commit: bool = True,
    ) -> VocabularyItemModel:
        item = VocabularyItemModel(**payload.model_dump())
        db.add(item)
        if auto_commit:
            db.commit()
            db.refresh(item)
        else:
            db.flush()
        return item

    def get_by_id_for_user(self, db: Session, item_id: int, user_id: int) -> VocabularyItemModel | None:
        stmt = select(VocabularyItemModel).where(
            VocabularyItemModel.id == item_id,
            VocabularyItemModel.user_id == user_id,
        )
        return db.scalar(stmt)

    def update(
        self,
        db: Session,
        item: VocabularyItemModel,
        *,
        english_lemma: str,
        russian_translation: str,
        source_sentence: str | None,
        source_url: str | None,
        auto_commit: bool = True,
    ) -> VocabularyItemModel:
        item.english_lemma = english_lemma.strip().lower()
        item.russian_translation = russian_translation.strip()
        item.source_sentence = source_sentence.strip() if source_sentence else None
        item.source_url = source_url.strip() if source_url else None
        db.add(item)
        if auto_commit:
            db.commit()
            db.refresh(item)
        else:
            db.flush()
        return item

    def delete(self, db: Session, item: VocabularyItemModel, *, auto_commit: bool = True) -> None:
        db.delete(item)
        if auto_commit:
            db.commit()
        else:
            db.flush()

    def get_translation_map(
        self,
        db: Session,
        user_id: int,
        english_lemmas: list[str],
    ) -> dict[str, str]:
        normalized = [lemma.strip().lower() for lemma in english_lemmas if lemma and lemma.strip()]
        if not normalized:
            return {}

        stmt = (
            select(VocabularyItemModel)
            .where(
                VocabularyItemModel.user_id == user_id,
                VocabularyItemModel.english_lemma.in_(normalized),
            )
            .order_by(VocabularyItemModel.id.desc())
        )
        rows = list(db.scalars(stmt))

        result: dict[str, str] = {}
        for row in rows:
            key = row.english_lemma.strip().lower()
            if key not in result:
                result[key] = row.russian_translation
        return result

    def get_definition_map(
        self,
        db: Session,
        user_id: int,
        english_lemmas: list[str],
    ) -> dict[str, str]:
        normalized = [lemma.strip().lower() for lemma in english_lemmas if lemma and lemma.strip()]
        if not normalized:
            return {}

        stmt = (
            select(VocabularyItemModel)
            .where(
                VocabularyItemModel.user_id == user_id,
                VocabularyItemModel.english_lemma.in_(normalized),
            )
            .order_by(VocabularyItemModel.id.desc())
        )
        rows = list(db.scalars(stmt))

        result: dict[str, str] = {}
        for row in rows:
            key = row.english_lemma.strip().lower()
            if key not in result and row.context_definition_ru:
                result[key] = row.context_definition_ru
        return result

    def get_latest_by_lemma(
        self,
        db: Session,
        user_id: int,
        english_lemma: str,
    ) -> VocabularyItemModel | None:
        normalized = english_lemma.strip().lower()
        if not normalized:
            return None
        stmt = (
            select(VocabularyItemModel)
            .where(
                VocabularyItemModel.user_id == user_id,
                VocabularyItemModel.english_lemma == normalized,
            )
            .order_by(VocabularyItemModel.id.desc())
            .limit(1)
        )
        return db.scalar(stmt)


vocabulary_repository = VocabularyRepository()
