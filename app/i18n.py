"""Minimal, dependency-free i18n layer for the Streamlit UI.

Scope: translates the app's own static chrome -- labels, buttons,
captions, headers, table columns, and the small fixed label dictionaries
formatting.py already defines for enum values (severity, category, match
status, etc.).

Deliberately out of scope: the permit facts pulled live from LA's open
data API (address, permit type, status description -- these are the
source record, not this app's own words) and the free-text analysis
prose Agent 3 generates (what_the_data_shows, what_this_usually_means,
developer/city-dependent steps, the disclaimer, knowledge-base caveats).
Those are generated content, not UI chrome, and machine-translating
agent-authored analytical text after the fact risks changing its
meaning -- translating that properly means generating it in Spanish at
the source, which is a separate, larger project from a UI toggle.

formatting.py stays Streamlit-free and English-only on purpose (its own
tests assert the English label dicts directly) -- this module layers
Spanish alternatives and language-aware accessor functions on top of it
rather than modifying it, so nothing there has to change.
"""

from __future__ import annotations

import re
from collections import Counter

import streamlit as st
import streamlit.components.v1 as components

import formatting
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome
from permit_stall_finder.schema.developer_explanation import GroundingStrength, VerificationStatus
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    IntervalState,
    Severity,
    StallCategory,
)

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "es": "Español"}

APP_NAME = "Permit Check LA"
"""The app's own name -- a proper noun, kept identical in both languages
(the same treatment the earlier gradient-bar title text got), not routed
through _STRINGS/t()."""


def get_language() -> str:
    return st.session_state.get("language", DEFAULT_LANGUAGE)


def set_language(lang: str) -> None:
    st.session_state["language"] = lang


def _sync_html_lang(lang: str) -> None:
    """Keeps the page's own <html lang> attribute in step with the
    selected UI language -- WCAG 3.1.1 Language of Page requires this so
    a screen reader applies the right pronunciation/voice rules to the
    (now-Spanish) text, rather than continuing to read it with English
    rules just because the <html> tag never changed. Streamlit doesn't
    expose an API for this, so it's done via a zero-size custom
    component: the injected script runs inside a same-origin iframe and
    reaches back out to window.parent.document, the actual top-level
    page Streamlit renders everything else into."""
    components.html(
        f"<script>try {{ window.parent.document.documentElement.lang = {lang!r}; }} "
        "catch (e) {{}}</script>",
        height=0,
        width=0,
    )


def render_language_toggle() -> None:
    """A two-state language switch (Phase 10 redesign -- replaces the
    earlier st.radio picker with a single st.toggle, since there are
    only ever two languages; streamlit_app.py centers this directly
    below the page title). Same rerun-and-reread-from-session_state
    pattern as before: every t()/label lookup below reads
    st.session_state["language"] fresh on the rerun a toggle flip
    triggers, so the whole page reflects the choice immediately."""
    current = get_language()
    _sync_html_lang(current)
    is_spanish = st.toggle(
        "EN  ·  ES",
        value=(current == "es"),
        key="language_picker",
    )
    new_lang = "es" if is_spanish else "en"
    if new_lang != current:
        set_language(new_lang)
        st.rerun()


# --- Spanish label dictionaries, mirroring formatting.py's enum -> label
# dicts one-for-one --------------------------------------------------------

CATEGORY_LABELS_ES: dict[StallCategory, str] = {
    StallCategory.PRE_ISSUANCE_STATUS_DWELL: "Tiempo en el estado actual previo a la emisión",
    StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP: "Brecha entre la emisión y la primera inspección",
    StallCategory.NO_INSPECTION_SINCE_ISSUANCE: "Sin inspección registrada desde la emisión",
    StallCategory.INTER_INSPECTION_GAP: "Brecha entre inspecciones",
    StallCategory.INACTIVITY_SINCE_LAST_INSPECTION: "Inactividad desde la última inspección",
    StallCategory.FINALIZATION_GAP: "Brecha antes de la finalización",
    StallCategory.REPEATED_CORRECTIONS: "Correcciones repetidas",
    StallCategory.REPEATED_NOT_READY_OUTCOMES: "Resultados repetidos de inspección 'no listo'",
    StallCategory.REPEATED_CANCELLATIONS: "Inspecciones canceladas repetidamente",
}

SEVERITY_LABELS_ES: dict[Severity, str] = {
    Severity.WATCH: "Vigilancia",
    Severity.ELEVATED: "Elevado",
    Severity.SEVERE: "Severo",
    Severity.UNSCORED: "Sin calificar",
}

MATCH_STATUS_LABELS_ES: dict[MatchStatus, str] = {
    MatchStatus.UNISSUED: "Aún no emitido",
    MatchStatus.ISSUED_WITH_INSPECTIONS: "Emitido, con inspecciones registradas",
    MatchStatus.ISSUED_NO_INSPECTIONS_FOUND: "Emitido, no se encontraron inspecciones",
    MatchStatus.PERMIT_NOT_FOUND: "Permiso no encontrado en el conjunto de datos de origen",
}

DATA_QUALITY_FLAG_LABELS_ES: dict[DataQualityFlag, str] = {
    DataQualityFlag.STATUS_ISSUE_DATE_INCONSISTENT: (
        "El propio registro de permiso de la ciudad tiene un estado y una fecha de emisión que "
        "no concuerdan del todo para este permiso -- es una discrepancia en los datos de origen, "
        "no algo introducido por esta herramienta."
    ),
    DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE: (
        "Para este tipo de permiso, los registros de inspección no siempre se vinculan de forma "
        "confiable con los registros de permisos en los datos de la ciudad -- así que si no "
        "aparece una inspección aquí, eso no significa necesariamente que no haya ocurrido."
    ),
    DataQualityFlag.FIRST_OBSERVATION: (
        "Esta es la primera vez que Permit Check LA consulta este número de permiso, así que no "
        "podemos contarle su historial de estancamientos antes de hoy. Esta herramienta funciona "
        "comparando varios conjuntos de datos del Departamento de Edificación y Seguridad de Los "
        "Ángeles cada vez que se busca un permiso -- todavía no hay una instantánea anterior con "
        "la cual comparar este."
    ),
}

BENCHMARK_SEMANTICS_LABELS_ES: dict[BenchmarkSemantics, str] = {
    BenchmarkSemantics.ACTIVE_PEER_DWELL: "Comparado con otros permisos atascados en este mismo paso ahora mismo",
    BenchmarkSemantics.COMPLETED_INTERVAL: "Comparado con cuánto suele tardar este paso una vez terminado",
}

INTERVAL_STATE_LABELS_ES: dict[IntervalState, str] = {
    IntervalState.ONGOING: "Todavía en curso",
    IntervalState.COMPLETED: "Este paso ya terminó",
}

OUTCOME_CLEAN_TEXT_ES = "No se identificaron señales materiales de estancamiento"
OUTCOME_INSUFFICIENT_TEXT_ES = "Evidencia insuficiente para evaluar este permiso de forma confiable"

GROUNDING_STRENGTH_LABELS_ES: dict[GroundingStrength, str] = {
    GroundingStrength.DIRECTLY_SUPPORTED: "respaldado directamente por la fuente",
    GroundingStrength.CAUTIOUS_SYNTHESIS: "sugerencia razonada",
    GroundingStrength.NOT_AVAILABLE: "no disponible",
}

VERIFICATION_STATUS_LABELS_ES: dict[VerificationStatus, str] = {
    VerificationStatus.DIRECT_PRIMARY_FETCH: "Verificado directamente contra la fuente primaria",
    VerificationStatus.SEARCH_SYNTHESIS_DETAILED: (
        "Obtenido mediante síntesis de búsqueda detallada, no una obtención directa completa"
    ),
    VerificationStatus.SEARCH_SYNTHESIS_GENERAL: (
        "Obtenido mediante síntesis de búsqueda general, no una obtención directa completa"
    ),
    VerificationStatus.UNVERIFIED: "No verificado",
}


