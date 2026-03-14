from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.learning_graph.repository import learning_graph_repository
from app.modules.learning_graph.schemas import (
    InterestUpsertRequest,
    LearningGraphObservabilityResponse,
    LearningGraphOverviewResponse,
    RecommendationsResponse,
    SemanticUpsertRequest,
    SemanticUpsertResponse,
    SenseAnchorsResponse,
    TopicClusterRead,
    UserInterestsResponse,
    WordSenseRead,
)
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/learning-graph", tags=["learning_graph"])


@router.get("/me/overview", response_model=LearningGraphOverviewResponse)
def get_learning_graph_overview_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningGraphOverviewResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    overview = learning_graph_repository.get_overview(db, user_id=current_user_id)
    return LearningGraphOverviewResponse(user_id=current_user_id, **overview)


@router.get("/me/interests", response_model=UserInterestsResponse)
def list_interests_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserInterestsResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInterestsResponse(
        user_id=current_user_id,
        interests=learning_graph_repository.list_interests(db, current_user_id),
    )


@router.put("/me/interests", response_model=UserInterestsResponse)
def upsert_interests_me(
    payload: InterestUpsertRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserInterestsResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated = learning_graph_repository.upsert_interests(
        db,
        user_id=current_user_id,
        interests=payload.interests,
    )
    return UserInterestsResponse(user_id=current_user_id, interests=updated)


@router.post("/me/semantic-upsert", response_model=SemanticUpsertResponse)
def semantic_upsert_me(
    payload: SemanticUpsertRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SemanticUpsertResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        result = learning_graph_repository.semantic_upsert(
            db,
            user_id=current_user_id,
            english_lemma=payload.english_lemma,
            russian_translation=payload.russian_translation,
            context_definition_ru=payload.context_definition_ru,
            source_sentence=payload.source_sentence,
            source_url=payload.source_url,
            topic_hint=payload.topic_hint,
            vocabulary_item_id=payload.vocabulary_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(result.sense)

    cluster_read = None
    if result.cluster is not None:
        cluster_read = TopicClusterRead(
            id=result.cluster.id,
            key=result.cluster.cluster_key,
            name=result.cluster.name,
            description=result.cluster.description,
        )
    return SemanticUpsertResponse(
        user_id=current_user_id,
        created_new_sense=result.created_new,
        semantic_duplicate_of_id=result.duplicate_of_id,
        sense=WordSenseRead(
            id=result.sense.id,
            english_lemma=result.sense.english_lemma,
            semantic_key=result.sense.semantic_key,
            russian_translation=result.sense.russian_translation,
            context_definition_ru=result.sense.context_definition_ru,
            source_sentence=result.sense.source_sentence,
            source_url=result.sense.source_url,
            topic_cluster_id=result.sense.topic_cluster_id,
            created_at=result.sense.created_at,
        ),
        cluster=cluster_read,
    )


@router.get("/me/recommendations", response_model=RecommendationsResponse)
def get_recommendations_me(
    mode: Literal["interest", "weakness", "mixed"] = Query(default="mixed"),
    limit: int = Query(default=10, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RecommendationsResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    items = learning_graph_repository.get_recommendations(
        db,
        user_id=current_user_id,
        mode=mode,
        limit=limit,
    )
    return RecommendationsResponse(user_id=current_user_id, mode=mode, items=items)


@router.get("/me/observability", response_model=LearningGraphObservabilityResponse)
def get_observability_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LearningGraphObservabilityResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    snapshot = learning_graph_repository.get_observability(user_id=current_user_id)
    return LearningGraphObservabilityResponse(user_id=current_user_id, **snapshot)


@router.get("/me/anchors", response_model=SenseAnchorsResponse)
def get_anchors_me(
    english_lemma: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=5, ge=1, le=50),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SenseAnchorsResponse:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    anchors = learning_graph_repository.list_anchors(
        db,
        user_id=current_user_id,
        english_lemma=english_lemma,
        limit=limit,
    )
    return SenseAnchorsResponse(
        user_id=current_user_id,
        english_lemma=english_lemma.strip().lower(),
        anchors=anchors,
    )
