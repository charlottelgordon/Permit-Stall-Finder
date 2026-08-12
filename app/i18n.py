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

from collections import Counter

import streamlit as st
import streamlit.components.v1 as components

import formatting
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome
from permit_stall_finder.schema.developer_explanation import GroundingStrength, VerificationStatus
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus
from permit_stall_finder.schema.stall_detection import BenchmarkSemantics, IntervalState, Severity, StallCategory

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "es": "Español"}


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
    """A small language picker. Changing it reruns the script (every
    Streamlit widget interaction does), and every t()/label lookup below
    reads st.session_state["language"] fresh on that rerun -- so the
    whole page reflects the choice immediately, not just newly-rendered
    widgets."""
    current = get_language()
    _sync_html_lang(current)
    codes = list(LANGUAGES.keys())
    choice = st.radio(
        "Language / Idioma",
        options=codes,
        format_func=lambda code: LANGUAGES[code],
        index=codes.index(current),
        key="language_picker",
        horizontal=True,
        label_visibility="collapsed",
    )
    if choice != current:
        set_language(choice)
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
        "El estado y la fecha de emisión del registro de origen son inconsistentes entre sí "
        "para este permiso."
    ),
    DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE: (
        "Este tipo de permiso tiene una tasa de coincidencia históricamente incierta con el "
        "conjunto de datos público de inspecciones -- una inspección faltante es menos "
        "informativa para este tipo."
    ),
    DataQualityFlag.FIRST_OBSERVATION: (
        "Esta es la primera vez que esta herramienta observa este permiso -- no se conoce el "
        "historial de estado anterior."
    ),
}

BENCHMARK_SEMANTICS_LABELS_ES: dict[BenchmarkSemantics, str] = {
    BenchmarkSemantics.ACTIVE_PEER_DWELL: "Comparado con: permisos actualmente en este estado",
    BenchmarkSemantics.COMPLETED_INTERVAL: "Comparado con: intervalos comparables completados",
}

