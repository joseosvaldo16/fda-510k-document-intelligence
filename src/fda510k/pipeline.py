"""Orchestration for idempotent PDF processing."""

import hashlib
import logging

from .extractors import PdfExtractor
from .llm import LlmReviewer
from .matching import extract_predicates
from .models import MatchStatus, ProcessingAudit
from .storage import AuditStore

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """Process one PDF and retain an audit record for every outcome."""

    def __init__(
        self, extractor: PdfExtractor, store: AuditStore, reviewer: LlmReviewer | None = None
    ) -> None:
        self.extractor = extractor
        self.store = store
        self.reviewer = reviewer

    def process(
        self, document_id: str, source_k_number: str, content: bytes, force: bool = False
    ) -> dict[str, object]:
        digest = hashlib.sha256(content).hexdigest()
        if not force and self.store.seen(digest):
            logger.info(
                "document_already_processed", extra={"document_id": document_id, "sha256": digest}
            )
            return {"document_id": document_id, "status": "skipped", "sha256": digest}
        try:
            extraction = self.extractor.extract(document_id, digest, content)
            if self.reviewer:
                self.reviewer.review_ocr(extraction, content, source_k_number)
                relationships = self.reviewer.match(source_k_number, extraction)
            else:
                relationships = extract_predicates(source_k_number, extraction.text_by_page)
            unresolved_pages = set(extraction.unresolved_ocr_pages)
            for relationship in relationships:
                if any(item.page_number in unresolved_pages for item in relationship.evidence):
                    relationship.status = MatchStatus.AMBIGUOUS
                    relationship.review_reason = "Unresolved OCR identifier on an evidence page."
            records = [item.model_dump(mode="json") for item in relationships]
            self.store.save(
                ProcessingAudit(
                    document_id=document_id,
                    sha256=digest,
                    status="completed",
                    extractor=extraction.extractor,
                    review_notes=extraction.review_notes,
                    ocr_words=extraction.ocr_words,
                ),
                records,
            )
            return {
                "document_id": document_id,
                "status": "completed",
                "sha256": digest,
                "relationships": records,
                "review_notes": extraction.review_notes,
            }
        except Exception as exc:
            logger.exception("document_processing_failed", extra={"document_id": document_id})
            self.store.save(
                ProcessingAudit(
                    document_id=document_id, sha256=digest, status="failed", message=str(exc)
                ),
                [],
            )
            raise