def severity_label(severity: Severity) -> str:
    d = SEVERITY_LABELS_ES if get_language() == "es" else formatting.SEVERITY_LABELS
    return d[severity]


def category_label(category: StallCategory) -> str:
    d = CATEGORY_LABELS_ES if get_language() == "es" else formatting.CATEGORY_LABELS
    return d[category]


def match_status_label(status: MatchStatus) -> str:
    d = MATCH_STATUS_LABELS_ES if get_language() == "es" else formatting.MATCH_STATUS_LABELS
    return d.get(status, status.value)


def data_quality_flag_label(flag: DataQualityFlag) -> str:
    d = DATA_QUALITY_FLAG_LABELS_ES if get_language() == "es" else formatting.DATA_QUALITY_FLAG_LABELS
    return d.get(flag, flag.value)


def benchmark_semantics_label(b: BenchmarkSemantics) -> str:
    d = BENCHMARK_SEMANTICS_LABELS_ES if get_language() == "es" else formatting.BENCHMARK_SEMANTICS_LABELS
    return d[b]


def interval_state_label(i: IntervalState) -> str:
    d = INTERVAL_STATE_LABELS_ES if get_language() == "es" else formatting.INTERVAL_STATE_LABELS
    return d[i]


def grounding_strength_label(g: GroundingStrength) -> str:
    d = GROUNDING_STRENGTH_LABELS_ES if get_language() == "es" else formatting.GROUNDING_STRENGTH_LABELS
    return d[g]


def verification_status_label(v: VerificationStatus) -> str:
    d = VERIFICATION_STATUS_LABELS_ES if get_language() == "es" else formatting.VERIFICATION_STATUS_LABELS
    return d[v]


_CONFIDENCE_NOTES: dict[str, dict[CohortConfidence, str]] = {
    "en": {
        CohortConfidence.FULL: "",
        CohortConfidence.REDUCED: " -- a smaller comparison group",
        CohortConfidence.INSUFFICIENT: " -- too few similar permits to compare confidently",
        CohortConfidence.ZERO_VARIANCE: " -- a comparison group where this rarely varies",
    },
    "es": {
        CohortConfidence.FULL: "",
        CohortConfidence.REDUCED: " -- un grupo de comparación más pequeño",
        CohortConfidence.INSUFFICIENT: " -- muy pocos permisos similares para comparar con confianza",
        CohortConfidence.ZERO_VARIANCE: " -- un grupo de comparación donde esto casi no varía",
    },
}


def cohort_basis_caption(n: int, confidence: CohortConfidence) -> str:
    """Plain-language replacement for the old '(n=50, full)' caption --
    states the comparison group size in words, and only adds a qualifier
    when the comparison is weaker than the normal case (full confidence
    stays a bare count, nothing extra to hedge)."""
    note = _CONFIDENCE_NOTES.get(get_language(), _CONFIDENCE_NOTES["en"]).get(confidence, "")
    return t("based_on_n_similar").format(n=n) + note


def unusualness_phrase(percentile_rank: float) -> str:
    """'Slower than 97 out of 100 similar permits' instead of a bare
    percentile number -- same underlying value, just spelled out."""
    return t("slower_than_out_of_100").format(rank=round(percentile_rank))


def top_finding_bullet(detection) -> str:
    """One line for the quick-glance "Top Findings" bullet list, e.g.
    "SEVERE Gap between inspections". Severity + category only -- the
    elapsed_days/observed_count/percentile_rank numbers deliberately
    stay out of this line (Phase 13): they already appear in the
    matching finding card's own metric row and "what the data shows"
    prose in the right panel, and repeating them a third time here was
    flagged as redundant. This is meant as a fast-scan index into those
    cards, not a restatement of their numbers."""
    severity_text = severity_label(detection.severity).upper()
    category_text = category_label(detection.category)
    return f"{severity_text} {category_text}"


def extra_time_metric_label(benchmark_semantics: BenchmarkSemantics) -> str:
    if benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
        return t("extra_time_metric_active")
    return t("extra_time_metric")


def days_vs_typical_phrase(excess_days: float, benchmark_semantics: BenchmarkSemantics) -> str:
    """'{n} days longer/shorter than typical' instead of a signed
    '+79 days vs. median' -- same number, phrased as a comparison rather
    than a signed statistic.

    COMPLETED_INTERVAL is an unbiased sample of concluded intervals, so
    calling its median "typical" is a fair description. ACTIVE_PEER_DWELL
    is a length-biased sample of permits still in progress -- the same
    reason schema/stall_detection.py's render_dwell_statement() never
    lets that cohort type produce "permits normally take N days"
    language (see its own docstring and test_dwell_language.py's
    test_active_peer_dwell_never_produces_normally_take_language). This
    mirrors that rule here: for ACTIVE_PEER_DWELL the comparison is
    phrased against "other active permits," never "typical."
    """
    rounded = round(excess_days)
    if benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
        if rounded >= 0:
            return t("days_longer_than_others_active").format(days=rounded)
        return t("days_shorter_than_others_active").format(days=abs(rounded))
    if rounded >= 0:
        return t("days_longer_than_typical").format(days=rounded)
    return t("days_shorter_than_typical").format(days=abs(rounded))


def extra_count_metric_label(benchmark_semantics: BenchmarkSemantics) -> str:
    if benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
        return t("extra_count_metric_active")
    return t("extra_count_metric")


def count_vs_typical_phrase(excess_count: float, benchmark_semantics: BenchmarkSemantics) -> str:
    """Same idea as days_vs_typical_phrase() for count-based (friction)
    detections, e.g. repeated corrections -- see that function's
    docstring for why benchmark_semantics gates the wording."""
    rounded = round(excess_count, 1)
    if benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
        if rounded >= 0:
            return t("more_than_others_active").format(n=rounded)
        return t("fewer_than_others_active").format(n=abs(rounded))
    if rounded >= 0:
        return t("more_than_typical").format(n=rounded)
    return t("fewer_than_typical").format(n=abs(rounded))


_SEVERITY_ORDER = [Severity.SEVERE, Severity.ELEVATED, Severity.WATCH]


def summarize_severity_counts(detections) -> str:
    if get_language() != "es":
        return formatting.summarize_severity_counts(detections)
    counts = Counter(d.severity for d in detections)
    parts = []
    for sev in _SEVERITY_ORDER:
        n = counts.get(sev, 0)
        if n:
            label = severity_label(sev).lower()
            noun = t("finding_singular") if n == 1 else t("finding_plural")
            parts.append(f"{n} {label} {noun}")
    return " · ".join(parts) if parts else OUTCOME_CLEAN_TEXT_ES


def summarize_severity_counts_compact(detections) -> str:
    """Bilingual wrapper for formatting.summarize_severity_counts_compact(),
    same "get_language() != 'es' -> delegate" pattern as
    summarize_severity_counts() above."""
    if get_language() != "es":
        return formatting.summarize_severity_counts_compact(detections)
    counts = Counter(d.severity for d in detections)
    parts = []
    for sev in _SEVERITY_ORDER:
        n = counts.get(sev, 0)
        if n:
            parts.append(f"{n} {severity_label(sev).lower()}")
    return ", ".join(parts) if parts else OUTCOME_CLEAN_TEXT_ES


def outcome_headline(result) -> str:
    if get_language() != "es":
        return formatting.outcome_headline(result)
    if result.outcome == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED:
        return OUTCOME_CLEAN_TEXT_ES
    if result.outcome == AnalysisOutcome.INSUFFICIENT_EVIDENCE:
        return OUTCOME_INSUFFICIENT_TEXT_ES
    return summarize_severity_counts(result.stall_assessment.detections)