INTERVAL_STATE_LABELS_ES: dict[IntervalState, str] = {
    IntervalState.ONGOING: "Aún en curso",
    IntervalState.COMPLETED: "Intervalo completado",
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


def outcome_headline(result) -> str:
    if get_language() != "es":
        return formatting.outcome_headline(result)
    if result.outcome == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED:
        return OUTCOME_CLEAN_TEXT_ES
    if result.outcome == AnalysisOutcome.INSUFFICIENT_EVIDENCE:
        return OUTCOME_INSUFFICIENT_TEXT_ES
    return summarize_severity_counts(result.stall_assessment.detections)


# --- Static UI chrome ----------------------------------------------------

_STRINGS: dict[str, dict[str, str]] = {
    "page_intro": {
        "en": (
            "Understand the observable journey of an LA building permit, identify unusual "
            "delays or process friction, and see grounded guidance on what may happen next. "
            "Paste one permit number for a full deep-dive, or several to triage a portfolio "
            "at once -- or search by address if you don't have the permit number handy."
        ),
        "es": (
            "Entienda el trayecto observable de un permiso de construcción de LA, identifique "
            "retrasos inusuales o fricciones en el proceso, y vea orientación fundamentada "
            "sobre lo que podría pasar después. Pegue un número de permiso para un análisis "
            "completo, o varios para evaluar un portafolio a la vez -- o busque por dirección "
            "si no tiene a la mano el número de permiso."
        ),
    },
    "clear_results": {"en": "Clear results", "es": "Borrar resultados"},
    "tab_permit_number": {"en": "Search by permit number", "es": "Buscar por número de permiso"},
    "tab_address": {"en": "Search by address", "es": "Buscar por dirección"},
    "permit_numbers_label": {"en": "Permit number(s)", "es": "Número(s) de permiso"},
    "analyze_button": {"en": "Analyze", "es": "Analizar"},
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
    "permit_caption": {"en": "Permit", "es": "Permiso"},
    "show_full_analysis": {
        "en": "Show full analysis (permit journey, finding-by-finding explanations, coverage notes)",
        "es": "Mostrar análisis completo (trayecto del permiso, explicaciones de cada hallazgo, "
        "notas de cobertura)",
    },
    "finding_singular": {"en": "finding", "es": "hallazgo"},
    "finding_plural": {"en": "findings", "es": "hallazgos"},
    # quick_access.py
    "starred": {"en": "⭐ Starred", "es": "⭐ Destacados"},
    "recent": {"en": "🕒 Recent", "es": "🕒 Recientes"},
    "manage_starred": {"en": "Manage starred", "es": "Administrar destacados"},
    "unstar": {"en": "Unstar", "es": "Quitar destacado"},
    "starred_button": {"en": "★ Starred", "es": "★ Destacado"},
    "star_this_button": {"en": "☆ Star this", "es": "☆ Destacar"},
    # address_search.py
    "address_search_caption": {
        "en": "Don't know the permit number? Search by street address and pick the permit(s) "
        "you want analyzed.",
        "es": "¿No sabe el número de permiso? Busque por dirección y seleccione el o los "
        "permisos que desea analizar.",
    },
    "street_address_label": {"en": "Street address", "es": "Dirección"},
    "street_address_placeholder": {"en": "e.g. 200 N Spring St", "es": "p. ej. 200 N Spring St"},
    "search_by_address_button": {"en": "Search by address", "es": "Buscar por dirección"},
    "warning_enter_address": {
        "en": "Enter a street address to search.",
        "es": "Ingrese una dirección para buscar.",
    },
    "info_no_permits_found": {
        "en": "No permits found for that address. Try a shorter or differently formatted address.",
        "es": "No se encontraron permisos para esa dirección. Intente con una dirección más "
        "corta o con otro formato.",
    },
    "permits_found_caption": {
        "en": "permit(s) found -- select which to analyze:",
        "es": "permiso(s) encontrado(s) -- seleccione cuál(es) analizar:",
    },
    "analyze_selected_button": {"en": "Analyze selected", "es": "Analizar seleccionados"},
    # quick_glance.py
    "qg_permit": {"en": "Permit", "es": "Permiso"},
    "qg_address": {"en": "Address", "es": "Dirección"},
    "qg_type": {"en": "Type", "es": "Tipo"},
    "qg_status": {"en": "Status", "es": "Estado"},
    "qg_days_in_status": {"en": "Days in status", "es": "Días en este estado"},
    "qg_top_finding": {"en": "Top finding", "es": "Hallazgo principal"},
    "qg_result": {"en": "Result", "es": "Resultado"},
    # location_map.py
    "city_label": {"en": "City of Los Angeles", "es": "Ciudad de Los Ángeles"},
    "county_label": {"en": "Los Angeles County", "es": "Condado de Los Ángeles"},
    "map_unavailable": {
        "en": "Map unavailable -- this permit's source record has no coordinates.",
        "es": "Mapa no disponible -- el registro de origen de este permiso no tiene coordenadas.",
    },
    "open_in_google_maps": {"en": "Open in Google Maps", "es": "Abrir en Google Maps"},
    "zip_prefix": {"en": "ZIP", "es": "Código postal"},
    # coverage_gaps.py
    "coverage_notes_header": {
        "en": "Coverage & data-quality notes",
        "es": "Notas de cobertura y calidad de datos",
    },
    "coverage_notes_warning": {
        "en": "Parts of this permit could not be fully assessed, or the underlying data has "
        "known limitations. This is separate from -- and does not confirm or rule out -- "
        "a stall.",
        "es": "Algunas partes de este permiso no se pudieron evaluar por completo, o los datos "
        "subyacentes tienen limitaciones conocidas. Esto es independiente de -- y no confirma "
        "ni descarta -- un estancamiento.",
    },
    "coverage_gaps_label": {"en": "Coverage gaps", "es": "Vacíos de cobertura"},
    "data_quality_notes_label": {"en": "Data-quality notes", "es": "Notas de calidad de datos"},
    # permit_journey.py
    "permit_journey_header": {"en": "Permit journey", "es": "Trayecto del permiso"},
    "no_journey_record": {
        "en": "No permit record was found to reconstruct a journey from.",
        "es": "No se encontró ningún registro de permiso a partir del cual reconstruir un trayecto.",
    },
    "observed_milestones": {"en": "Observed milestones", "es": "Hitos observados"},
    "submitted": {"en": "Submitted", "es": "Presentado"},
    "current_status_prefix": {"en": "Current status", "es": "Estado actual"},
    "issued": {"en": "Issued", "es": "Emitido"},
    "cofo_issued": {"en": "Certificate of Occupancy issued", "es": "Certificado de ocupación emitido"},
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
    "stall_findings_header": {"en": "Stall findings", "es": "Hallazgos de estancamiento"},
    "mixed_grounding_caption": {
        "en": "Some findings below are backed by an authoritative knowledge-base entry; "
        "others are not -- this is noted individually on each finding.",
        "es": "Algunos hallazgos a continuación están respaldados por una entrada autorizada de "
        "la base de conocimiento; otros no -- esto se indica individualmente en cada hallazgo.",
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
    "learn_more_prefix": {"en": "Learn more about your", "es": "Más información sobre sus"},
    "grounded_findings_suffix": {"en": "grounded finding(s)", "es": "hallazgo(s) fundamentado(s)"},
    # portfolio.py
    "portfolio_triage_header": {"en": "Portfolio triage", "es": "Evaluación del portafolio"},
    "portfolio_worst_first": {"en": "permits, worst first.", "es": "permisos, del peor al mejor."},
    "portfolio_severity_col": {"en": "Severity", "es": "Severidad"},
    "portfolio_dev_action_col": {
        "en": "Developer action available",
        "es": "Acción del desarrollador disponible",
    },
    "portfolio_view_detail_for": {"en": "View full detail for:", "es": "Ver detalle completo de:"},
    "yes": {"en": "Yes", "es": "Sí"},
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
