"""Downloadable report -- one self-contained HTML file covering every
permit currently shown in the results table, for someone who wants to
save/print the full detail rather than read it on screen (Phase 17).

A single combined document rather than one file per permit: Streamlit's
st.download_button only ever offers one file per click, and a print-
friendly page-break before each permit's section gets the same practical
result (open it, print it, each permit starts on its own page) without
needing a zip archive.

Every sentence of content here is built from the exact same i18n/
formatting functions the on-screen Permit Details view uses (category_label,
severity_label, top_finding_bullet, plain_coverage_gap, ...) -- this module
only wraps that same already-worded text in plain HTML instead of Streamlit
widgets. It invents no new analysis or phrasing of its own, same as every
other section renderer.

Content per permit, in reading order (not the two-column on-screen layout,
which doesn't translate to a printed page): overview facts, Top Findings
bullets, full finding-by-finding detail (metrics, explanations, steps,
sources -- everything the right panel's cards show), Permit Journey,
Other Permits at this address (one live fetch per permit, same call the
on-screen expander makes), Resources, Data Limitations, and the
disclaimer.
"""

from __future__ import annotations

import html as html_lib
from datetime import datetime, timezone

import streamlit as st

import portfolio
from errors import GENERIC_ERROR_MESSAGE
from formatting import kb_entry_by_id
from i18n import (
    APP_NAME,
    category_label,
    cohort_basis_caption,
    data_quality_flag_label,
    days_vs_typical_phrase,
    count_vs_typical_phrase,
    extra_count_metric_label,
    extra_time_metric_label,
    get_language,
    grounding_strength_label,
    interval_state_label,
    benchmark_semantics_label,
    match_status_label,
    plain_coverage_gap,
    severity_label,
    t,
    top_finding_bullet,
    translate_error_message,
    unusualness_phrase,
    verification_status_label,
)
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.knowledge_base.loader import KnowledgeBase
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult
from permit_stall_finder.schema.developer_explanation import DeveloperExplanation, GroundingStatus
from permit_stall_finder.schema.stall_detection import DelayStallDetection

_STYLE = """
body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a1a; line-height: 1.5; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
h1 { border-bottom: 3px solid #052D49; padding-bottom: 0.5rem; }
h2 { color: #052D49; margin-top: 2rem; }
h3 { margin-bottom: 0.25rem; }
.severity-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; color: white; }
.finding-card { border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
.caption { color: #666; font-size: 0.9em; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; font-size: 0.9em; }
.permit-section { page-break-before: always; }
.permit-section:first-of-type { page-break-before: auto; }
.disclaimer { font-style: italic; color: #555; border-top: 1px solid #ccc; padding-top: 1rem; margin-top: 2rem; }
@media print { a { color: inherit; text-decoration: underline; } }
"""

_SEVERITY_HEX = {
    "SEVERE": "#B0553F",
    "ELEVATED": "#B8860B",
    "WATCH": "#5B7A99",
    "UNSCORED": "#888888",
}


def _esc(value: object) -> str:
    return html_lib.escape(str(value))


def _severity_badge_html(detection) -> str:
    label = severity_label(detection.severity)
    color = _SEVERITY_HEX.get(label.upper(), "#888888")
    return f'<span class="severity-badge" style="background-color:{color}">{_esc(label)}</span>'


def _metrics_html(detection) -> str:
    parts = []
    if isinstance(detection, DelayStallDetection):
        parts.append(f"<strong>{_esc(t('elapsed_days_metric'))}:</strong> {detection.elapsed_days} {_esc(t('days_suffix'))}")
        if detection.percentile_rank is not None:
            parts.append(f"<strong>{_esc(t('how_unusual_metric'))}:</strong> {_esc(unusualness_phrase(detection.percentile_rank))}")
        if detection.excess_days_vs_median is not None:
            label = extra_time_metric_label(detection.cohort.benchmark_semantics)
            phrase = days_vs_typical_phrase(detection.excess_days_vs_median, detection.cohort.benchmark_semantics)
            parts.append(f"<strong>{_esc(label)}:</strong> {_esc(phrase)}")
        caption = (
            f"{interval_state_label(detection.interval_state)} · "
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"({cohort_basis_caption(detection.cohort.n, detection.cohort.confidence)})"
        )
    else:
        parts.append(f"<strong>{_esc(t('observed_count_metric'))}:</strong> {detection.observed_count}")
        if detection.percentile_rank is not None:
            parts.append(f"<strong>{_esc(t('how_unusual_metric'))}:</strong> {_esc(unusualness_phrase(detection.percentile_rank))}")
        if detection.excess_count_vs_median is not None:
            label = extra_count_metric_label(detection.cohort.benchmark_semantics)
            phrase = count_vs_typical_phrase(detection.excess_count_vs_median, detection.cohort.benchmark_semantics)
            parts.append(f"<strong>{_esc(label)}:</strong> {_esc(phrase)}")
        caption = (
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"({cohort_basis_caption(detection.cohort.n, detection.cohort.confidence)})"
        )
    return (
        "<p>" + " &nbsp;|&nbsp; ".join(parts) + "</p>"
        f'<p class="caption">{_esc(caption)}</p>'
    )


