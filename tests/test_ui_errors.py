"""Tests for app/errors.py: input validation and safe error messaging.
Confirms safe_error_message() never leaks the underlying exception type,
message, or a file path onto the page."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import errors  # noqa: E402

from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, PipelineStage  # noqa: E402


def test_validate_permit_number_rejects_empty_string():
    cleaned, error = errors.validate_permit_number("")
    assert cleaned is None
    assert error == "Please enter a permit number."


def test_validate_permit_number_rejects_whitespace_only():
    cleaned, error = errors.validate_permit_number("   ")
    assert cleaned is None
    assert error is not None


def test_validate_permit_number_strips_surrounding_whitespace():
    cleaned, error = errors.validate_permit_number("  21030-20000-00256  ")
    assert cleaned == "21030-20000-00256"
    assert error is None


def test_validate_permit_number_rejects_overly_long_input():
    cleaned, error = errors.validate_permit_number("1" * 101)
    assert cleaned is None
    assert error is not None


def test_validate_permit_number_accepts_input_at_max_length():
    raw = "1" * errors.MAX_PERMIT_NUMBER_LENGTH
    cleaned, error = errors.validate_permit_number(raw)
    assert cleaned == raw
    assert error is None


def test_validate_permit_number_does_not_reject_apostrophes_or_quotes():
    """UI-layer validation is a usability check only -- it must not reject
    input that's merely unusual; the security boundary is the escaping fix
    in ingestion/socrata.py, not this function."""
    cleaned, error = errors.validate_permit_number("21030-20000-00256'; DROP TABLE permits;--")
    assert error is None
    assert cleaned is not None


def test_safe_error_message_maps_known_pipeline_stages():
    for stage in PipelineStage:
        exc = PipelineExecutionError("TEST-1", stage, RuntimeError("boom"))
        message = errors.safe_error_message(exc)
        assert message == errors._STAGE_MESSAGES[stage]


def test_safe_error_message_never_leaks_exception_details():
    secret = "super-secret-internal-detail /Users/jamie/db.duckdb"
    exc = PipelineExecutionError("TEST-1", PipelineStage.JOURNEY_RECONSTRUCTION, RuntimeError(secret))
    message = errors.safe_error_message(exc)
    assert secret not in message
    assert "RuntimeError" not in message
    assert "Traceback" not in message


def test_safe_error_message_falls_back_to_generic_for_unexpected_exception_types():
    message = errors.safe_error_message(ValueError("some internal detail"))
    assert message == errors.GENERIC_ERROR_MESSAGE
