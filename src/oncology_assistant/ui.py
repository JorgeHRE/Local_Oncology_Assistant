"""Local Streamlit chat UI for the Oncology Assistant.

Thin presentation layer over :func:`oncology_assistant.assistant.ask`: no RAG or SQL logic lives
here. Pure formatting helpers are kept free of Streamlit imports so they can be unit-tested in CI
without installing the optional ``[ui]`` extra.

Launch locally with ``make ui`` (binds to ``127.0.0.1`` with usage stats disabled).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from oncology_assistant import assistant, cohorts, corpus, rag
from oncology_assistant.db import REPO_ROOT

logger = logging.getLogger(__name__)

_COHORT_SQL_FILE = re.compile(r"^cohort_(nct\d{8})\.sql$", re.IGNORECASE)
_CATALOG_COLUMNS = ["NCT", "Título", "Cohorte OMOP", "Nota", "Rol"]


@dataclass(frozen=True)
class RouteBadge:
    """Visual label and semantic tone for the route returned by ``assistant.ask``."""

    label: str
    tone: str  # "green", "blue", "orange", "red"


@dataclass(frozen=True)
class ExamplePrompt:
    """Curated demo question shown in the sidebar."""

    label: str
    question: str
    kind: str  # "RAG" or "Cohorte OMOP"


EXAMPLE_PROMPTS: tuple[ExamplePrompt, ...] = (
    ExamplePrompt(
        label="PD-L1 CPS en NCT06346197 (RAG)",
        question="What is the required PD-L1 CPS in trial NCT06346197?",
        kind="RAG",
    ),
    ExamplePrompt(
        label="Requisito HER2 en NCT06123494 (RAG)",
        question="What is the HER2 requirement in trial NCT06123494?",
        kind="RAG",
    ),
    ExamplePrompt(
        label="Pacientes elegibles para NCT06177041 (OMOP)",
        question="How many patients are eligible for NCT06177041?",
        kind="Cohorte OMOP",
    ),
    ExamplePrompt(
        label="Cohorte piloto SPOTLIGHT NCT03504397 (OMOP)",
        question="How many patients are eligible for NCT03504397?",
        kind="Cohorte OMOP",
    ),
)

_ROUTE_BADGES: dict[str, RouteBadge] = {
    "cohort": RouteBadge(label="Cohorte OMOP (SQL)", tone="green"),
    "cohort-missing": RouteBadge(label="Cohorte no definida", tone="orange"),
    "cohort-unavailable": RouteBadge(label="Base OMOP no disponible", tone="red"),
    "rag": RouteBadge(label="RAG (citas verificadas)", tone="blue"),
}


def route_badge(response: assistant.Response) -> RouteBadge:
    """Return the Spanish UI badge describing which tool produced ``response``."""
    if response.route == "rag" and response.answer is not None:
        if response.answer.answer == rag.NOT_FOUND:
            return RouteBadge(label="RAG (sin evidencia en el corpus)", tone="orange")
        if not response.answer.grounded:
            return RouteBadge(label="RAG (citas no verificadas)", tone="orange")
    return _ROUTE_BADGES.get(
        response.route,
        RouteBadge(label=f"Ruta: {response.route}", tone="blue"),
    )


def attrition_dataframe(result: cohorts.CohortResult) -> pd.DataFrame:
    """Convert a cohort's attrition steps into a display-ready DataFrame."""
    rows = [
        {
            "Paso": step.step,
            "Filtro aplicado": step.description,
            "Pacientes restantes": step.n_remaining,
            "Descartados": step.n_lost,
        }
        for step in result.attrition
    ]
    return pd.DataFrame(
        rows,
        columns=["Paso", "Filtro aplicado", "Pacientes restantes", "Descartados"],
    )


def sample_dataframe(result: cohorts.CohortResult) -> pd.DataFrame:
    """Convert a cohort's sample patients into a display-ready DataFrame."""
    rows = [
        {"person_id": person_id, "Fecha índice": str(index_date)}
        for person_id, index_date in result.sample
    ]
    return pd.DataFrame(rows, columns=["person_id", "Fecha índice"])


def citation_rows(answer: rag.Answer) -> list[dict[str, Any]]:
    """Build structured citation items for rendering in the UI."""
    return [
        {
            "passage": citation.passage,
            "doc_id": citation.doc_id or "desconocido",
            "quote": citation.quote,
            "verified": citation.verified,
            "status": "Verificada en el fragmento"
            if citation.verified
            else "No encontrada literalmente",
        }
        for citation in answer.citations
    ]


def passage_summary(index: int, hit: dict[str, Any]) -> dict[str, Any]:
    """Extract display fields from a single retrieved passage dict."""
    meta = hit.get("metadata") or {}
    distance = hit.get("distance")
    return {
        "number": index,
        "doc_id": meta.get("doc_id") or hit.get("id", "desconocido"),
        "section": meta.get("section") or "sin sección",
        "distance": float(distance) if distance is not None else None,
        "text": str(hit.get("text", "")),
    }


