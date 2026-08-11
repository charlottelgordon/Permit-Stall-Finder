"""Tests for the permit-level administrative/documentary-permit exemption
layer (analysis/inspection_exemption.py). Fixes the false positive on the
real, verified permit 18010-20001-05038 -- see AGENT2_DESIGN.md."""

from __future__ import annotations

from permit_stall_finder.analysis.inspection_exemption import assess_inspection_exemption


def test_known_administrative_correction_permit_is_plausibly_exempt():
    """18010-20001-05038's real, verified data: $0 valuation, work_desc
    referencing a supplemental correction to a prior permit number."""
    result = assess_inspection_exemption(
        "18010-20001-05038",
        "SUPPLEMENTAL TO 18010-20000-05038:  TO CORRECT LEGAL DESCRIPTION DUE TO TRACT MAP RECORDATION",
        0.0,
    )
    assert result.is_plausibly_exempt is True
    assert result.is_ambiguous is False
    assert "zero_valuation" in result.matched_signals


def test_normal_construction_permit_is_not_exempt():
    """20010-20000-02739's real data: real valuation, ordinary construction
    work_desc -- must proceed to the normal eligibility path."""
    result = assess_inspection_exemption(
        "20010-20000-02739", "NEW SFD/GARAGE, PLAN 1BR, TRACT 50505", 556000.0
    )
    assert result.is_plausibly_exempt is False
    assert result.is_ambiguous is False
    assert result.matched_signals == []


def test_only_zero_valuation_is_ambiguous_not_exempt():
    """22014-10001-04999's real data: $0 valuation, but work_desc describes
    a real scope change (not a documentary correction) -- only one signal,
    must not be silently treated as exempt."""
    result = assess_inspection_exemption(
        "22014-10001-04999", "SUPPLEMENTAL PERMIT TO INCREASE BUILDING HEIGHT AND REVISE CEILING HEIGHTS", 0.0
    )
    assert result.is_plausibly_exempt is False
    assert result.is_ambiguous is True
    assert result.matched_signals == ["zero_valuation"]


def test_only_administrative_language_without_zero_valuation_is_ambiguous():
    result = assess_inspection_exemption(
        "TEST-1", "SUPPLEMENTAL TO 12345-00000-00001 TO CORRECT LEGAL DESCRIPTION", 15000.0
    )
    assert result.is_plausibly_exempt is False
    assert result.is_ambiguous is True
    assert "zero_valuation" not in result.matched_signals


def test_no_work_description_is_not_exempt_not_ambiguous():
    result = assess_inspection_exemption("TEST-1", None, 15000.0)
    assert result.is_plausibly_exempt is False
    assert result.is_ambiguous is False


def test_matching_is_case_insensitive():
    result = assess_inspection_exemption("TEST-1", "supplemental to 12345-00000-00001 to correct legal description", 0.0)
    assert result.is_plausibly_exempt is True
