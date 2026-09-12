"""Extract explicitly labeled predicate lists and keep reference devices separate."""

import re
from typing import Literal

from .models import MatchStatus, PredicateCandidate, PredicateRelationship

K_NUMBER = re.compile(r"\b[Kk][0-9]{6}\b")
SPACED_K_NUMBER = re.compile(r"\b[Kk][ \t]*(?:[0-9][ \t]*){5}[0-9](?![0-9])")
RELATIONSHIP_HEADING = re.compile(
    r"^[ \t]*(?:(?:[A-Z]\.)?\d+\.|[IVX]+\.|[A-Z]\.[0-9]*\.?)[ \t]*"
    r"(?P<numbered>(?:primary |additional |secondary |reference )?predicate(?:\s+devices?)?"
    r"|reference\s+devices?)"
    r"|^[ \t]*(?P<plain>(?:primary |additional |secondary |reference )?predicate(?:\s+devices?)?"
    r"|reference\s+devices?)"
    r"|^[^\n]*Table\s+\d+:[^\n]*Equivalent Predicates[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)
SECTION_END = re.compile(
    r"^[ \t]*(?:(?:[A-Z]\.)?\d+\.|[IVX]+\.|[A-Z]\.)?[ \t]*"
    r"(?:Device\s+(?:Description|The\b)|Device\s*$|Indications|Intended Use|"
    r"Summary of|Performance|Technological|Comparison|[A-Z]\.\d+\.)",
    re.IGNORECASE | re.MULTILINE,
)


def normalize_k_numbers(text: str) -> str:
    """Join whitespace within otherwise valid identifiers; never guess a character."""
    return SPACED_K_NUMBER.sub(lambda match: re.sub(r"\s", "", match.group()).upper(), text)


def extract_predicates(
    source_k_number: str, text_by_page: dict[int, str]
) -> list[PredicateRelationship]:
    relationships: dict[str, PredicateRelationship] = {}
    for page_number, original_text in text_by_page.items():
        text = normalize_k_numbers(original_text)
        headings = list(RELATIONSHIP_HEADING.finditer(text))
        for index, heading in enumerate(headings):
            label = heading.group().lower()
            role: Literal["predicate", "primary", "additional", "reference"] = "predicate"
            if "reference" in label:
                role = "reference"
            elif "primary" in label:
                role = "primary"
            elif "additional" in label or "secondary" in label:
                role = "additional"
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            section = text[heading.start() : end]
            following_heading = SECTION_END.search(section, heading.end() - heading.start())
            if following_heading:
                section = section[: following_heading.start()]
            # Bound an unrecognized section rather than collecting the rest of a long page.
            section = section[:1800]
            for match in K_NUMBER.finditer(section):
                k_number = match.group().upper()
                if k_number == source_k_number.upper():
                    continue
                evidence = PredicateCandidate(
                    k_number=k_number,
                    page_number=page_number,
                    evidence=section.strip(),
                )
                existing = relationships.get(k_number)
                if existing is not None:
                    existing.evidence.append(evidence)
                    if role != "predicate" and existing.relationship_type == "predicate":
                        existing.relationship_type = role
                    elif role != "predicate" and existing.relationship_type != role:
                        existing.status = MatchStatus.AMBIGUOUS
                        existing.review_reason = (
                            "Conflicting relationship labels in source sections."
                        )
                    continue
                relationships[k_number] = PredicateRelationship(
                    source_k_number=source_k_number.upper(),
                    predicate_k_number=k_number,
                    status=MatchStatus.MATCHED,
                    relationship_type=role,
                    evidence=[evidence],
                )
    if not relationships:
        return [
            PredicateRelationship(source_k_number=source_k_number, status=MatchStatus.UNMATCHED)
        ]
    return list(relationships.values())