def _steps_html(heading: str, steps, placeholder: str) -> str:
    if not steps:
        return f'<p><strong>{_esc(heading)}</strong></p><p class="caption">{_esc(placeholder)}</p>'
    items = "".join(
        f"<li>{_esc(step.text)} <em>({_esc(grounding_strength_label(step.grounding_strength))})</em></li>"
        for step in steps
    )
    return f"<p><strong>{_esc(heading)}</strong></p><ul>{items}</ul>"


def _source_grounding_html(explanation: DeveloperExplanation, kb: KnowledgeBase) -> str:
    entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
    if entry is None:
        return f'<p><strong>{_esc(t("source_and_grounding"))}</strong></p><p class="caption">{_esc(t("no_kb_entry"))}</p>'
    parts = [
        f'<p><strong>{_esc(t("source_and_grounding"))}</strong></p>',
        f'<p class="caption">Knowledge-base entry {_esc(entry.entry_id)} · v{_esc(entry.kb_version)} '
        f"· last reviewed {_esc(entry.last_reviewed.isoformat())}</p>",
    ]
    for source in entry.sources:
        parts.append(
            f'<p>- <a href="{_esc(source.url)}">{_esc(source.title)}</a> — {_esc(source.publisher)}<br>'
            f'<span class="caption">{_esc(verification_status_label(source.verification_status))} '
            f"(retrieved {_esc(source.retrieved_date.isoformat())})</span></p>"
        )
    if entry.caveats:
        parts.append(f'<p><strong>{_esc(t("caveats_on_guidance"))}</strong></p>')
        parts.append("<ul>" + "".join(f"<li>{_esc(c)}</li>" for c in entry.caveats) + "</ul>")
    return "".join(parts)


def _finding_card_html(detection, explanation: DeveloperExplanation, kb: KnowledgeBase) -> str:
    what_means_heading = (
        t("no_entry_heading")
        if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE
        else t("what_this_usually_means")
    )
    learn_more = ""
    if explanation.grounding_status == GroundingStatus.GROUNDED:
        entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
        if entry is not None and entry.sources:
            links = "".join(f'<li><a href="{_esc(s.url)}">{_esc(s.title)}</a></li>' for s in entry.sources)
            learn_more = f'<p><strong>{_esc(t("learn_more_this_finding"))}</strong></p><ul>{links}</ul>'

    caveats_html = ""
    if detection.caveats:
        caveats_html = f'<p><strong>{_esc(t("caveats"))}</strong></p><ul>' + "".join(
            f"<li>{_esc(c)}</li>" for c in detection.caveats
        ) + "</ul>"

    limitations_html = ""
    if explanation.limitations:
        limitations_html = f'<p><strong>{_esc(t("cannot_tell"))}</strong></p><ul>' + "".join(
            f"<li>{_esc(item)}</li>" for item in explanation.limitations
        ) + "</ul>"

    return (
        '<div class="finding-card">'
        f"<h3>{_esc(category_label(detection.category))} {_severity_badge_html(detection)}</h3>"
        f"{_metrics_html(detection)}"
        f"{learn_more}"
        f'<p><strong>{_esc(t("what_data_shows"))}</strong></p><p>{_esc(explanation.what_the_data_shows)}</p>'
        f'<p><strong>{_esc(what_means_heading)}</strong></p><p>{_esc(explanation.what_this_usually_means)}</p>'
        f'{_steps_html(t("steps_you_can_take"), explanation.developer_actionable_steps, t("no_developer_steps"))}'
        f'{_steps_html(t("steps_depend_on_city"), explanation.city_dependent_steps, t("no_city_steps"))}'
        f"{limitations_html}"
        f"{caveats_html}"
        f"{_source_grounding_html(explanation, kb)}"
        "</div>"
    )