# --- Plain-language status descriptions -----------------------------------
# status_desc is a raw field straight from LADBS's own open-data record
# (research/DATASET_VALIDATION.md catalogs the full observed vocabulary --
# both the pre-issuance "Submitted" family and the post-issuance "Final"
# family). Several of LADBS's own values use internal abbreviations
# ("PC" = Plan Check, "CofO" = Certificate of Occupancy) that make sense
# to LADBS staff but not to a homeowner or developer reading this page.
# This is a display-only relabeling -- the underlying status_desc string
# is never altered or reinterpreted, just spelled out in plain words.
# Anything LADBS returns that isn't in this dict (a long tail of rare
# values exists) falls back to showing the raw string unchanged, rather
# than hiding or guessing at unfamiliar statuses.

_STATUS_DESC_LABELS: dict[str, dict[str, str]] = {
    "Submitted": {"en": "Submitted, not yet under review", "es": "Presentado, aún no revisado"},
    "Plans on Hold": {"en": "Plans on hold", "es": "Planos en espera"},
    "Re-Submittal Required": {"en": "Resubmission required", "es": "Se requiere volver a presentar"},
    "Quality Review Completed": {"en": "Initial quality review completed", "es": "Revisión de calidad inicial completada"},
    "Verifications in Progress": {"en": "Verifications in progress", "es": "Verificaciones en curso"},
    "PC Assigned": {"en": "Assigned for plan review", "es": "Asignado para revisión de planos"},
    "PC in Progress": {"en": "Plan review in progress", "es": "Revisión de planos en curso"},
    "PC Info Complete": {"en": "Plan review information complete", "es": "Información de revisión de planos completa"},
    "Corrections Issued": {"en": "Corrections requested", "es": "Correcciones solicitadas"},
    "Not Ready to Issue": {"en": "Not yet ready to issue", "es": "Aún no listo para emitir"},
    "Reviewed by Supervisor": {"en": "Reviewed by a supervisor", "es": "Revisado por un supervisor"},
    "Submitted for Qual. Rev.": {"en": "Submitted for quality review", "es": "Presentado para revisión de calidad"},
    "No Progress": {"en": "No progress recorded", "es": "Sin progreso registrado"},
    "PC Approved": {"en": "Plan review approved, not yet issued", "es": "Revisión de planos aprobada, aún no emitido"},
    "Ready to Issue": {"en": "Approved and ready to be issued", "es": "Aprobado y listo para ser emitido"},
    "Issued": {"en": "Permit issued", "es": "Permiso emitido"},
    "CofO Issued": {"en": "Certificate of Occupancy issued", "es": "Certificado de ocupación emitido"},
    "CofO in Progress": {"en": "Certificate of Occupancy in progress", "es": "Certificado de ocupación en trámite"},
    "CofO Corrected": {"en": "Certificate of Occupancy corrected", "es": "Certificado de ocupación corregido"},
    "CofO Reactivated": {"en": "Certificate of Occupancy reactivated", "es": "Certificado de ocupación reactivado"},
    "CofC Issued": {"en": "Certificate of Compliance issued", "es": "Certificado de cumplimiento emitido"},
    "Permit Finaled": {"en": "Permit finaled -- all inspections complete", "es": "Permiso finalizado -- todas las inspecciones completas"},
    "Permit Closed": {"en": "Permit closed", "es": "Permiso cerrado"},
    "Permit Expired": {"en": "Permit expired", "es": "Permiso vencido"},
    "Refund Completed": {"en": "Refund completed", "es": "Reembolso completado"},
    "Permit Withdrawn": {"en": "Permit withdrawn", "es": "Permiso retirado"},
    "Re-Activate Permit": {"en": "Permit reactivated", "es": "Permiso reactivado"},
}


_FRICTION_CATEGORY_PHRASES: dict[str, dict[str, str]] = {
    "repeated_corrections": {"en": "corrections were requested", "es": "se solicitaron correcciones"},
    "repeated_not_ready_outcomes": {
        "en": "inspections came back \u2018not ready\u2019",
        "es": "las inspecciones resultaron \u2018no listo\u2019",
    },
    "repeated_cancellations": {"en": "inspections were cancelled", "es": "se cancelaron inspecciones"},
}


def plain_coverage_gap(raw_gap: str) -> str:
    """Plain-language rendering of a coverage_gaps entry.

    These strings come straight from Agent 2 (stall_detector.py) and are
    explicitly passed through unchanged everywhere else in the pipeline
    (see developer_explanation.py's own comment to that effect) -- this
    function never touches the underlying coverage_gaps list, only how
    one entry is displayed. It recognizes the small, fixed set of message
    shapes Agent 2 actually produces (confirmed by reading
    stall_detector.py directly) and rewords each into a plain sentence;
    anything that doesn't match one of those shapes -- a future message
    shape this function doesn't know about yet -- falls back to showing
    the raw string unchanged, the same safety-net pattern
    plain_status_desc() uses for unrecognized statuses."""
    lang = get_language()

    if raw_gap == "Permit not found by Agent 1 -- no stall assessment possible.":
        return (
            "We couldn't find this permit in the city's records, so no analysis could be run."
            if lang != "es"
            else "No pudimos encontrar este permiso en los registros de la ciudad, así que no se pudo hacer ningún análisis."
        )

    if raw_gap == (
        "FINALIZATION_GAP not assessed for finaled_only_track: confirmed degenerate "
        "(effectively same-day finalization is normal LADBS behavior for this track, "
        "not a stall) -- see AGENT2_DESIGN.md \u00a77."
    ):
        return (
            "We didn't score how long it took this permit to close out, because for this type of "
            "permit, closing out the same day as the last inspection is normal LADBS practice -- not "
            "a sign of delay."
            if lang != "es"
            else "No evaluamos cuánto tardó este permiso en cerrarse, porque para este tipo de permiso "
            "es una práctica normal de LADBS cerrarse el mismo día de la última inspección -- no es "
            "señal de retraso."
        )

    m = re.match(r"FINALIZATION_GAP not assessed: permit exited via '(?P<status>[^']+)', which is not", raw_gap)
    if m:
        status = plain_status_desc(m.group("status"))
        return (
            f"We didn't score how long closing out took, because this permit didn't finalize the "
            f"usual way -- it exited as \u201c{status}\u201d instead."
            if lang != "es"
            else f"No evaluamos cuánto tardó el cierre, porque este permiso no se finalizó de la manera "
            f"habitual -- salió como \u201c{status}\u201d en su lugar."
        )

    m = re.match(
        r"(?P<category>[a-z_]+) not assessed: insufficient inspection exposure "
        r"\((?P<n>\d+) substantive inspection\(s\) observed so far, minimum (?P<min>\d+)\)\.",
        raw_gap,
    )
    if m:
        category_phrase = _FRICTION_CATEGORY_PHRASES.get(m.group("category"), {}).get(lang)
        n, minimum = m.group("n"), m.group("min")
        if category_phrase:
            return (
                f"We haven't checked whether {category_phrase} an unusual number of times yet -- only "
                f"{n} inspection(s) have happened so far, and we wait for at least {minimum} before "
                f"judging that."
                if lang != "es"
                else f"Aún no hemos revisado si {category_phrase} un número inusual de veces -- solo se "
                f"han realizado {n} inspección(es) hasta ahora, y esperamos al menos {minimum} antes de "
                f"evaluar eso."
            )

    m = re.match(r"NO_INSPECTION_SINCE_ISSUANCE not assessed for [^:]+: (?P<rest>.+)", raw_gap)
    if m:
        prefix = (
            "We didn't flag the lack of an inspection as unusual for this permit"
            if lang != "es"
            else "No marcamos la falta de una inspección como inusual para este permiso"
        )
        return f"{prefix} -- {m.group('rest')}"

    return raw_gap


