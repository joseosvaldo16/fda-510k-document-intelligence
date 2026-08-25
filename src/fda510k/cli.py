"""Command-line entry point for local processing and exports."""

import argparse
import json
from pathlib import Path

import duckdb

from .extractors import PdfExtractor
from .pipeline import ProcessingPipeline
from .storage import LocalAuditStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Process an FDA 510(k) PDF.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--k-number", required=True)
    parser.add_argument("--audit-file", type=Path, default=Path("data/audit.jsonl"))
    parser.add_argument("--export", type=Path, help="Write audit records as CSV or Parquet.")
    args = parser.parse_args()
    store = LocalAuditStore(args.audit_file)
    result = ProcessingPipeline(PdfExtractor(), store).process(
        args.pdf.name, args.k_number, args.pdf.read_bytes()
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
