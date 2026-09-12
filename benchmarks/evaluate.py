"""Compare matchers against visually reviewed labels without sending labels to the model."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from benchmarks.legacy_matching import extract_predicates as legacy_match
from fda510k.azure_di import AzureLayoutExtractor
from fda510k.extractors import PdfExtractor
from fda510k.llm import LlmReviewer
from fda510k.matching import extract_predicates
from fda510k.models import ExtractionResult, MatchStatus


def score_sets(expected: set[str], predicted: set[str]) -> dict[str, int]:
    return {
        "true_positives": len(expected & predicted),
        "false_positives": len(predicted - expected),
        "false_negatives": len(expected - predicted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=["legacy", "rules", "llm"], required=True)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--labels", type=Path, default=Path("benchmarks/fda_predicates.json"))
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extraction-cache", type=Path)
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text())
    settings_path = Path("local.settings.json")
    settings = json.loads(settings_path.read_text())["Values"] if settings_path.exists() else {}
    endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT") or settings.get(
        "DOCUMENT_INTELLIGENCE_ENDPOINT"
    )
    llm_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or settings.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or settings.get("AZURE_OPENAI_DEPLOYMENT")
    if args.ocr and not endpoint:
        parser.error("OCR requires DOCUMENT_INTELLIGENCE_ENDPOINT.")
    if args.method == "llm" and (not llm_endpoint or not deployment):
        parser.error("LLM mode requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT.")
    extractor = PdfExtractor(AzureLayoutExtractor(endpoint) if args.ocr else None)
    reviewer = LlmReviewer(llm_endpoint, deployment) if args.method == "llm" else None
    rows = []
    args.corpus.mkdir(parents=True, exist_ok=True)
    raw_output = Path("data/benchmark") / (args.method + ("-ocr" if args.ocr else "-native"))
    raw_output.mkdir(parents=True, exist_ok=True)
    for document in labels["documents"]:
        source = document["source_k_number"]
        pdf_path = args.corpus / f"{source}.pdf"
        if not pdf_path.exists() and args.download:
            response = httpx.get(document["url"], timeout=60, follow_redirects=True)
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != document["sha256"]:
                raise ValueError(f"Downloaded PDF hash changed: {source}. Review before scoring.")
            pdf_path.write_bytes(response.content)
        content = pdf_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != document["sha256"]:
            raise ValueError(f"PDF hash mismatch: {source}.")
        started = time.monotonic()
        if args.extraction_cache:
            cached = json.loads((args.extraction_cache / f"{source}.json").read_text())
            extraction = ExtractionResult.model_validate(cached["extraction"])
            if extraction.sha256 != digest:
                raise ValueError(f"Cached extraction hash mismatch: {source}")
        else:
            extraction = extractor.extract(pdf_path.name, digest, content)
        if reviewer:
            reviewer.review_ocr(extraction, content, source)
            relationships = reviewer.match(source, extraction)
        elif args.method == "legacy":
            relationships = legacy_match(source, extraction.text_by_page)
        else:
            relationships = extract_predicates(source, extraction.text_by_page)
        for relationship in relationships:
            if any(e.page_number in extraction.unresolved_ocr_pages for e in relationship.evidence):
                relationship.status = MatchStatus.AMBIGUOUS
                relationship.review_reason = "Unresolved OCR identifier on an evidence page."
        predicates = set()
        references = set()
        predicted_roles = set()
        for relationship in relationships:
            if args.method == "legacy":
                predicates.update(relationship.candidates)
            if relationship.predicate_k_number and (
                relationship.status == MatchStatus.MATCHED or args.method == "legacy"
            ):
                target = relationship.predicate_k_number
                if relationship.relationship_type == "reference":
                    references.add(target)
                else:
                    predicates.add(target)
                predicted_roles.add((target, relationship.relationship_type))
        expected_predicates = {
            r["k_number"]
            for r in document["relationships"]
            if r["relationship_type"] != "reference"
        }
        expected_references = {
            r["k_number"]
            for r in document["relationships"]
            if r["relationship_type"] == "reference"
        }
        expected_roles = {
            (r["k_number"], r["relationship_type"]) for r in document["relationships"]
        }
        review_count = sum(r.status == MatchStatus.AMBIGUOUS for r in relationships)
        row = {
            "source_k_number": source,
            **score_sets(expected_predicates, predicates),
            "reference_scores": score_sets(expected_references, references),
            "predicted_predicates": sorted(predicates),
            "predicted_references": sorted(references),
            "exact_relationships": predicted_roles == expected_roles and review_count == 0,
            "review_count": review_count,
            "used_ocr": extraction.used_document_intelligence,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "review_notes": extraction.review_notes,
        }
        rows.append(row)
        (raw_output / f"{source}.json").write_text(
            json.dumps(
                {
                    "extraction": extraction.model_dump(mode="json"),
                    "relationships": [r.model_dump(mode="json") for r in relationships],
                },
                indent=2,
            )
            + "\n"
        )
        print(
            f"{source}: TP={row['true_positives']} FP={row['false_positives']} "
            f"FN={row['false_negatives']} review={review_count}",
            flush=True,
        )
    tp, fp, fn = [
        sum(row[key] for row in rows)
        for key in ["true_positives", "false_positives", "false_negatives"]
    ]
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": args.method,
        "ocr_enabled": args.ocr,
        "reused_extraction": args.extraction_cache is not None,
        "model": deployment if reviewer else None,
        "labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
        "documents": len(rows),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp else 0,
        "exact_relationship_documents": sum(row["exact_relationships"] for row in rows),
        "reference_scores": {
            key: sum(row["reference_scores"][key] for row in rows)
            for key in ["true_positives", "false_positives", "false_negatives"]
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