def plain_status_desc(raw_status: str | None) -> str:
    """LADBS's own status_desc, in plain words instead of internal
    abbreviations -- falls back to the raw value unchanged for anything
    not in the table above (an unfamiliar status is still better shown
    than hidden)."""
    if not raw_status:
        return raw_status or "—"
    entry = _STATUS_DESC_LABELS.get(raw_status)
    if entry is None:
        return raw_status
    return entry.get(get_language(), entry.get("en", raw_status))


# --- Static UI chrome ----------------------------------------------------

_STRINGS: dict[str, dict[str, str]] = {
    "page_intro": {
        "en": (
            "Check whether your permit is moving at a normal pace or getting stuck -- and "
            "why. We compare your permit to hundreds of similar ones, and when something's "
            "taking longer, we'll tell you how unusual the delay is, why it might be "
            "happening, and what you or the city can do next."
        ),
        "es": (
            "Vea si su permiso avanza a un ritmo normal o si se ha estancado -- y por qué. "
            "Comparamos su permiso con cientos de permisos similares, y cuando algo está "
            "tardando más de lo normal, le decimos qué tan inusual es el retraso, por qué "
            "podría estar pasando, y qué puede hacer usted o la ciudad al respecto."
        ),
    },
    "clear_results": {"en": "Clear results", "es": "Borrar resultados"},
    "tab_permit_number": {"en": "Search by permit number", "es": "Buscar por número de permiso"},
    "tab_address": {"en": "Search by address", "es": "Buscar por dirección"},
    "permit_numbers_label": {"en": "Permit number(s)", "es": "Número(s) de permiso"},
    "analyze_button": {"en": "Analyze", "es": "Analizar"},
    "searching_button": {"en": "Searching...", "es": "Buscando..."},
    "search_loading_caption": {
        "en": "We promise this won't take as long as your permit approval!",
        "es": "¡Prometemos que esto no tardará tanto como la aprobación de su permiso!",
    },
    "permit_number_help": {
        "en": (
            "LADBS permit numbers look like 21030-20000-00256 (year - plan check number - "
            "permit number). Find yours on your permit paperwork, an inspection notice, or "
            "by searching your address under the \u201cSearch by address\u201d tab."
        ),
        "es": (
            "Los números de permiso de LADBS tienen este formato: 21030-20000-00256 (año - "
            "número de revisión de planos - número de permiso). Lo encuentra en el papeleo de "
            "su permiso, en un aviso de inspección, o buscando su dirección en la pestaña "
            "\u201cBuscar por dirección\u201d."
        ),
    },
    "warning_enter_permit_number": {
        "en": "Enter at least one permit number.",
        "es": "Ingrese al menos un número de permiso.",
    },
    "spinner_analyzing": {"en": "Analysing permit...", "es": "Analizando permiso..."},
    "warning_some_unanalyzed": {
        "en": "permit(s) couldn't be analyzed right now (the city's open data service may be "
        "temporarily unavailable) and are omitted below:",
        "es": "permiso(s) no se pudieron analizar en este momento (el servicio de datos "
        "abiertos de la ciudad podría no estar disponible temporalmente) y se omiten abajo:",
    },
    "show_full_analysis": {
        "en": "Show full analysis (permit journey, finding-by-finding explanations, coverage notes)",
        "es": "Mostrar análisis completo (trayecto del permiso, explicaciones de cada hallazgo, "
        "notas de cobertura)",
    },
    "finding_singular": {"en": "finding", "es": "hallazgo"},
    "finding_plural": {"en": "findings", "es": "hallazgos"},
    # plain-language stall-metric copy (stall_findings.py _render_metrics)
    "how_unusual_metric": {"en": "How unusual", "es": "Qué tan inusual"},
    "slower_than_out_of_100": {
        "en": "Slower than {rank} of 100 similar permits",
        "es": "Más lento que {rank} de cada 100 permisos similares",
    },
    "extra_time_metric": {"en": "Extra time vs. typical", "es": "Tiempo extra vs. lo típico"},
    "days_longer_than_typical": {"en": "{days} days longer than typical", "es": "{days} días más que lo típico"},
    "days_shorter_than_typical": {"en": "{days} days shorter than typical", "es": "{days} días menos que lo típico"},
    "extra_count_metric": {"en": "Extra vs. typical", "es": "Extra vs. lo típico"},
    "more_than_typical": {"en": "{n} more than typical", "es": "{n} más que lo típico"},
    "fewer_than_typical": {"en": "{n} fewer than typical", "es": "{n} menos que lo típico"},
    # ACTIVE_PEER_DWELL-safe variants of the four keys above -- this cohort is a
    # length-biased sample of permits still in progress, so it must never be
    # described as "typical" (see days_vs_typical_phrase()'s docstring).
    "extra_time_metric_active": {
        "en": "Extra time vs. other active permits",
        "es": "Tiempo extra vs. otros permisos activos",
    },
    "days_longer_than_others_active": {
        "en": "{days} days more than other permits at this step",
        "es": "{days} días más que otros permisos en este paso",
    },
    "days_shorter_than_others_active": {
        "en": "{days} days less than other permits at this step",
        "es": "{days} días menos que otros permisos en este paso",
    },
    "extra_count_metric_active": {
        "en": "Extra vs. other active permits",
        "es": "Extra vs. otros permisos activos",
    },
    "more_than_others_active": {
        "en": "{n} more than other permits at this step",
        "es": "{n} más que otros permisos en este paso",
    },
    "fewer_than_others_active": {
        "en": "{n} fewer than other permits at this step",
        "es": "{n} menos que otros permisos en este paso",
    },
    "based_on_n_similar": {"en": "Based on {n} similar permits", "es": "Basado en {n} permisos similares"},
    "info_no_permits_found": {
        "en": "No permits found for that address. Try a shorter or differently formatted address.",
        "es": "No se encontraron permisos para esa dirección. Intente con una dirección más "
        "corta o con otro formato.",
    },
    "info_address_fallback_used": {
        "en": "No permits found at that exact address — showing other permits on the same street instead.",
        "es": "No se encontraron permisos en esa dirección exacta — mostrando otros permisos en la misma calle.",
    },
    # quick_glance.py
    "qg_address": {"en": "Address", "es": "Dirección"},
    "qg_type": {"en": "Type", "es": "Tipo"},
    "qg_status": {"en": "Status", "es": "Estado"},
    "qg_issuance_status": {"en": "Issuance status", "es": "Estado de emisión"},
    "qg_last_update": {"en": "Last status update", "es": "Última actualización de estado"},
    "qg_permit_status_header": {"en": "Permit status", "es": "Estado del permiso"},
    "qg_status_last_reported_template": {
        "en": "This permit's status was last reported as changed {rel}.",
        "es": "El estado de este permiso se informó por última vez como cambiado {rel}.",
    },
    "ymd_ago_template": {"en": "{ymd} ago", "es": "hace {ymd}"},
    "ymd_year_abbr": {"en": "y", "es": "a"},
    "ymd_month_abbr": {"en": "m", "es": "m"},
    "ymd_day_abbr": {"en": "d", "es": "d"},
    "qg_top_findings": {"en": "Total Number of Findings", "es": "Número total de hallazgos"},
    "qg_result": {"en": "Result", "es": "Resultado"},
    "resources_header": {"en": "Resources", "es": "Recursos"},
    # location_map.py
    "city_label": {"en": "City of Los Angeles", "es": "Ciudad de Los Ángeles"},
    "county_label": {"en": "Los Angeles County", "es": "Condado de Los Ángeles"},
    "map_unavailable": {
        "en": "Map unavailable -- this permit's source record has no coordinates.",
        "es": "Mapa no disponible -- el registro de origen de este permiso no tiene coordenadas.",
    },
    "open_in_google_maps": {"en": "Open in Google Maps", "es": "Abrir en Google Maps"},
    "zip_prefix": {"en": "ZIP", "es": "Código postal"},
    # report_export.py -- coverage/data-quality notes are downloadable-report-only now
    # (removed from the on-screen drill-down per explicit request; see drill_down.py)
    "coverage_notes_header": {
        "en": "What we couldn't check",
        "es": "Lo que no pudimos revisar",
    },
    "coverage_notes_warning": {
        "en": "Permit Check LA works by comparing two City of Los Angeles Department of Building "
        "and Safety datasets -- permits and inspections -- to reconstruct a permit's timeline. "
        "The specific items below are ones we couldn't fully check for this permit. That doesn't "
        "mean there is or isn't a delay -- it just means we can't say, for those specific items.",
        "es": "Permit Check LA funciona comparando dos conjuntos de datos del Departamento de "
        "Edificación y Seguridad de Los Ángeles -- permisos e inspecciones -- para reconstruir el "
        "cronograma de un permiso. Los puntos específicos a continuación son los que no pudimos "
        "revisar por completo para este permiso. Eso no significa que haya o no haya un retraso -- "
        "solo significa que no podemos saberlo para esos puntos en particular.",
    },
    "coverage_gaps_label": {"en": "Checks we skipped", "es": "Revisiones que omitimos"},
    "data_quality_notes_label": {"en": "About the data", "es": "Sobre los datos"},
    # permit_journey.py
    "no_journey_record": {
        "en": "No permit record was found to reconstruct a journey from.",
        "es": "No se encontró ningún registro de permiso a partir del cual reconstruir un trayecto.",
    },
    "observed_inspections": {"en": "Observed inspection events", "es": "Inspecciones observadas"},
    "col_date": {"en": "Date", "es": "Fecha"},
    "col_type": {"en": "Type", "es": "Tipo"},
    "col_result": {"en": "Result", "es": "Resultado"},
    "derived_metrics": {"en": "Derived elapsed-time metrics", "es": "Métricas de tiempo transcurrido"},
    "submitted_to_issued": {"en": "Submitted → issued", "es": "Presentado → emitido"},
    "issued_to_first_inspection": {
        "en": "Issued → first inspection",
        "es": "Emitido → primera inspección",
    },
    "total_observed_span": {"en": "Total observed span", "es": "Duración total observada"},
    "days_suffix": {"en": "days", "es": "días"},
    "not_observed": {"en": "Not observed", "es": "No observado"},
    "technical_details": {"en": "Technical details", "es": "Detalles técnicos"},
    "reconstruction_notes": {"en": "Reconstruction notes:", "es": "Notas de reconstrucción:"},
    # stall_findings.py
    "stall_findings_header": {"en": "Where this project has stalled", "es": "Dónde se ha estancado este proyecto"},
    "card_label_ongoing": {"en": "Ongoing", "es": "En curso"},
    "card_label_completed": {"en": "Completed", "es": "Completado"},
    "stage_context_between": {"en": "Between {stage}", "es": "Entre {stage}"},
    "stage_context_most_recent": {
        "en": "Most recent inspection: {stage}",
        "es": "Inspección más reciente: {stage}",
    },
    "elapsed_days_metric": {"en": "Elapsed days", "es": "Días transcurridos"},
    "percentile_rank_metric": {"en": "Percentile rank", "es": "Percentil"},
    "excess_vs_median_metric": {"en": "Excess vs. median", "es": "Exceso vs. mediana"},
    "observed_count_metric": {"en": "Observed count", "es": "Cantidad observada"},
    "what_data_shows": {"en": "What the data shows", "es": "Lo que muestran los datos"},
    "what_this_usually_means": {"en": "What this usually means", "es": "Qué suele significar esto"},
    "no_entry_heading": {
        "en": "No authoritative guidance available",
        "es": "No hay orientación autorizada disponible",
    },
    "steps_you_can_take": {"en": "Steps you can take", "es": "Pasos que puede tomar"},
    "steps_depend_on_city": {
        "en": "Steps that depend on the city",
        "es": "Pasos que dependen de la ciudad",
    },
    "no_developer_steps": {
        "en": "No developer-actionable guidance is available for this specific pattern.",
        "es": "No hay orientación disponible para el desarrollador sobre este patrón específico.",
    },
    "no_city_steps": {
        "en": "No city-dependent guidance is available for this specific pattern.",
        "es": "No hay orientación dependiente de la ciudad disponible para este patrón específico.",
    },
    "cannot_tell": {
        "en": "What we cannot tell from this data",
        "es": "Lo que no podemos determinar con estos datos",
    },
    "findings_cause_disclaimer": {
        "en": (
            "Permit Check LA reports elapsed time and inspection counts, not cause. "
            "It cannot determine which party (applicant, contractor, or LADBS) is "
            "responsible for delays, why a permit hasn't progressed further, or "
            "whether a gap reflects slow construction versus a delay in requesting "
            "the next inspection."
        ),
        "es": (
            "Permit Check LA informa el tiempo transcurrido y el número de "
            "inspecciones, no la causa. No puede determinar qué parte (solicitante, "
            "contratista o LADBS) es responsable de los retrasos, por qué un permiso "
            "no ha avanzado más, o si un intervalo refleja una construcción lenta "
            "frente a una demora en solicitar la siguiente inspección."
        ),
    },
    "caveats": {"en": "Caveats", "es": "Advertencias"},
    "source_and_grounding": {"en": "Source & grounding", "es": "Fuente y fundamento"},
    "no_kb_entry": {
        "en": "No knowledge-base entry is associated with this explanation.",
        "es": "No hay ninguna entrada de la base de conocimiento asociada con esta explicación.",
    },
    "caveats_on_guidance": {"en": "Caveats on this guidance", "es": "Advertencias sobre esta orientación"},
    # next_best_action.py
    "next_best_action": {"en": "Next best action", "es": "Próxima mejor acción"},
    "confirm_status_link": {
        "en": "Confirm this permit's current status directly on LADBS",
        "es": "Confirme el estado actual de este permiso directamente en LADBS",
    },
    "authoritative_source_note": {
        "en": "the authoritative source; this tool is informational only.",
        "es": "la fuente autorizada; esta herramienta es solo informativa.",
    },
    "search_records_link": {
        "en": "Search LADBS's online building records for this address",
        "es": "Busque los registros de construcción en línea de LADBS para esta dirección",
    },
    "talk_to_a_person": {"en": "Talk to a person", "es": "Hable con una persona"},
    "call_prefix": {"en": "Call", "es": "Llame al"},
    "or": {"en": "or", "es": "o"},
    "call_line_text": {
        "en": "to reach LADBS customer service -- they take inspection requests, answer "
        "general questions, and can route zoning or code questions to an engineer or "
        "inspector.",
        "es": "para comunicarse con servicio al cliente de LADBS -- reciben solicitudes de "
        "inspección, responden preguntas generales y pueden derivar preguntas de zonificación "
        "o código a un ingeniero o inspector.",
    },
    "deeper_attention_prefix": {
        "en": "For a case that needs deeper attention:",
        "es": "Para un caso que necesite atención más profunda:",
    },
    "learn_more_this_finding": {
        "en": "Learn more about this finding",
        "es": "Más información sobre este hallazgo",
    },
    "yes": {"en": "Yes", "es": "Sí"},

    # --- Phase 10 redesign: header, unified search, results table, drill-down ---
    "site_welcome_intro": {
        "en": "See where your Los Angeles City building permit's stuck, why, and what usually gets it moving.",
        "es": "Vea dónde se ha detenido su permiso de construcción de la Ciudad de Los Ángeles, por qué, y qué suele ponerlo en marcha de nuevo.",
    },
    "header_home_aria_label": {"en": "Home", "es": "Inicio"},
    "header_ladbs_link": {
        "en": "Official LADBS Building Permit Resources",
        "es": "Recursos oficiales de permisos de construcción de LADBS",
    },
    # persona_picker.py
    "impact_stat_text": {
        "en": "{n} search{plural} run on Permit Check LA so far",
        "es": "{n} búsqueda{plural} realizada{plural} en Permit Check LA hasta ahora",
    },
    "persona_picker_heading": {
        "en": "Let us know your role, so you can get the most out of this experience.",
        "es": "Cuéntenos su rol, para que pueda aprovechar al máximo esta experiencia.",
    },
    "persona_contractor": {"en": "Contractor", "es": "Contratista"},
    "persona_developer": {"en": "Developer", "es": "Desarrollador"},
    "persona_government_employee": {"en": "Government Employee", "es": "Empleado de gobierno"},
    "persona_individual": {"en": "Individual", "es": "Particular"},
    "unified_search_placeholder": {
        "en": "Search permits by permit number or address",
        "es": "Busque permisos por número de permiso o dirección",
    },
    "unified_search_help": {
        "en": (
            "Permit number: LADBS permit numbers look like 21030-20000-00256 (year - plan "
            "check number - permit number). Enter more than one, separated by commas or new "
            "lines, to check several at once.\n\n"
            "Address: enter the property's street address as it's filed with LADBS, e.g. "
            "200 N Spring St. No need to include city, state, or ZIP code."
        ),
        "es": (
            "Número de permiso: los números de permiso de LADBS tienen este formato: "
            "21030-20000-00256 (año - número de revisión de planos - número de permiso). "
            "Ingrese más de uno, separados por comas o saltos de línea, para revisar varios "
            "a la vez.\n\n"
            "Dirección: ingrese la dirección de la propiedad tal como está registrada en "
            "LADBS, por ejemplo 200 N Spring St. No es necesario incluir ciudad, estado ni "
            "código postal."
        ),
    },
    "search_button": {"en": "Search", "es": "Buscar"},
    "results_table_header": {
        "en": "Permit Search Results",
        "es": "Resultados de la búsqueda de permisos",
    },
    "results_table_caption_suffix": {"en": "permit(s) found", "es": "permiso(s) encontrado(s)"},
    "results_table_hint": {
        "en": "Click a row to see its full detail below.",
        "es": "Haga clic en una fila para ver su detalle completo abajo.",
    },
    "download_searched_permits_button": {
        "en": "⬇ Download Searched Permits",
        "es": "⬇ Descargar permisos buscados",
    },
    "col_permit_number": {"en": "Permit number", "es": "Número de permiso"},
    "col_permit_number_help": {
        "en": "The LADBS permit number: year, plan check number, and permit number.",
        "es": "El número de permiso de LADBS: año, número de revisión de planos y número de permiso.",
    },
    "col_findings": {"en": "Findings", "es": "Hallazgos"},
    "col_findings_help": {
        "en": "How many stall findings this tool detected for this permit, grouped by severity.",
        "es": "Cuántos hallazgos de estancamiento detectó esta herramienta para este permiso, agrupados por gravedad.",
    },
    "col_submitted_date": {"en": "Permit submission", "es": "Presentación del permiso"},
    "col_submitted_date_help": {
        "en": "The date this permit application was submitted to LADBS.",
        "es": "La fecha en que se presentó esta solicitud de permiso a LADBS.",
    },
    "col_permit_type": {"en": "Permit type", "es": "Tipo de permiso"},
    "col_permit_type_help": {
        "en": "The category of work this permit covers, as classified by LADBS.",
        "es": "La categoría de trabajo que cubre este permiso, según la clasificación de LADBS.",
    },
    "col_issuance_status": {"en": "Issuance status", "es": "Estado de emisión"},
    "col_issuance_status_help": {
        "en": "Whether LADBS has issued this permit yet.",
        "es": "Si LADBS ya ha emitido este permiso.",
    },
    "col_permit_status": {"en": "Permit status", "es": "Estado del permiso"},
    "col_permit_status_help": {
        "en": (
            "This permit's current status, as reported by LADBS. Common values:\n"
            "Submitted: application received, not yet under review\n"
            "PC in Progress: plan review in progress, not yet issued\n"
            "Corrections Issued: corrections requested before the next step\n"
            "Ready to Issue: approved, awaiting issuance\n"
            "Issued: the permit has been issued\n"
            "CofO Issued: Certificate of Occupancy issued\n"
            "Permit Finaled: all inspections complete"
        ),
        "es": (
            "El estado actual de este permiso, según lo informado por LADBS. Valores comunes:\n"
            "Submitted: solicitud recibida, aún no revisada\n"
            "PC in Progress: revisión de planos en curso, aún no emitido\n"
            "Corrections Issued: se solicitaron correcciones antes del siguiente paso\n"
            "Ready to Issue: aprobado, en espera de emisión\n"
            "Issued: el permiso ha sido emitido\n"
            "CofO Issued: Certificado de Ocupación emitido\n"
            "Permit Finaled: todas las inspecciones completas"
        ),
    },
    "col_last_update": {"en": "Last status update", "es": "Última actualización de estado"},
    "col_last_update_help": {
        "en": "How long ago this permit's status was last reported as changed.",
        "es": "Cuánto tiempo hace que se reportó por última vez un cambio en el estado de este permiso.",
    },
    "issued_status_text": {"en": "Permit has been issued", "es": "El permiso ha sido emitido"},
    "not_issued_status_text": {"en": "Permit has not been issued", "es": "El permiso no ha sido emitido"},
    "today_label": {"en": "today", "es": "hoy"},
    "drill_down_header": {"en": "Permit Details", "es": "Detalles del permiso"},
    "drill_down_permit_journey": {"en": "Permit Journey", "es": "Trayectoria del permiso"},
    "drill_down_other_permits": {
        "en": "Other permits at this address",
        "es": "Otros permisos en esta dirección",
    },
    "drill_down_data_limitations": {"en": "Data Limitations", "es": "Limitaciones de los datos"},
    "no_other_permits_found": {
        "en": "No other permits were found at this address.",
        "es": "No se encontraron otros permisos en esta dirección.",
    },
    "open_permit_tab_button": {"en": "Open", "es": "Abrir"},
    "stall_findings_banner_subtext": {
        "en": (
            "These are patterns our analysis found by comparing this permit to hundreds of "
            "similar ones using City of Los Angeles Department of Building and Safety's "
            "publicly accessible data."
        ),
        "es": (
            "Estos son patrones que nuestro análisis encontró al comparar este permiso con "
            "cientos de permisos similares, utilizando los datos de acceso público del "
            "Departamento de Edificación y Seguridad de la Ciudad de Los Ángeles."
        ),
    },

    # --- Nav switcher: Home / Search / My Permits / Trends Dashboard / FAQ -
    "nav_home": {"en": "Home", "es": "Inicio"},
    "nav_search": {"en": "Search", "es": "Buscar"},
    "nav_my_permits": {"en": "My Permits", "es": "Mis permisos"},
    "nav_trends": {"en": "Trends Dashboard", "es": "Panel de tendencias"},
    "nav_faq": {"en": "FAQ", "es": "Preguntas frecuentes"},

    # --- Trends dashboard --------------------------------------------------
    "trends_dashboard_header": {"en": "Trends Dashboard", "es": "Panel de tendencias"},
    "trends_disclaimer_text": {
        "en": (
            "These figures describe how permits like this have historically moved through "
            "the process, based on a sample of past permits -- they are not a prediction "
            "of how long any specific permit will take, and this tool is informational only, "
            "not an official LADBS determination."
        ),
        "es": (
            "Estas cifras describen cómo se han movido históricamente permisos similares a "
            "este dentro del proceso, según una muestra de permisos anteriores -- no son una "
            "predicción de cuánto tardará un permiso específico, y esta herramienta es solo "
            "informativa, no una determinación oficial de LADBS."
        ),
    },
    "trends_generated_caption": {
        "en": "Based on a sample of up to {n} permits per year/type, generated {generated}.",
        "es": "Basado en una muestra de hasta {n} permisos por año/tipo, generado el {generated}.",
    },
    "trends_no_artifact": {
        "en": (
            "No trends data has been generated yet. Run "
            "scripts/generate_trends_artifact.py to build it."
        ),
        "es": (
            "Aún no se han generado datos de tendencias. Ejecute "
            "scripts/generate_trends_artifact.py para generarlos."
        ),
    },
    "trends_no_data_for_selection": {
        "en": "No data for this selection.", "es": "No hay datos para esta selección.",
    },
    "trends_year_over_year_header": {
        "en": "Typical duration, year over year", "es": "Duración típica, año tras año",
    },
    "trends_duration_by_type_header": {
        "en": "Typical duration by permit type", "es": "Duración típica por tipo de permiso",
    },
    "trends_delay_reasons_header": {
        "en": "Most common delay reasons this year", "es": "Motivos de retraso más comunes este año",
    },
    "trends_permit_type_label": {"en": "Permit type", "es": "Tipo de permiso"},
    "trends_year_label": {"en": "Year", "es": "Año"},
    "trends_filters_header": {"en": "Filters", "es": "Filtros"},
    "trends_scope_label": {"en": "Show trends for", "es": "Mostrar tendencias de"},
    "trends_scope_citywide": {"en": "Citywide", "es": "Toda la ciudad"},
    "trends_scope_my_permits": {"en": "My saved permits", "es": "Mis permisos guardados"},
    "trends_my_permits_caption": {
        "en": "Based on your {n} saved permit(s), computed just now.",
        "es": "Basado en sus {n} permiso(s) guardado(s), calculado en este momento.",
    },
    "trends_my_permits_empty": {
        "en": "Star a search first to see trends across your own saved permits.",
        "es": "Marque una búsqueda primero para ver tendencias entre sus propios permisos guardados.",
    },
    "trends_date_range_label": {"en": "Date range", "es": "Rango de fechas"},
    "trends_delay_reasons_range_caption": {
        "en": "Combined across {start}–{end}",
        "es": "Combinado entre {start} y {end}",
    },

    # --- FAQ (sections/faq.py) ---------------------------------------------
    "faq_infographic_header": {
        "en": "How long does each phase typically take?",
        "es": "¿Cuánto suele tardar cada fase?",
    },
    "faq_infographic_subtext": {
        "en": "Based on the same Trends Dashboard data, for one permit type and year at a time.",
        "es": "Basado en los mismos datos del Panel de tendencias, para un tipo de permiso y año a la vez.",
    },
    "faq_infographic_typical_label": {"en": "Typical:", "es": "Típico:"},
    "faq_infographic_no_data": {
        "en": "Not separately tracked in this data.",
        "es": "No se rastrea por separado en estos datos.",
    },
    "faq_phase_1_title": {"en": "1. Before submission", "es": "1. Antes de la presentación"},
    "faq_phase_1_steps": {
        "en": "Confirm the property is within LA City zoning limits · Gather documentation (proof of ownership, project plans, contractor license) · Submit through ePlan",
        "es": "Confirmar que la propiedad está dentro de los límites de zonificación de LA · Reunir documentación (prueba de propiedad, planos, licencia de contratista) · Presentar a través de ePlan",
    },
    "faq_phase_2_title": {
        "en": "2. Plan check, corrections, payment & issuance",
        "es": "2. Revisión de planos, correcciones, pago y emisión",
    },
    "faq_phase_2_steps": {
        "en": "Routed to plan check (Express, Counter, Expanded Counter, or Regular Plan, depending on project complexity) · Correction cycles until issues are resolved · Payment · Issuance",
        "es": "Enviado a revisión de planos (Express, Mostrador, Mostrador Ampliado o Plan Regular, según la complejidad) · Ciclos de corrección hasta resolver los problemas · Pago · Emisión",
    },
    "faq_phase_3_title": {"en": "3. Construction & inspections", "es": "3. Construcción e inspecciones"},
    "faq_phase_3_steps": {
        "en": "Each phase (e.g. foundation, framing) requires its own passed inspection before work continues.",
        "es": "Cada fase (por ejemplo, cimentación, estructura) requiere su propia inspección aprobada antes de continuar.",
    },
    "faq_phase_3_duration": {
        "en": "{first} to first inspection · {between} typical gap between inspections",
        "es": "{first} hasta la primera inspección · {between} de brecha típica entre inspecciones",
    },
    "faq_phase_4_title": {"en": "4. Final inspection & closeout", "es": "4. Inspección final y cierre"},
    "faq_phase_4_steps": {
        "en": "Final inspection, then Certificate of Occupancy or permit finaled.",
        "es": "Inspección final y luego Certificado de Ocupación o cierre del permiso.",
    },
    "faq_questions_header": {"en": "Questions", "es": "Preguntas"},
    "faq_q_data_source": {"en": "Where does this data come from?", "es": "¿De dónde provienen estos datos?"},
    "faq_a_data_source": {
        "en": "Permit Check LA joins two City of Los Angeles Open Data datasets -- Building Permits and Building Inspections -- using the permit number as the shared key. Both are published by LADBS and updated on their own schedules.",
        "es": "Permit Check LA combina dos conjuntos de datos abiertos de la Ciudad de Los Ángeles -- Permisos de Construcción e Inspecciones de Construcción -- usando el número de permiso como clave compartida. Ambos son publicados por LADBS y se actualizan según sus propios calendarios.",
    },
    "faq_q_official": {
        "en": "Is this an official LADBS status check?",
        "es": "¿Es esta una verificación oficial de LADBS?",
    },
    "faq_a_official": {
        "en": "No. Permit Check LA is informational only and is not an official determination by the Los Angeles Department of Building and Safety (LADBS). Always confirm current status directly with LADBS.",
        "es": "No. Permit Check LA es solo informativo y no es una determinación oficial del Departamento de Edificación y Seguridad de Los Ángeles (LADBS). Siempre confirme el estado actual directamente con LADBS.",
    },
    "faq_q_severity": {
        "en": "What do Watch, Elevated, and Severe mean?",
        "es": "¿Qué significan Vigilancia, Elevado y Severo?",
    },
    "faq_a_severity": {
        "en": "They describe how unusual a permit's elapsed time or event count is compared to similar permits -- Watch is slower than roughly 75% of comparable permits, Elevated slower than roughly 90%, Severe slower than roughly 95%. They describe how unusual something is, not who is at fault or what caused it.",
        "es": "Describen qué tan inusual es el tiempo transcurrido o la cantidad de eventos de un permiso en comparación con permisos similares -- Vigilancia es más lento que aproximadamente el 75% de los permisos comparables, Elevado más lento que aproximadamente el 90%, Severo más lento que aproximadamente el 95%. Describen qué tan inusual es algo, no quién tiene la culpa ni qué lo causó.",
    },
    "faq_q_no_guidance": {
        "en": "Why do some findings say “No authoritative guidance available”?",
        "es": "¿Por qué algunos hallazgos dicen “No hay orientación autorizada disponible”?",
    },
    "faq_a_no_guidance": {
        "en": "Some patterns Agent 2 detects don't yet have an approved knowledge-base entry explaining what they usually mean. Rather than guess, Permit Check LA says so directly and suggests contacting LADBS about that specific permit.",
        "es": "Algunos patrones que detecta el Agente 2 aún no tienen una entrada aprobada en la base de conocimiento que explique qué suelen significar. En lugar de adivinar, Permit Check LA lo indica directamente y sugiere contactar a LADBS sobre ese permiso específico.",
    },
    "faq_q_freshness": {"en": "How current is the data?", "es": "¿Qué tan actuales son los datos?"},
    "faq_a_freshness": {
        "en": "A permit search always pulls live from the two City datasets at the moment you search. The Trends Dashboard is different -- it's built from a periodically-regenerated sample, not live, so its own “generated” date tells you how fresh it is.",
        "es": "Una búsqueda de permiso siempre obtiene datos en vivo de los dos conjuntos de datos de la Ciudad en el momento de la búsqueda. El Panel de tendencias es diferente -- se construye a partir de una muestra regenerada periódicamente, no en vivo, así que su propia fecha de “generado” indica qué tan reciente es.",
    },
    "trends_metric_label": {"en": "Metric", "es": "Métrica"},
    "trends_metric_issuance": {
        "en": "Days from submission to issuance", "es": "Días de la presentación a la emisión",
    },
    "trends_metric_first_inspection": {
        "en": "Days from issuance to first inspection",
        "es": "Días de la emisión a la primera inspección",
    },
    "trends_metric_inter_inspection": {
        "en": "Days between inspections", "es": "Días entre inspecciones",
    },
    "trends_delay_occurrences_suffix": {"en": "occurrences", "es": "ocurrencias"},

    # --- Starred searches / My Permits --------------------------------------
    "star_this_search": {"en": "☆ Star this search", "es": "☆ Marcar esta búsqueda"},
    "unstar_this_search": {"en": "★ Starred", "es": "★ Marcada"},
    "my_permits_header": {"en": "My Permits", "es": "Mis permisos"},
    "my_permits_empty": {
        "en": "You haven't starred any searches yet. Run a search, then click \"Star this search\" to have it load here automatically next time.",
        "es": "Aún no ha marcado ninguna búsqueda. Realice una búsqueda y haga clic en \"Marcar esta búsqueda\" para que se cargue aquí automáticamente la próxima vez.",
    },
    "my_permits_no_uid": {
        "en": "Starring isn't available yet this session -- try reloading the page.",
        "es": "Marcar aún no está disponible en esta sesión -- intente recargar la página.",
    },
    "my_permits_starred_searches_header": {"en": "Starred searches", "es": "Búsquedas marcadas"},
    "unstar_button": {"en": "Unstar", "es": "Quitar marca"},

    # --- Lifecycle stepper (sections/lifecycle_stepper.py) -- the general
    # LADBS permitting process, condensed for a compact per-permit-card
    # visual. Full step descriptions live in the stepper's own caption
    # line, not the dot labels themselves. ---------------------------------
    "lifecycle_step_1": {"en": "Zoning check", "es": "Verificación de zonificación"},
    "lifecycle_step_2": {"en": "Documentation", "es": "Documentación"},
    "lifecycle_step_3": {"en": "Application submitted", "es": "Solicitud presentada"},
    "lifecycle_step_4": {"en": "Plan check", "es": "Revisión de planos"},
    "lifecycle_step_5": {"en": "Payment", "es": "Pago"},
    "lifecycle_step_6": {"en": "Issuance", "es": "Emisión"},
    "lifecycle_step_7": {"en": "Construction & inspections", "es": "Construcción e inspecciones"},
    "lifecycle_step_8": {"en": "Final inspection & closeout", "es": "Inspección final y cierre"},
    "lifecycle_step_caption": {
        "en": "Step {n} of {total} — {label}",
        "es": "Paso {n} de {total} — {label}",
    },
}


