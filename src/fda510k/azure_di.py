"""Azure AI Document Intelligence adapter using managed identity by default."""

from azure.ai.documentintelligence import DocumentIntelligenceClient as AzureClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential


class AzureLayoutExtractor:
    """Extract per-page text with the prebuilt-layout model."""

    def __init__(self, endpoint: str, key: str | None = None) -> None:
        credential = AzureKeyCredential(key) if key else DefaultAzureCredential()
        self.client = AzureClient(endpoint=endpoint, credential=credential)

    def extract_layout(self, content: bytes) -> dict[int, str]:
        poller = self.client.begin_analyze_document(
            "prebuilt-layout", AnalyzeDocumentRequest(bytes_source=content)
        )
        result = poller.result()
        full_text = result.content or ""
        return {
            page.page_number: "".join(
                full_text[span.offset : span.offset + span.length] for span in (page.spans or [])
            )
            for page in result.pages
        }