def _permit_journey_html(journey) -> str:
    parts = [f"<h2>{_esc(t('drill_down_permit_journey'))}</h2>"]
    snapshot = journey.latest_snapshot
    if snapshot is None:
        parts.append(f"<p>{_esc(t('no_journey_record'))}</p>")
        return "".join(parts)

    if journey.inspection_events:
        parts.append(f"<p><strong>{_esc(t('observed_inspections'))}</strong></p>")
        rows = "".join(
            f"<tr><td>{_esc(e.inspection_date.isoformat())}</td><td>{_esc(e.inspection_type)}</td>"
            f"<td>{_esc(e.inspection_result)}</td></tr>"
            for e in journey.inspection_events
        )
        parts.append(
            f"<table><tr><th>{_esc(t('col_date'))}</th><th>{_esc(t('col_type'))}</th>"
            f"<th>{_esc(t('col_result'))}</th></tr>{rows}</table>"
        )

    derived = journey.derived
    if derived is not None:
        rows = []
        if derived.days_submitted_to_issuance is not None:
            rows.append((t("submitted_to_issued"), f"{derived.days_submitted_to_issuance} {t('days_suffix')}"))
        if derived.days_issuance_to_first_inspection is not None:
            rows.append((t("issued_to_first_inspection"), f"{derived.days_issuance_to_first_inspection} {t('days_suffix')}"))
        if derived.total_observed_elapsed_days is not None:
            rows.append((t("total_observed_span"), f"{derived.total_observed_elapsed_days} {t('days_suffix')}"))
        if rows:
            parts.append(f"<p><strong>{_esc(t('derived_metrics'))}</strong></p><ul>")
            parts.extend(f"<li>{_esc(label)}: {_esc(value)}</li>" for label, value in rows)
            parts.append("</ul>")

    if journey.not_observed_notes:
        parts.append(f"<p><strong>{_esc(t('not_observed'))}</strong></p><ul>")
        parts.extend(f"<li>{_esc(note)}</li>" for note in journey.not_observed_notes)
        parts.append("</ul>")

    return "".join(parts)


def _other_permits_html(result: PermitAnalysisResult) -> str:
    parts = [f"<h2>{_esc(t('drill_down_other_permits'))}</h2>"]
    address = portfolio.address_of(result)
    if address == "—":
        parts.append(f'<p class="caption">{_esc(t("no_other_permits_found"))}</p>')
        return "".join(parts)
    try:
        matches = fetch_permits_by_address(address)
    except Exception:
        parts.append(f'<p class="caption">{_esc(t("no_other_permits_found"))}</p>')
        return "".join(parts)

    others = [m for m in matches if m.get("permit_nbr") and m.get("permit_nbr") != result.permit_number]
    if not others:
        parts.append(f'<p class="caption">{_esc(t("no_other_permits_found"))}</p>')
        return "".join(parts)

    parts.append("<ul>")
    for row in others:
        permit_type = row.get("permit_type") or "—"
        status_desc = row.get("status_desc") or "—"
        parts.append(f"<li><strong>{_esc(row['permit_nbr'])}</strong> — {_esc(permit_type)} — {_esc(status_desc)}</li>")
    parts.append("</ul>")
    return "".join(parts)


def _resources_html() -> str:
    from sections.next_best_action import (
        LADBS_311_LINE,
        LADBS_CASE_MANAGEMENT_CONTACT,
        LADBS_OUTSIDE_LA_PHONE,
        LADBS_PERMIT_STATUS_URL,
        LADBS_RECORDS_SEARCH_URL,
    )

    return (
        f"<h2>{_esc(t('resources_header'))}</h2>"
        f'<p><strong>{_esc(t("next_best_action"))}</strong></p>'
        f'<p>→ <a href="{_esc(LADBS_PERMIT_STATUS_URL)}">{_esc(t("confirm_status_link"))}</a> '
        f"— {_esc(t('authoritative_source_note'))}</p>"
        f'<p>→ <a href="{_esc(LADBS_RECORDS_SEARCH_URL)}">{_esc(t("search_records_link"))}</a></p>'
        f'<p><strong>{_esc(t("talk_to_a_person"))}</strong></p>'
        f"<p>{_esc(t('call_prefix'))} {_esc(LADBS_311_LINE)} {_esc(t('or'))} {_esc(LADBS_OUTSIDE_LA_PHONE)} {_esc(t('call_line_text'))}</p>"
        f"<p>{_esc(t('deeper_attention_prefix'))} {_esc(LADBS_CASE_MANAGEMENT_CONTACT)}</p>"
    )


def _data_limitations_html(result: PermitAnalysisResult) -> str:
    if not result.coverage_gaps and not result.data_quality_flags:
        return ""
    parts = [f"<h2>{_esc(t('coverage_notes_header'))}</h2>", f"<p>{_esc(t('coverage_notes_warning'))}</p>"]
    if result.coverage_gaps:
        parts.append(f'<p><strong>{_esc(t("coverage_gaps_label"))}</strong></p><ul>')
        parts.extend(f"<li>{_esc(plain_coverage_gap(gap))}</li>" for gap in result.coverage_gaps)
        parts.append("</ul>")
    if result.data_quality_flags:
        parts.append(f'<p><strong>{_esc(t("data_quality_notes_label"))}</strong></p><ul>')
        parts.extend(f"<li>{_esc(data_quality_flag_label(flag))}</li>" for flag in result.data_quality_flags)
        parts.append("</ul>")
    return "".join(parts)


