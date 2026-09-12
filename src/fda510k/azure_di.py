"""Azure OCR with token authentication and optional page selection."""

from io import BytesIO

from azure.ai.documentintelligence import DocumentIntelligenceClient as AzureClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from pypdf import PdfReader, PdfWriter

from .models import OcrResult, OcrWord


class AzureLayoutExtractor:
    """Extract per-page text with the prebuilt-layout model."""

    def __init__(self, endpoint: str, key: str | None = None) -> None:
        credential = AzureKeyCredential(key) if key else DefaultAzureCredential()
        self.client = AzureClient(endpoint=endpoint, credential=credential)

    def extract_layout(self, content: bytes, page_numbers: list[int] | None = None) -> OcrResult:
        """Upload selected pages and return text under the original page numbers."""
        if page_numbers is not None:
            if not page_numbers:
                return OcrResult()
            reader = PdfReader(BytesIO(content))
            writer = PdfWriter()
            for page_number in page_numbers:
                if page_number < 1 or page_number > len(reader.pages):
                    raise ValueError(f"Page {page_number} is outside the PDF.")
                writer.add_page(reader.pages[page_number - 1])
            selected_pdf = BytesIO()
            writer.write(selected_pdf)
            content = selected_pdf.getvalue()

        poller = self.client.begin_analyze_document(
            "prebuilt-layout",
            AnalyzeDocumentRequest(bytes_source=content),
            string_index_type="unicodeCodePoint",
        )
        result = poller.result()
        full_text = result.content or ""
        text_by_page = {
            (page_numbers[page.page_number - 1] if page_numbers else page.page_number): "".join(
                full_text[span.offset : span.offset + span.length] for span in (page.spans or [])
            )
            for page in result.pages
        }
        words = []
        for page in result.pages:
            original_page = page_numbers[page.page_number - 1] if page_numbers else page.page_number
            for word in page.words or []:
                words.append(
                    OcrWord(
                        page_number=original_page, text=word.content, confidence=word.confidence
                    )
                )
        return OcrResult(text_by_page=text_by_page, words=words)