# --- Error-message translation -------------------------------------------
# errors.py stays untouched (its own tests assert the exact English
# strings it returns), so known error strings are translated here instead,
# at the point they're about to be displayed.

_ERROR_TRANSLATIONS: dict[str, str] = {
    "Please enter a permit number.": "Ingrese un número de permiso.",
    "That doesn't look like a permit number -- it's too long.": (
        "Eso no parece un número de permiso -- es demasiado largo."
    ),
    "Something went wrong while analyzing this permit. Please try again shortly.": (
        "Ocurrió un error al analizar este permiso. Inténtelo de nuevo en unos momentos."
    ),
    (
        "We couldn't retrieve this permit's record right now -- the city's open data "
        "service may be temporarily unavailable."
    ): (
        "No pudimos obtener el registro de este permiso en este momento -- el servicio de "
        "datos abiertos de la ciudad podría no estar disponible temporalmente."
    ),
    (
        "We retrieved this permit's record, but couldn't complete the comparison "
        "analysis right now -- the city's open data service may be temporarily unavailable."
    ): (
        "Obtuvimos el registro de este permiso, pero no pudimos completar el análisis "
        "comparativo en este momento -- el servicio de datos abiertos de la ciudad podría no "
        "estar disponible temporalmente."
    ),
    (
        "We completed the analysis but couldn't generate the explanation right now. "
        "Please try again shortly."
    ): (
        "Completamos el análisis, pero no pudimos generar la explicación en este momento. "
        "Inténtelo de nuevo en unos momentos."
    ),
}