def format_runtime_error(exc: Exception) -> str:
    """Translate expected local runtime errors into actionable Spanish messages."""
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return (
            "No se pudo conectar con el servidor local de Ollama (`127.0.0.1:11500`). "
            "Inícialo con `make llm-up` y vuelve a intentar."
        )
    if isinstance(exc, FileNotFoundError):
        return (
            "No se encontró un archivo o índice local requerido. "
            "Verifica haber ejecutado `make index-embed`."
        )
    return f"Ocurrió un error al procesar la consulta: {exc}"


def cohort_trial_ids(sql_dir: Path | None = None) -> set[str]:
    """Return the uppercase NCT ids that have an OMOP cohort SQL script in ``sql/``."""
    directory = sql_dir or (REPO_ROOT / "sql")
    if not directory.is_dir():
        return set()
    ids: set[str] = set()
    for path in directory.iterdir():
        match = _COHORT_SQL_FILE.match(path.name)
        if match:
            ids.add(match.group(1).upper())
    if (directory / "02_cohorte.sql").is_file():
        ids.update(cohorts.LEGACY_PREFIXES.values())
    return ids


def trial_catalog_dataframe(
    manifest_path: Path | None = None,
    sql_dir: Path | None = None,
) -> pd.DataFrame:
    """Build a searchable table of the ClinicalTrials.gov trials in the corpus manifest."""
    path = manifest_path or corpus.MANIFEST_PATH
    if not path.is_file():
        return pd.DataFrame(columns=_CATALOG_COLUMNS)
    data = json.loads(path.read_text(encoding="utf-8"))
    with_cohort = cohort_trial_ids(sql_dir)
    rows = []
    for doc in data.get("documents", []):
        if doc.get("source") != "clinicaltrials.gov":
            continue
        nct = str(doc.get("identifier", "")).upper()
        if not nct:
            continue
        rows.append(
            {
                "NCT": nct,
                "Título": str(doc.get("title", "")),
                "Cohorte OMOP": "Sí" if nct in with_cohort else "Solo RAG",
                "Nota": str(doc.get("note", "")),
                "Rol": str(doc.get("role", "")),
            }
        )
    df = pd.DataFrame(rows, columns=_CATALOG_COLUMNS)
    if df.empty:
        return df
    return df.sort_values(
        by=["Cohorte OMOP", "NCT"],
        key=lambda col: col.map({"Sí": 0, "Solo RAG": 1}) if col.name == "Cohorte OMOP" else col,
    ).reset_index(drop=True)


def filter_trial_catalog(
    df: pd.DataFrame,
    query: str = "",
    only_with_cohort: bool = False,
) -> pd.DataFrame:
    """Filter the trial catalog by cohort availability and free-text substring match."""
    if df.empty:
        return df
    filtered = df[df["Cohorte OMOP"] == "Sí"] if only_with_cohort else df
    term = query.strip().lower()
    if not term:
        return filtered.reset_index(drop=True)
    mask = (
        filtered["NCT"].str.lower().str.contains(term, regex=False)
        | filtered["Título"].str.lower().str.contains(term, regex=False)
        | filtered["Nota"].str.lower().str.contains(term, regex=False)
        | filtered["Rol"].str.lower().str.contains(term, regex=False)
    )
    return filtered[mask].reset_index(drop=True)


def _render_cohort_response(st: Any, response: assistant.Response) -> None:
    """Render an OMOP cohort result with metrics, attrition table and sample."""
    result = response.cohort
    if result is None:
        st.markdown(response.text)
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Ensayo", result.trial)
    col2.metric("Pacientes elegibles", result.count)
    col3.metric("Filtros aplicados", len(result.attrition))

    st.markdown(
        f"Cohorte de **{result.trial}** en la base sintética OMOP: "
        f"**{result.count} pacientes** cumplen los criterios evaluables en los datos."
    )

    if result.attrition:
        st.caption("Tabla de atrición (recuento exacto desde vistas SQL, sin LLM):")
        st.dataframe(
            attrition_dataframe(result),
            use_container_width=True,
            hide_index=True,
        )

    if result.sample:
        with st.expander(f"Muestra de los primeros {len(result.sample)} pacientes sintéticos"):
            st.dataframe(
                sample_dataframe(result),
                use_container_width=True,
                hide_index=True,
            )

    st.caption(
        "Nota: datos sintéticos (Synthea -> OMOP CDM v5.4). Los criterios no evaluables "
        "en la base (p. ej. ciertos laboratorios o enfermedad medible) no forman parte de esta "
        "cohorte."
    )


