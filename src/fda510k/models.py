"""Normalized domain records used throughout the pipeline."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class PredicateCandidate(BaseModel):
    k_number: str
    page_number: int
    evidence: str


class PredicateRelationship(BaseModel):
    source_k_number: str
    predicate_k_number: str | None = None
    status: MatchStatus
    candidates: list[str] = Field(default_factory=list)
    evidence: list[PredicateCandidate] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    document_id: str
    sha256: str
    extractor: str
    page_count: int
    text_by_page: dict[int, str]
    used_document_intelligence: bool = False


class ProcessingAudit(BaseModel):
    document_id: str
    sha256: str
    status: str
    extractor: str | None = None
    message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
