"""Regression cases for missed lists, reference roles, and false predicate links."""

from fda510k.matching import extract_predicates, normalize_k_numbers
from fda510k.models import MatchStatus


def test_all_list_entries_are_retained_as_separate_relationships() -> None:
    text = (
        "3. Predicate Devices:\nCatheter K043272\nOther catheter K002901\n"
        "Third catheter K092205\n4. Device Description:\nAccessory K555555"
    )
    result = extract_predicates("K111372", {1: text})
    assert {r.predicate_k_number for r in result} == {"K043272", "K002901", "K092205"}
    assert all(r.status == MatchStatus.MATCHED for r in result)
    assert all(r.evidence[0].page_number == 1 for r in result)


def test_reference_devices_are_separate_from_primary_and_additional_predicates() -> None:
    text = (
        "Primary Predicate\nDevice K160702 Plate\nAdditional Predicate\n"
        "Device K080646 Other plate\nReference Devices K160313 Cage\n"
        "K191074 Graft\nDevice Description\nUnrelated K999999"
    )
    result = extract_predicates("K213456", {4: text})
    assert {r.predicate_k_number: r.relationship_type for r in result} == {
        "K160702": "primary",
        "K080646": "additional",
        "K160313": "reference",
        "K191074": "reference",
    }


def test_self_number_is_never_a_predicate() -> None:
    result = extract_predicates("K140814", {1: "Predicate device: K140814"})
    assert result[0].status == MatchStatus.UNMATCHED


def test_whitespace_normalization_preserves_surrounding_words_and_never_guesses_letters() -> None:
    assert normalize_k_numbers("K1 11295 Catheter") == "K111295 Catheter"
    assert normalize_k_numbers("Kill295 Catheter") == "Kill295 Catheter"


def test_conflicting_explicit_roles_require_review() -> None:
    result = extract_predicates(
        "K999999", {1: "Primary Predicate: K123456", 2: "Reference Devices: K123456"}
    )
    assert result[0].status == MatchStatus.AMBIGUOUS


def test_description_column_does_not_end_a_predicate_table() -> None:
    text = (
        "Table 1: Substantially Equivalent Predicates\nManufacturer\nDescription\n"
        "Submission Number\nCompany\nPlate\nK132886\nCompany\nInstrument\nK123055\n"
        "Summary of Pre-Clinical Testing\nAccessory K999999"
    )
    result = extract_predicates("K140814", {2: text})
    assert {r.predicate_k_number for r in result} == {"K132886", "K123055"}