def _render_rag_response(st: Any, response: assistant.Response) -> None:
    """Render a RAG answer with verified citations and expandable retrieved passages."""
    answer = response.answer
    if answer is None:
        st.markdown(response.text)
        return

    st.markdown(answer.answer)

    if answer.citations:
        if not answer.grounded:
            st.warning(
                "Al menos una cita no coincide literalmente con el fragmento recuperado; "
                "no confíes en esta respuesta sin verificar el documento original."
            )
        st.markdown("**Fuentes citadas:**")
        for item in citation_rows(answer):
            icon = "✅" if item["verified"] else "⚠️"
            st.markdown(
                f"{icon} **[{item['passage']}]** `{item['doc_id']}` "
                f'— *{item["status"]}*\n> "{item["quote"]}"'
            )
    elif answer.answer != rag.NOT_FOUND:
        st.warning("La respuesta no incluye citas verificables; no confíes en ella.")

    if answer.retried:
        st.caption("Una cita fue corregida automáticamente en un segundo intento.")

    if answer.passages or answer.search_query:
        with st.expander(f"Fragmentos recuperados ({len(answer.passages)})"):
            if answer.search_query:
                st.caption(f"Consulta reformulada: `{answer.search_query}`")
            for idx, hit in enumerate(answer.passages, start=1):
                info = passage_summary(idx, hit)
                dist = (
                    f" · distancia {info['distance']:.3f}" if info["distance"] is not None else ""
                )
                st.markdown(f"**[{info['number']}] `{info['doc_id']}`** ({info['section']}){dist}")
                st.text(info["text"])


def _render_response(st: Any, response: assistant.Response) -> None:
    """Render any ``assistant.Response`` inside a Streamlit chat message."""
    badge = route_badge(response)
    st.badge(badge.label, color=badge.tone)

    if response.route == "cohort":
        _render_cohort_response(st, response)
    elif response.route == "rag":
        _render_rag_response(st, response)
    elif response.route == "cohort-unavailable":
        st.error(response.text)
    else:
        st.warning(response.text)


def render_app() -> None:
    """Build and run the Streamlit web interface."""
    import streamlit as st

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    st.set_page_config(
        page_title="Local Oncology Assistant",
        page_icon="🩺",
        layout="wide",
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.header("Configuración")
        k = st.slider(
            "Fragmentos recuperados (k)",
            min_value=1,
            max_value=12,
            value=6,
            help="Número de fragmentos del corpus enviados al LLM en consultas RAG.",
        )
        rewrite = st.checkbox(
            "Reformular consulta (rewrite)",
            value=True,
            help="Expande abreviaturas y biomarcadores antes de buscar en ChromaDB.",
        )

        st.divider()
        st.subheader("Preguntas de demostración")
        st.caption("Haz clic en un ejemplo para ejecutarlo directamente (en inglés):")
        selected_example: str | None = None
        for idx, item in enumerate(EXAMPLE_PROMPTS):
            if st.button(item.label, key=f"example_{idx}", use_container_width=True):
                selected_example = item.question

        st.divider()
        if st.button("Limpiar conversación", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.caption(
            "**Aviso de uso:** Prototipo de investigación 100 % local sobre datos sintéticos. "
            "No es un dispositivo médico ni debe usarse para decisiones clínicas "
            "(`docs/POLITICA_DE_USO.md`)."
        )

    st.title("Local Oncology Assistant")
    st.caption(
        "Asistente local de tamizaje de elegibilidad en cáncer gástrico: "
        "RAG con citas verificadas sobre ensayos clínicos + cohortes exactas en OMOP CDM v5.4."
    )
    st.info(
        "Escribe tus consultas **en inglés** (el corpus de ClinicalTrials.gov y el enrutador "
        "de cohortes están validados en inglés). Cada consulta se evalúa de forma independiente."
    )

    catalog = trial_catalog_dataframe()
    if not catalog.empty:
        n_cohorts = int((catalog["Cohorte OMOP"] == "Sí").sum())
        with st.expander(
            f"📚 Catálogo de ensayos del corpus ({len(catalog)} NCTs · {n_cohorts} con cohorte OMOP)"
        ):
            col_search, col_filter = st.columns([3, 1])
            search_term = col_search.text_input(
                "Buscar por NCT, biomarcador, fármaco o título",
                placeholder="Ej. HER2, CLDN18, PD-L1, ToGA, NCT061...",
                key="catalog_search",
            )
            only_cohorts = col_filter.checkbox(
                f"Solo con cohorte OMOP ({n_cohorts})",
                value=False,
                key="catalog_only_cohorts",
            )
            filtered = filter_trial_catalog(
                catalog, query=search_term, only_with_cohort=only_cohorts
            )
            st.caption(
                f"Mostrando {len(filtered)} de {len(catalog)} ensayos clínicos "
                "(copia cualquier NCT y pégalo en la caja de chat)."
            )
            st.dataframe(filtered, use_container_width=True, hide_index=True)

    for entry in st.session_state.messages:
        with st.chat_message(entry["role"]):
            if entry["role"] == "user":
                st.markdown(entry["content"])
            elif entry.get("error"):
                st.error(entry["error"])
            else:
                _render_response(st, entry["response"])

    typed_question = st.chat_input(
        "Escribe tu consulta en inglés (ej. How many patients are eligible for NCT06177041?)"
    )
    question = selected_example or typed_question

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"), st.spinner("Consultando el asistente local..."):
            try:
                response = assistant.ask(question, k=k, rewrite=rewrite)
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                logger.exception("Failed to answer question in Streamlit UI")
                err_msg = format_runtime_error(exc)
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "error": err_msg})
            else:
                _render_response(st, response)
                st.session_state.messages.append({"role": "assistant", "response": response})


if __name__ == "__main__":
    render_app()
