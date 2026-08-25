"""Azure Functions entry points for scheduled and manual PDF processing."""

import json
import logging
import os
from pathlib import Path

import azure.functions as func

from fda510k.azure_di import AzureLayoutExtractor
from fda510k.extractors import PdfExtractor
from fda510k.pipeline import ProcessingPipeline
from fda510k.storage import LocalAuditStore

app = func.FunctionApp()
logger = logging.getLogger(__name__)


def pipeline() -> ProcessingPipeline:
    """Build dependencies from environment without embedding credentials."""
    endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
    di = (
        AzureLayoutExtractor(endpoint, os.getenv("DOCUMENT_INTELLIGENCE_KEY")) if endpoint else None
    )
    return ProcessingPipeline(
        PdfExtractor(di), LocalAuditStore(Path(os.getenv("AUDIT_FILE", "data/audit.jsonl")))
    )


@app.function_name(name="reprocess_510k_pdf")
@app.route(route="reprocess", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def reprocess(req: func.HttpRequest) -> func.HttpResponse:
    """Process a locally mounted or downloaded PDF supplied by the caller."""
    try:
        body = req.get_json()
        pdf_path = Path(body["pdf_path"])
        result = pipeline().process(
            pdf_path.name, body["k_number"], pdf_path.read_bytes(), force=True
        )
        return func.HttpResponse(json.dumps(result), mimetype="application/json")
    except (KeyError, ValueError, OSError) as exc:
        return func.HttpResponse(str(exc), status_code=400)


@app.function_name(name="scheduled_510k_ingestion")
@app.schedule(schedule="0 0 6 * * *", arg_name="timer", use_monitor=True)
def scheduled_ingestion(timer: func.TimerRequest) -> None:
    """Scheduled hook reserved for a configured public FDA document feed."""
    logger.info("scheduled_ingestion_triggered", extra={"past_due": timer.past_due})
