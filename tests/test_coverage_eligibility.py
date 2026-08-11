from __future__ import annotations

from permit_stall_finder.analysis.coverage_eligibility import assess_eligibility


def test_bldg_new_ineligible_at_default_threshold():
    """§4b: 0.60 is chosen specifically to separate Bldg-New (50.3%) from
    types clearing 60%+."""
    result = assess_eligibility("Bldg-New")
    assert result.eligible is False
    assert result.observed_forward_match_rate == 0.503


def test_bldg_alter_repair_eligible_at_default_threshold():
    result = assess_eligibility("Bldg-Alter/Repair")
    assert result.eligible is True
    assert result.observed_forward_match_rate == 0.711


def test_unmeasured_permit_type_defaults_ineligible():
    result = assess_eligibility("Some-Type-Never-Measured")
    assert result.eligible is False
    assert result.observed_forward_match_rate is None
    assert result.sample_n == 0


def test_bldg_relocation_ineligible_low_sample():
    result = assess_eligibility("Bldg-Relocation")
    assert result.eligible is False
    assert result.sample_n == 9


def test_sensitivity_at_070_threshold_excludes_more_types():
    """§4b sensitivity table: at 0.70, Bldg-Addition (68.7%) becomes
    ineligible even though it passes at the 0.60 default."""
    at_60 = assess_eligibility("Bldg-Addition", min_coverage_rate=0.60)
    at_70 = assess_eligibility("Bldg-Addition", min_coverage_rate=0.70)
    assert at_60.eligible is True
    assert at_70.eligible is False


def test_sensitivity_at_050_threshold_makes_bldg_new_eligible():
    """Confirms the sensitivity table's claim that 0.50 is too permissive
    -- it would let Bldg-New through."""
    result = assess_eligibility("Bldg-New", min_coverage_rate=0.50)
    assert result.eligible is True
