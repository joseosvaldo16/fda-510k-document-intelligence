"""Deterministic extraction and reconciliation of FDA K-numbers."""

import re
from collections import defaultdict

from .models import MatchStatus, PredicateCandidate, PredicateRelationship

K_NUMBER = re.compile(r"\b[Kk][0-9]{6}\b")
PREDICATE_CONTEXT = re.compile(r"predicate|substantial(?:ly)?\s+equivalent", re.IGNORECASE)


def extract_predicates(
    source_k_number: str, text_by_page: dict[int, str]
) -> list[PredicateRelationship]:
    """Return evidence-backed relationships without guessing between candidates."""
    candidates: dict[str, list[PredicateCandidate]] = defaultdict(list)
    for page, text in text_by_page.items():
        for match in K_NUMBER.finditer(text):
            start, end = max(0, match.start() - 100), min(len(text), match.end() + 100)
            evidence = text[start:end].replace("\n", " ")
            if PREDICATE_CONTEXT.search(evidence):
                candidates[match.group().upper()].append(
                    PredicateCandidate(
                        k_number=match.group().upper(), page_number=page, evidence=evidence
                    )
                )
    if not candidates:
        return [
            PredicateRelationship(source_k_number=source_k_number, status=MatchStatus.UNMATCHED)
        ]
    if len(candidates) == 1:
        k_number, candidate_evidence = next(iter(candidates.items()))
        return [
            PredicateRelationship(
                source_k_number=source_k_number,
                predicate_k_number=k_number,
                status=MatchStatus.MATCHED,
                evidence=candidate_evidence,
            )
        ]
    return [
        PredicateRelationship(
            source_k_number=source_k_number,
            status=MatchStatus.AMBIGUOUS,
            candidates=sorted(candidates),
            evidence=[item for values in candidates.values() for item in values],
        )
    ]