def _ymd_breakdown(days: int) -> str:
    """"2y 2m 3d" style breakdown of a day count into years/months/days
    (calendar-approximate: 365-day years, 30-day months) -- omits
    zero-value components except to guarantee at least one part is
    always shown (e.g. "3d", never an empty string)."""
    units = {
        "year": t("ymd_year_abbr"),
        "month": t("ymd_month_abbr"),
        "day": t("ymd_day_abbr"),
    }
    years, remainder = divmod(days, 365)
    months, d = divmod(remainder, 30)
    parts = []
    if years:
        parts.append(f"{years}{units['year']}")
    if months:
        parts.append(f"{months}{units['month']}")
    if d or not parts:
        parts.append(f"{d}{units['day']}")
    return " ".join(parts)


def _ymd_relative_phrase(days: int) -> str:
    """"today" / "2y 2m 3d ago" -- the one shared building block behind
    both status_updated_ymd_phrase() (terse, for the results table) and
    status_last_reported_changed_phrase() (the fuller quick-glance
    sentence). A raw day count like "794 days ago" is hard to size up at
    a glance; breaking it into years/months/days reads instantly."""
    if days <= 0:
        return t("today_label")
    return t("ymd_ago_template").format(ymd=_ymd_breakdown(days))


def status_updated_ymd_phrase(days_since_status_change: int) -> str:
    """"2y 2m 3d ago" -- the results table's 'Last status update' column
    value. No "status updated" prefix: the column header already says
    "Last status update", so the cell just states the relative time."""
    return _ymd_relative_phrase(days_since_status_change)


