"""LLM suggestions must pass source checks before becoming matched relationships."""

import pytest

from fda510k.llm import (
    LlmRelationship,
    LlmRelationships,
    OcrFinding,
    OcrFindings,
    apply_ocr_findings,
    validate_relationships,
)
from fda510k.models import ExtractionResult, MatchStatus, OcrWord


def test_source_supported_llm_relationship_is_accepted() -> None:
    quote = "Primary Predicate: K123456 Device"
    response = LlmRelationships(
        relationships=[
            LlmRelationship(
                k_number="K123456",
                relationship_type="primary",
                page_number=4,
                start_line=1,
                end_line=1,
            )
        ]
    )
    result = validate_relationships("K654321", {4: quote}, response)
    assert result[0].status == MatchStatus.MATCHED
    assert result[0].relationship_type == "primary"


@pytest.mark.parametrize(
    "number,page,quote,role",
    [
        ("K654321", 4, "Primary Predicate: K654321", "primary"),
        ("K123456", 5, "Primary Predicate: K123456 Device", "primary"),
        ("K999999", 4, "Primary Predicate: K123456 Device", "primary"),
        ("K123456", 4, "Invented text K123456", "primary"),
        ("K123456", 4, "Primary Predicate: K123456 Device", "reference"),
    ],
)
def test_unsupported_llm_answers_remain_review_items(
    number: str, page: int, quote: str, role: str
) -> None:
    response = LlmRelationships.model_validate(
        {
            "relationships": [
                {
                    "k_number": number,
                    "page_number": page,
                    "start_line": 1,
                    "end_line": 1 if quote != "Invented text K123456" else 9,
                    "relationship_type": role,
                }
            ]
        }
    )
    result = validate_relationships("K654321", {4: "Primary Predicate: K123456 Device"}, response)
    assert result[0].status == MatchStatus.AMBIGUOUS
    assert result[0].review_reason


def test_empty_llm_result_does_not_erase_rule_candidates() -> None:
    result = validate_relationships(
        "K654321", {1: "Predicate Device: K123456"}, LlmRelationships(relationships=[])
    )
    assert result[0].predicate_k_number == "K123456"
    assert result[0].status == MatchStatus.AMBIGUOUS


def test_vision_suggestion_alone_cannot_replace_uncertain_ocr() -> None:
    extraction = ExtractionResult(
        document_id="test",
        sha256="test",
        extractor="azure-layout",
        page_count=1,
        text_by_page={1: "Predicate K1O3456"},
        ocr_words=[OcrWord(page_number=1, text="K1O3456", confidence=0.7)],
    )
    findings = OcrFindings(
        findings=[OcrFinding(original="K1O3456", corrected="K103456", readable=True)]
    )
    apply_ocr_findings(extraction, 1, ["K1O3456"], findings)
    assert extraction.text_by_page[1] == "Predicate K1O3456"
    assert extraction.unresolved_ocr_pages == [1]


def test_vision_repair_requires_agreement_with_a_strong_ocr_occurrence() -> None:
    extraction = ExtractionResult(
        document_id="test",
        sha256="test",
        extractor="azure-layout",
        page_count=2,
        text_by_page={1: "Predicate K1O3456", 2: "Predicate K103456"},
        ocr_words=[
            OcrWord(page_number=1, text="K1O3456", confidence=0.7),
            OcrWord(page_number=2, text="K103456", confidence=0.99),
        ],
    )
    findings = OcrFindings(
        findings=[OcrFinding(original="K1O3456", corrected="K103456", readable=True)]
    )
    apply_ocr_findings(extraction, 1, ["K1O3456"], findings)
    assert extraction.text_by_page[1] == "Predicate K103456"
    assert extraction.ocr_words[0].text == "K1O3456"
    assert extraction.unresolved_ocr_pages == []
