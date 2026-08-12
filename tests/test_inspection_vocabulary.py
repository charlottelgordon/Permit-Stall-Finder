"""Vocabulary normalization tests, including refinement #4's load-bearing
requirement: an unmapped/unknown raw value must route visibly to UNKNOWN
(results) or None (stages) -- never silently inherit an existing category."""

from __future__ import annotations

from permit_stall_finder.schema.inspection_vocabulary import (
    ResultFamily,
    inspection_stage,
    is_substantive,
    result_family,
    result_mapping_metadata,
    stage_mapping_metadata,
)


def test_known_result_maps_to_its_assigned_family():
    assert result_family("Approved") == ResultFamily.APPROVED
    assert result_family("Corrections Issued") == ResultFamily.CORRECTIONS
    assert result_family("Insp Scheduled") == ResultFamily.SCHEDULED
    assert result_family("Insp Cancelled") == ResultFamily.CANCELLED


def test_never_before_seen_result_routes_to_unknown_not_an_existing_family():
    """The load-bearing case: a synthetic value that is definitely not in
    the mapping table must not be silently coerced into any real family."""
    assert result_family("Some Brand New Result Never Seen Before 12345") == ResultFamily.UNKNOWN


def test_null_or_empty_result_is_unknown():
    assert result_family(None) == ResultFamily.UNKNOWN
    assert result_family("") == ResultFamily.UNKNOWN


def test_known_type_maps_to_a_stage():
    assert inspection_stage("Footing/Foundation/Slab") == "FOUNDATION_EARTHWORK"


def test_deliberately_unmapped_known_type_stays_unmapped():
    """'Inspection' is a real, high-volume raw value that was deliberately
    left unmapped (§5b) rather than force-fit into a stage."""
    assert inspection_stage("Inspection") is None


def test_never_before_seen_type_routes_to_none_not_an_existing_stage():
    assert inspection_stage("Some Brand New Inspection Type Never Seen 12345") is None


def test_substantive_family_filter():
    assert is_substantive("Approved") is True
    assert is_substantive("Corrections Issued") is True
    assert is_substantive("Not Ready for Inspection") is True
    assert is_substantive("Partial Approval") is True
    assert is_substantive("Insp Scheduled") is False
    assert is_substantive("Insp Cancelled") is False
    assert is_substantive("Permit Finaled") is False
    assert is_substantive(None) is False


def test_mapping_files_carry_versioning_metadata():
    """Refinement #4: source_dataset_id, vocabulary_extraction_date,
    mapping_version must be present."""
    result_meta = result_mapping_metadata()
    for key in ("source_dataset_id", "vocabulary_extraction_date", "mapping_version"):
        assert key in result_meta
    assert result_meta["source_dataset_id"] == "9w5z-rg2h"

    stage_meta = stage_mapping_metadata()
    for key in ("source_dataset_id", "vocabulary_extraction_date", "mapping_version"):
        assert key in stage_meta