def status_last_reported_changed_phrase(days_since_status_change: int) -> str:
    """"This permit's status was last reported as changed 2y 2m 3d ago."
    -- the drill-down quick-glance panel's own, more spelled-out phrasing
    around the same _ymd_relative_phrase() the results table's column
    uses tersely. days_since_status_change is never recomputed here,
    only worded, same as every other plain-language function in this
    module."""
    return t("qg_status_last_reported_template").format(
        rel=_ymd_relative_phrase(days_since_status_change)
    )


def issuance_status_text(issued: bool) -> str:
    """"Permit has been issued" / "Permit has not been issued" -- reads
    directly off whether an issue_date is present on the latest snapshot;
    no new judgment, just wording an already-observed fact (issue_date is
    None or it isn't)."""
    return t("issued_status_text") if issued else t("not_issued_status_text")


def translate_error_message(message: str) -> str:
    """Translates a known errors.py-generated message when the current
    language is Spanish; returns it unchanged for English or for any
    string that isn't one of the fixed set errors.py can produce."""
    if get_language() != "es":
        return message
    return _ERROR_TRANSLATIONS.get(message, message)


def t(key: str) -> str:
    """Looks up a static UI string in the current language, falling back
    to English if a translation is somehow missing."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(get_language(), entry.get("en", key))
