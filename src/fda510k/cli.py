"""Command-line entry point for local processing and exports."""

import argparse
import json
import os
from pathlib import Path

import duckdb

from .azure_di import AzureLayoutExtractor
from .extractors import PdfExtractor
from .pipeline import ProcessingPipeline
from .storage import LocalAuditStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Process an FDA 510(k) PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--k-number", required=True)
    parser.add_argument("--audit-file", type=Path, default=Path("data/audit.jsonl"))
    parser.add_argument("--export", type=Path, help="Write audit records as CSV or Parquet.")
    parser.add_argument(
        "--local-only", action="store_true", help="Disable Azure OCR and keep PDF processing local."
    )
    parser.add_argument(
        "--force", action="store_true", help="Process a previously recorded PDF again."
    )
    args = parser.parse_args()
    document_intelligence = None
    if not args.local_only:
        endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
        key = os.getenv("DOCUMENT_INTELLIGENCE_KEY")
        settings_path = Path("local.settings.json")
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())["Values"]
                endpoint = endpoint or settings.get("DOCUMENT_INTELLIGENCE_ENDPOINT")
                key = key or settings.get("DOCUMENT_INTELLIGENCE_KEY")
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                parser.error(f"Cannot read Azure configuration from {settings_path}: {exc}")
        if not endpoint:
            parser.error(
                "Set DOCUMENT_INTELLIGENCE_ENDPOINT in the environment or local.settings.json, "
                "or use --local-only."
            )
        document_intelligence = AzureLayoutExtractor(endpoint, key)
    store = LocalAuditStore(args.audit_file)
    result = ProcessingPipeline(PdfExtractor(document_intelligence), store).process(
        args.pdf.name, args.k_number, args.pdf.read_bytes(), force=args.force
    )
    print(json.dumps(result, indent=2))
    if args.export:
        conn = duckdb.connect()
        escaped = str(args.audit_file).replace("'", "''")
        target = str(args.export).replace("'", "''")
        fmt = "PARQUET" if args.export.suffix == ".parquet" else "CSV"
        conn.execute(
            f"COPY (SELECT * FROM read_json_auto('{escaped}')) TO '{target}' (FORMAT {fmt})"
        )


if __name__ == "__main__":
    main()
