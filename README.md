# FDA 510(k) Document Intelligence

A public, clean-room Python project that extracts predicate-device K-numbers from FDA 510(k) PDFs and records a deterministic reconciliation result.

## What it does

1. Calculates a SHA-256 digest for each PDF, making repeat processing idempotent.
2. Extracts native text with `pypdf`, filling weak pages with `pdfplumber`.
3. Optionally sends only weak/scanned pages through Azure AI Document Intelligence `prebuilt-layout`.
4. Finds K-numbers near predicate-equivalence language and stores a `matched`, `ambiguous`, or `unmatched` result with evidence.
5. Writes auditable JSONL locally and can export it to CSV or Parquet with DuckDB.

The implementation is deliberately conservative: multiple predicate candidates remain **ambiguous** instead of choosing one silently.

## Quick start

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m fda510k.cli path/to/summary.pdf --k-number K123456 --export exports/results.parquet
```

Download a small public reference sample:

```bash
python scripts/download_reference_data.py
```

## Azure Functions

`function_app.py` uses the Python v2 programming model and provides:

- `POST /api/reprocess` — manual processing. Provide `{"pdf_path":"/path/file.pdf","k_number":"K123456"}`.
- `scheduled_510k_ingestion` — a daily timer hook for a future configured FDA document feed.

For OCR/layout escalation, set `DOCUMENT_INTELLIGENCE_ENDPOINT`. `DefaultAzureCredential` is used in Azure (managed identity); `DOCUMENT_INTELLIGENCE_KEY` is accepted only for local development. Copy `local.settings.json.example` to `local.settings.json` for local Functions work.

## Data provenance and limitations

Reference metadata is fetched from the public [openFDA 510(k) API](https://open.fda.gov/apis/device/510k/). PDF availability and layouts vary across FDA sources. This project does not claim that every K-number in a document is a predicate: it requires nearby predicate/equivalence context, preserves the source text, and deliberately surfaces uncertain cases for review.

Azure resources are optional and may incur charges. Local processing, the public API sample, and CSV/Parquet export do not require a subscription.

## Repository layout

`src/fda510k/` contains the domain models, extraction adapters, reconciliation logic, storage boundary, API client, and CLI. `function_app.py` contains the Azure Functions triggers. The project is configured for Ruff and mypy; tests and deployment infrastructure are intentionally the next increment.
