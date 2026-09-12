"""Layered PDF extraction, escalating only when native text is weak."""

from io import BytesIO
from typing import Protocol

import pdfplumber
from pypdf import PdfReader

from .models import ExtractionResult


class DocumentIntelligenceClient(Protocol):
    """Small adapter boundary around Azure Document Intelligence."""

    def extract_layout(
        self, content: bytes, page_numbers: list[int] | None = None
    ) -> dict[int, str]: ...


class PdfExtractor:
    """Try embedded text first, then request OCR only for weak pages."""

    def __init__(self, document_intelligence: DocumentIntelligenceClient | None = None) -> None:
        self.document_intelligence = document_intelligence

    def extract(self, document_id: str, sha256: str, content: bytes) -> ExtractionResult:
        reader = PdfReader(BytesIO(content))
        pypdf_text = {
            index + 1: (page.extract_text() or "").strip()
            for index, page in enumerate(reader.pages)
        }
        text_by_page = self._enrich_with_pdfplumber(content, pypdf_text)
        weak = [page for page, text in text_by_page.items() if len(text) < 40]
        used_di = False
        if weak and self.document_intelligence:
            layout_text = self.document_intelligence.extract_layout(content, page_numbers=weak)
            text_by_page.update({page: layout_text[page] for page in weak if layout_text.get(page)})
            used_di = True
        extractor = "azure-layout" if used_di else "pypdf/pdfplumber"
        return ExtractionResult(
            document_id=document_id,
            sha256=sha256,
            extractor=extractor,
            page_count=len(reader.pages),
            text_by_page=text_by_page,
            used_document_intelligence=used_di,
        )

    @staticmethod
    def _enrich_with_pdfplumber(content: bytes, pages: dict[int, str]) -> dict[int, str]:
        with pdfplumber.open(BytesIO(content)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                if len(pages[index]) < 40:
                    pages[index] = (page.extract_text() or "").strip()
        return pages