def _permit_section_html(permit_number: str, cached, kb: KnowledgeBase) -> str:
    if isinstance(cached, str) or cached is None:
        message = translate_error_message(cached if isinstance(cached, str) else GENERIC_ERROR_MESSAGE)
        return (
            f'<div class="permit-section"><h1>{_esc(permit_number)}</h1>'
            f"<p>{_esc(message)}</p></div>"
        )

    result: PermitAnalysisResult = cached
    row = portfolio.summarize_result(result)
    snapshot = result.journey.latest_snapshot

    type_lines = [match_status_label(result.journey.match_status)]
    permit_type_line = row.permit_type
    if snapshot and snapshot.permit_sub_type:
        permit_type_line += f" — {snapshot.permit_sub_type}"
    type_lines.append(permit_type_line)
    if snapshot and snapshot.work_description:
        type_lines.append(snapshot.work_description)

    detections = result.stall_assessment.detections
    top_findings_html = ""
    if detections:
        bullets = "".join(f"<li>{_esc(top_finding_bullet(d))}</li>" for d in detections)
        top_findings_html = f"<h2>{_esc(t('qg_top_findings'))}</h2><ul>{bullets}</ul>"

    findings_detail_html = ""
    if detections:
        cards = "".join(
            _finding_card_html(d, e, kb)
            for d, e in zip(detections, result.developer_explanations.explanations)
        )
        findings_detail_html = f"<h2>{_esc(t('stall_findings_header'))}</h2>{cards}"

    return (
        '<div class="permit-section">'
        f"<h1>{_esc(permit_number)}</h1>"
        "<h2>Overview</h2>"
        f'<p><strong>{_esc(t("qg_address"))}:</strong> {_esc(row.address)}</p>'
        f'<p><strong>{_esc(t("qg_type"))}:</strong><br>' + "<br>".join(_esc(l) for l in type_lines) + "</p>"
        f'<p><strong>{_esc(t("qg_status"))}:</strong> {_esc(row.status_desc)}</p>'
        f'<p><strong>{_esc(t("qg_issuance_status"))}:</strong> {_esc(row.issuance_status)}</p>'
        f'<p><strong>{_esc(t("qg_last_update"))}:</strong> {_esc(row.last_status_update)}</p>'
        f"{top_findings_html}"
        f"{findings_detail_html}"
        f"{_permit_journey_html(result.journey)}"
        f"{_other_permits_html(result)}"
        f"{_resources_html()}"
        f"{_data_limitations_html(result)}"
        f'<p class="disclaimer">{_esc(result.developer_explanations.disclaimer)}</p>'
        "</div>"
    )


def build_report_html(permit_numbers: list[str], results_cache: dict, kb: KnowledgeBase) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = "".join(_permit_section_html(p, results_cache.get(p), kb) for p in permit_numbers)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(t('drill_down_header'))}</title>"
        f"<style>{_STYLE}</style></head><body>"
        f"<p class='caption'>Generated {generated} · {_esc(APP_NAME)}</p>"
        f"{sections}"
        "</body></html>"
    )


@st.cache_data(show_spinner=False, ttl=300)
def _cached_report_html(
    permit_numbers: tuple[str, ...], language: str, _results_cache: dict, _kb: KnowledgeBase
) -> str:
    """Cached by (permit set, language) -- st.download_button's data=
    argument has to be fully computed on every script run where the
    button appears, not just on click, and this report includes a live
    fetch_permits_by_address() call per permit for "Other permits at
    this address" (the same call the on-screen expander already makes,
    just for potentially every permit in the table at once). Without
    caching, that refetches for every permit on every unrelated rerun
    (typing, toggling language, expanding a section). _results_cache/_kb
    are underscore-prefixed so Streamlit doesn't try to hash them --
    permit_numbers + language is a sufficient cache key since results_cache
    is only ever additive within a session (see streamlit_app.py) and kb
    is loaded once at startup."""
    return build_report_html(list(permit_numbers), _results_cache, _kb)


def render_download_button(permit_numbers: list[str], results_cache: dict, kb: KnowledgeBase) -> None:
    """"Download Searched Permits" -- one combined, print-friendly HTML
    file covering every permit currently in the results table (not just
    checked/selected rows), so someone can save or print the full detail
    for the whole search rather than one permit at a time."""
    if not permit_numbers:
        return
    html_report = _cached_report_html(tuple(permit_numbers), get_language(), results_cache, kb)
    st.download_button(
        t("download_searched_permits_button"),
        data=html_report,
        file_name=f"permit-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html",
        mime="text/html",
    )
