from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.models.user import User
from app.services.lexicon_jsonl_reviews import (
    load_jsonl_review_session,
    materialize_jsonl_review_outputs,
    resolve_compiled_artifact_path,
    resolve_decisions_sidecar_path,
    resolve_output_dir_path,
    update_jsonl_review_decision,
)

router = APIRouter()


class LexiconJsonlReviewLoadRequest(BaseModel):
    artifact_path: str
    decisions_path: str | None = None
    output_dir: str | None = None


class LexiconJsonlReviewItemUpdateRequest(BaseModel):
    artifact_path: str
    decisions_path: str | None = None
    review_status: str
    decision_reason: str | None = None


class LexiconJsonlReviewMaterializeRequest(BaseModel):
    artifact_path: str
    decisions_path: str | None = None
    output_dir: str | None = None


class LexiconJsonlReviewItemResponse(BaseModel):
    entry_id: str
    entry_type: str
    normalized_form: str | None
    display_text: str
    entity_category: str | None
    language: str
    frequency_rank: int | None
    cefr_level: str | None
    review_status: str
    decision_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | str | None
    compiled_payload: dict[str, Any]
    compiled_payload_sha256: str


class LexiconJsonlReviewSessionResponse(BaseModel):
    artifact_filename: str
    artifact_path: str
    artifact_sha256: str
    decisions_path: str
    output_dir: str | None = None
    total_items: int
    pending_count: int
    approved_count: int
    rejected_count: int
    items: list[LexiconJsonlReviewItemResponse]


class LexiconJsonlReviewMaterializeResponse(BaseModel):
    artifact_sha256: str
    decision_count: int
    approved_count: int
    rejected_count: int
    regenerate_count: int
    decisions_output_path: str
    approved_output_path: str
    rejected_output_path: str
    regenerate_output_path: str


def _resolve_paths(
    *,
    artifact_path: str,
    decisions_path: str | None,
    output_dir: str | None,
    settings: Settings,
) -> tuple[str, str, str | None]:
    artifact = resolve_compiled_artifact_path(artifact_path, settings=settings)
    decisions = resolve_decisions_sidecar_path(artifact, decisions_path, settings=settings)
    materialize_output_dir = str(resolve_output_dir_path(artifact, output_dir, settings=settings)) if output_dir else None
    return str(artifact), str(decisions), materialize_output_dir


@router.post("/load", response_model=LexiconJsonlReviewSessionResponse)
async def load_lexicon_jsonl_review_session(
    request: LexiconJsonlReviewLoadRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconJsonlReviewSessionResponse:
    artifact_path, decisions_path, output_dir = _resolve_paths(
        artifact_path=request.artifact_path,
        decisions_path=request.decisions_path,
        output_dir=request.output_dir,
        settings=settings,
    )
    payload = load_jsonl_review_session(
        artifact_path=resolve_compiled_artifact_path(artifact_path, settings=settings),
        decisions_path=resolve_decisions_sidecar_path(
            resolve_compiled_artifact_path(artifact_path, settings=settings),
            decisions_path,
            settings=settings,
        ),
    )
    return LexiconJsonlReviewSessionResponse(**payload, output_dir=output_dir)


@router.patch("/items/{entry_id}", response_model=LexiconJsonlReviewItemResponse)
async def update_lexicon_jsonl_review_item(
    entry_id: str,
    request: LexiconJsonlReviewItemUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconJsonlReviewItemResponse:
    artifact_path, decisions_path, _ = _resolve_paths(
        artifact_path=request.artifact_path,
        decisions_path=request.decisions_path,
        output_dir=None,
        settings=settings,
    )
    payload = update_jsonl_review_decision(
        artifact_path=resolve_compiled_artifact_path(artifact_path, settings=settings),
        decisions_path=resolve_decisions_sidecar_path(
            resolve_compiled_artifact_path(artifact_path, settings=settings),
            decisions_path,
            settings=settings,
        ),
        entry_id=entry_id,
        review_status=request.review_status,
        decision_reason=request.decision_reason,
        reviewed_by=str(current_user.id),
    )
    return LexiconJsonlReviewItemResponse(**payload)


@router.post("/materialize", response_model=LexiconJsonlReviewMaterializeResponse)
async def materialize_lexicon_jsonl_review_outputs_route(
    request: LexiconJsonlReviewMaterializeRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconJsonlReviewMaterializeResponse:
    artifact_path, decisions_path, output_dir = _resolve_paths(
        artifact_path=request.artifact_path,
        decisions_path=request.decisions_path,
        output_dir=request.output_dir,
        settings=settings,
    )
    if output_dir is None:
        output_dir = str(resolve_compiled_artifact_path(artifact_path, settings=settings).parent)
    payload = materialize_jsonl_review_outputs(
        artifact_path=resolve_compiled_artifact_path(artifact_path, settings=settings),
        decisions_path=resolve_decisions_sidecar_path(
            resolve_compiled_artifact_path(artifact_path, settings=settings),
            decisions_path,
            settings=settings,
        ),
        output_dir=resolve_output_dir_path(
            resolve_compiled_artifact_path(artifact_path, settings=settings),
            output_dir,
            settings=settings,
        )
        or resolve_compiled_artifact_path(artifact_path, settings=settings).parent,
    )
    return LexiconJsonlReviewMaterializeResponse(**payload)
