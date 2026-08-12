"""Input validation and safe error messaging. Never surfaces a stack
trace, a file path, or the raw exception text to the page -- see
research/UI_DESIGN.md §4.

Note on the permit-number escaping issue found during UI-integration
review: it's fixed upstream (ingestion/socrata.py::escape_soql_string(),
applied in ingestion/permits.py), not here. validate_permit_number() below
is a UI-layer usability check (reject empty input before even calling the
pipeline) -- not a security boundary; the security fix lives in Agent 1's
ingestion layer where the query is actually built.
"""

from __future__ import annotations

from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, PipelineStage

MAX_PERMIT_NUMBER_LENGTH = 100


def validate_permit_number(raw_input: str) -> tuple[str | None, str | None]:
    """Returns (cleaned_permit_number, error_message). Exactly one of the
    two is non-None."""
    cleaned = raw_input.strip()
    if not cleaned:
        return None, "Please enter a permit number."
    if len(cleaned) > MAX_PERMIT_NUMBER_LENGTH:
        return None, "That doesn't look like a permit number -- it's too long."
    return cleaned, None


_STAGE_MESSAGES: dict[PipelineStage, str] = {
    PipelineStage.JOURNEY_RECONSTRUCTION: (
        "We couldn't retrieve this permit's record right now -- the city's open data "
        "service may be temporarily unavailable."
    ),
    PipelineStage.STALL_DETECTION: (
        "We retrieved this permit's record, but couldn't complete the comparison "
        "analysis right now -- the city's open data service may be temporarily unavailable."
    ),
    PipelineStage.DEVELOPER_EXPLANATION: (
        "We completed the analysis but couldn't generate the explanation right now. "
        "Please try again shortly."
    ),
}

GENERIC_ERROR_MESSAGE = "Something went wrong while analyzing this permit. Please try again shortly."


def safe_error_message(exc: Exception) -> str:
    """Maps any exception the pipeline call might raise to a message safe
    to show a user -- no exception type, no file path, no traceback."""
    if isinstance(exc, PipelineExecutionError):
        return _STAGE_MESSAGES.get(exc.stage, GENERIC_ERROR_MESSAGE)
    return GENERIC_ERROR_MESSAGE
