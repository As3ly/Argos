"""ui_app.py

UI NiceGUI pour piloter les recherches (jobs) et consulter les AO.

Philosophie:
- L'UI ne "scrape" pas et ne fait pas d'IA directement. Elle orchestre via pipeline.py.
- Zéro asyncio.run(). Tous les handlers peuvent être async.

Lancement:
    uv run ui_app.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from nicegui import ui

from db import repository as db_repository
from pipeline import (
    KeywordsResult,
    create_job_for_prompt,
    generate_keywords,
    get_available_scrapers,
    mots_recherche_to_requete,
    run_full_pipeline,
)

HISTORY_PAGE_SIZE = 20
ACTIVE_JOB_STATUSES = {"en_cours", "generation_mots_cle", "scraping", "tri_ia"}

PALETTE = {
    "ink": "#182230",
    "muted": "#667085",
    "line": "#EAECF0",
    "panel": "#FFFFFF",
    "soft": "#F8FAFC",
    "blue": "#2563EB",
    "blue_dark": "#1D4ED8",
    "orange": "#D97706",
    "green": "#16A34A",
    "red": "#DC2626",
}


def _score_style(score: Any) -> str:
    try:
        value = float(str(score).replace(",", "."))
    except (TypeError, ValueError):
        value = 0.0

    if value >= 0.85:
        fg, bg = PALETTE["green"], "#ECFDF3"
    elif value >= 0.7:
        fg, bg = PALETTE["orange"], "#FFFAEB"
    else:
        fg, bg = PALETTE["blue"], "#EFF6FF"

    return f"border-color: {fg}; color: {fg}; background: {bg}; font-weight: 600;"


ui.add_head_html(
    f"""
    <style>
      body.body--light {{ background: #F6F7FB; color: {PALETTE["ink"]}; }}
      .argos-page {{ min-height: 100vh; background: #F6F7FB; }}
      .argos-shell {{ width: min(1680px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 48px; }}
      .argos-detail-shell {{ width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 48px; }}
      .argos-workspace {{ display: grid; grid-template-columns: minmax(420px, 520px) minmax(0, 1fr); gap: 20px; align-items: start; }}
      .argos-left-pane, .argos-right-pane {{ min-width: 0; }}
      .argos-right-pane {{ position: sticky; top: 20px; max-height: calc(100vh - 40px); overflow: auto; padding-right: 2px; }}
      .argos-empty-detail {{ min-height: 420px; display: flex; align-items: center; justify-content: center; text-align: center; }}
      .home-split {{ display: grid; grid-template-columns: minmax(420px, 520px) minmax(0, 1fr); gap: 20px; align-items: start; }}
      .home-split .argos-topbar {{ grid-column: 1 / -1; }}
      .home-split .argos-left-gap {{ display: none; }}
      .argos-detail-home {{ grid-column: 2; grid-row: 2 / span 4; }}
      .argos-topbar {{ background: #FFFFFF; border: 1px solid {PALETTE["line"]}; border-radius: 8px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
      .argos-title {{ color: {PALETTE["ink"]}; font-size: 1.45rem; font-weight: 700; letter-spacing: 0; line-height: 1.2; }}
      .argos-subtitle {{ color: {PALETTE["muted"]}; font-size: .92rem; line-height: 1.45; }}
      .argos-panel {{ background: #FFFFFF; border: 1px solid {PALETTE["line"]}; border-radius: 8px; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
      .argos-panel-header {{ padding: 16px 18px 0; }}
      .argos-panel-body {{ padding: 16px 18px 18px; }}
      .argos-section-title {{ color: {PALETTE["ink"]}; font-size: .96rem; font-weight: 650; }}
      .argos-muted {{ color: {PALETTE["muted"]}; }}
      .argos-source-tile {{ border: 1px solid {PALETTE["line"]}; background: #FFFFFF; border-radius: 8px; padding: 10px 12px; min-width: 148px; }}
      .argos-source-tile:hover {{ border-color: #C7D7FE; background: #F8FAFF; }}
      .job-card {{ border-radius: 8px; border: 1px solid {PALETTE["line"]}; background: #FFFFFF; transition: box-shadow .16s ease, border-color .16s ease, transform .16s ease; }}
      .job-card:hover {{ box-shadow: 0 8px 24px rgba(16, 24, 40, .07); border-color: #D0D5DD; transform: translateY(-1px); }}
      .job-title {{ color: {PALETTE["ink"]}; font-size: .98rem; font-weight: 650; line-height: 1.35; white-space: normal; overflow-wrap: anywhere; }}
      .job-meta {{ color: {PALETTE["muted"]}; font-size: .82rem; }}
      .ao-card {{ border-radius: 8px; border: 1px solid {PALETTE["line"]}; background: #FFFFFF; transition: box-shadow .16s ease, border-color .16s ease; }}
      .ao-card:hover {{ box-shadow: 0 8px 24px rgba(16, 24, 40, .07); border-color: #D0D5DD; }}
      .ao-title {{ font-size: 1rem; font-weight: 650; color: {PALETTE["ink"]}; line-height: 1.4; white-space: normal; overflow-wrap: anywhere; }}
      .ao-meta {{ color: {PALETTE["muted"]}; }}
      .ao-chip {{ border-color: #C7D7FE; color: {PALETTE["blue"]}; background: #F8FAFF; }}
      .ao-link {{ color: {PALETTE["blue"]}; font-weight: 600; }}
      .ao-link:hover {{ color: {PALETTE["blue_dark"]}; }}
      .ao-details-btn {{ color: {PALETTE["blue"]}; font-weight: 600; }}
      .ao-details-btn:hover {{ color: {PALETTE["orange"]}; }}
      .saved-prompts-grid {{ display: grid; grid-template-columns: minmax(320px, 420px) minmax(0, 1fr); gap: 16px; align-items: start; }}
      .saved-prompts-dialog {{ width: min(1480px, 98vw) !important; max-width: 98vw !important; height: min(920px, 94vh) !important; max-height: 94vh !important; display: flex; flex-direction: column; overflow: hidden; }}
      .saved-prompts-body {{ flex: 1; min-height: 0; }}
      .saved-prompts-list {{ height: 100%; min-height: 0; overflow: auto; padding-right: 2px; }}
      .saved-prompt-card {{ appearance: none; display: block; border: 1px solid {PALETTE["line"]}; background: #FFFFFF; border-radius: 8px; padding: 12px; cursor: pointer; text-align: left; transition: border-color .16s ease, box-shadow .16s ease, background .16s ease; }}
      .saved-prompt-card:hover {{ border-color: #C7D7FE; background: #F8FAFF; box-shadow: 0 8px 24px rgba(16, 24, 40, .07); }}
      .saved-prompt-text {{ color: {PALETTE["ink"]}; font-size: .9rem; line-height: 1.45; white-space: pre-line; overflow-wrap: anywhere; }}
      .ao-dialog {{ border-radius: 8px; border: 1px solid {PALETTE["line"]}; box-shadow: 0 24px 54px rgba(16, 24, 40, 0.16); }}
      .ao-dialog-title {{ font-size: 1.18rem; font-weight: 650; color: {PALETTE["ink"]}; line-height: 1.4; }}
      .ao-field-key {{ color: #6B7485; font-weight: 500; }}
      .ao-field-value {{ color: #222E43; }}
      .ao-soft-section {{ background: #F8FAFC; border: 1px solid {PALETTE["line"]}; border-radius: 8px; padding: .75rem; }}
      .q-field--outlined .q-field__control {{ border-radius: 8px; }}
      .q-btn {{ border-radius: 8px; text-transform: none; font-weight: 600; }}
      .q-chip {{ border-radius: 999px; }}
      @media (max-width: 1100px) {{
        .argos-workspace, .home-split {{ grid-template-columns: 1fr; }}
        .argos-right-pane {{ position: static; max-height: none; overflow: visible; }}
        .argos-detail-home {{ grid-column: auto; grid-row: auto; }}
        .saved-prompts-grid {{ grid-template-columns: 1fr; align-content: start; overflow: auto; }}
        .saved-prompts-list {{ height: auto; max-height: 40vh; }}
      }}
    </style>
    """,
    shared=True,
)



###############################################################################
# DB helpers (on reste aligné avec db_repository.DB_PATH)
###############################################################################


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_repository.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def count_jobs() -> int:
    return db_repository.count_recherche_jobs()


def list_jobs(limit: int = HISTORY_PAGE_SIZE, offset: int = 0) -> List[Dict[str, Any]]:
    return list(
        db_repository.list_recherche_jobs(
            limit=limit,
            offset=offset,
            order_by="date_lancement DESC",
        )
    )


def get_job(search_id: int) -> Optional[Dict[str, Any]]:
    with closing(_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titre, requete, prompt_initial, source, params, warnings_json, date_lancement, statut, nb_trouves, nb_insere
            FROM recherches_jobs
            WHERE id = ?
            LIMIT 1
            """,
            (search_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_aos_p(search_id: int, limit: int = 300, *, score_desc: bool = True) -> List[Dict[str, Any]]:
    score_order = "DESC" if score_desc else "ASC"
    return list(
        db_repository.list_appels_offres_pert(
            search_id=search_id,
            limit=limit,
            order_by=f"score_ia {score_order}, date_ajout DESC",
        )
    )


def list_aos_np(search_id: int, limit: int = 300) -> List[Dict[str, Any]]:
    return list(
        db_repository.list_appels_offres_non_pert(
            search_id=search_id,
            limit=limit,
            order_by="date_ajout DESC",
        )
    )


###############################################################################
# UI helpers
###############################################################################


def _fmt_dt(s: Any) -> str:
    if s is None:
        return ""
    if isinstance(s, str):
        return s
    return str(s)


def _chip(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    t = str(value).strip()
    return t if t else fallback


def _status_badge(statut: str | None) -> Tuple[str, str]:
    """Retourne (label, class)."""
    s = (statut or "").strip().lower()
    mapping = {
        "en_cours": ("en cours", "bg-blue-50 text-blue-700"),
        "generation_mots_cle": ("mots-clés", "bg-purple-50 text-purple-700"),
        "scraping": ("scraping", "bg-amber-50 text-amber-700"),
        "tri_ia": ("tri IA", "bg-indigo-50 text-indigo-700"),
        "termine": ("terminé", "bg-green-50 text-green-700"),
        "erreur_scraper": ("erreur scraper", "bg-red-50 text-red-700"),
        "erreur_pipeline": ("erreur pipeline", "bg-red-50 text-red-700"),
        "erreur_generation": ("erreur génération", "bg-red-50 text-red-700"),
    }
    return mapping.get(s, (s or "?", "bg-gray-50 text-gray-700"))


def _status_key(statut: Any) -> str:
    return str(statut or "").strip().lower()


def _job_is_active(job: Dict[str, Any]) -> bool:
    return _status_key(job.get("statut")) in ACTIVE_JOB_STATUSES


def _job_has_warning(job: Dict[str, Any] | None) -> bool:
    if not job:
        return False
    warning_blob = (job.get("warnings_json") or "").strip()
    if not warning_blob:
        return False
    try:
        parsed = json.loads(warning_blob)
    except Exception:
        return True
    if isinstance(parsed, dict):
        limited = parsed.get("limited_searches")
        if isinstance(limited, list) and limited:
            return True
        if parsed.get("severity") in {"warning", "error"}:
            return True
        return bool(parsed.get("error"))
    if isinstance(parsed, list):
        return any(bool(item) for item in parsed)
    return bool(parsed)


def _render_status_badges(job_or_status: Any) -> None:
    if isinstance(job_or_status, dict):
        statut = job_or_status.get("statut")
        has_warning = _job_has_warning(job_or_status)
    else:
        statut = job_or_status
        has_warning = False
    label, cls = _status_badge(statut)
    ui.chip(label).classes(f"text-sm {cls}").props("outline")
    if _status_key(statut) == "termine" and has_warning:
        ui.chip("à vérifier", icon="warning").classes("text-xs bg-amber-50 text-amber-700").props("outline dense")


def _source_label(source: Any) -> str:
    labels = {
        "boamp": "BOAMP",
        "ted": "TED / JOUE",
        "francemarches": "France Marchés",
    }
    codes = [item.strip() for item in str(source or "").split(",") if item.strip()]
    if not codes:
        return "-"
    return " + ".join(labels.get(code, code) for code in codes)


def _source_summary(options: Sequence[Dict[str, str]]) -> str:
    if not options:
        return "Aucune source active"
    return " + ".join(option.get("label") or option.get("code", "") for option in options)


def build_job_card(
    job: Dict[str, Any],
    *,
    selected: bool = False,
    active: bool = False,
    on_open=None,
    on_selection_change=None,
    on_delete=None,
) -> None:
    rid = job["id"]
    titre_card = job.get("titre") or ""
    source = job.get("source") or ""
    dt = job.get("date_lancement")
    is_active = _job_is_active(job)

    card = (
        ui.card()
        .classes("w-full job-card" + (" border-blue-300 bg-blue-50" if active else ""))
        .props("flat bordered")
    )
    with card:
        with ui.row().classes("w-full items-start gap-3 flex-nowrap"):
            checkbox = ui.checkbox(value=selected, on_change=lambda e, _rid=rid: on_selection_change and on_selection_change(_rid, bool(e.value))).props("dense")
            if is_active:
                checkbox.props("disable")
                with checkbox:
                    ui.tooltip("Suppression indisponible pendant l'exécution")

            with ui.column().classes("flex-1 min-w-0 gap-1"):
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    ui.label(titre_card or f"Recherche #{rid}").classes("job-title flex-1 min-w-0")
                    with ui.row().classes("items-center gap-1 shrink-0"):
                        _render_status_badges(job)

                with ui.row().classes("w-full items-center justify-between gap-3"):
                    ui.label(f"#{rid} · {_source_label(source)} · {_fmt_dt(dt)}").classes("job-meta")
                    ui.label(
                        f"{_chip(job.get('nb_trouves'), '0')} trouvés · {_chip(job.get('nb_insere'), '0')} insérés"
                    ).classes("job-meta")

            with ui.row().classes("items-center gap-1 shrink-0"):
                def open_job(_e=None, _rid=rid):
                    if on_open:
                        on_open(_rid)
                    else:
                        ui.navigate.to(f"/recherche/{_rid}")

                open_btn = ui.button(icon="open_in_new", on_click=open_job).props("flat round dense")
                with open_btn:
                    ui.tooltip("Ouvrir")

                delete_btn = ui.button(icon="delete", on_click=lambda _e=None, _rid=rid: on_delete and on_delete([_rid])).props("flat round dense").classes("text-red-600")
                if is_active:
                    delete_btn.props("disable")
                    with delete_btn:
                        ui.tooltip("Suppression indisponible pendant l'exécution")
                else:
                    with delete_btn:
                        ui.tooltip("Supprimer")


def make_ao_dialog(ao: Dict[str, Any], on_open=None, on_close=None) -> ui.dialog:
    dlg = ui.dialog()

    if on_open:
        dlg.on('show', lambda e=None: on_open())
    if on_close:
        dlg.on('hide', lambda e=None: on_close())

    with dlg, ui.card().classes("w-[min(960px,95vw)] ao-dialog p-2"):
        with ui.row().classes("w-full items-start justify-between gap-4"):
            ui.label(_chip(ao.get("titre"), "(sans titre)")).classes("ao-dialog-title flex-1")
            ui.button(icon="close", on_click=dlg.close).props("flat round").classes("ao-details-btn")

        with ui.row().classes("w-full gap-2 mt-1"):
            score_chip = ui.chip(f"score: {_chip(ao.get('score_ia'))}").props("outline")
            score_chip.style(_score_style(ao.get("score_ia")))
            ui.chip(f"source: {_chip(ao.get('source'))}").props("outline").classes("ao-chip")
            ui.chip(f"publication: {_chip(ao.get('date_publication'))}").props("outline").classes("ao-chip")
            ui.chip(f"clôture: {_chip(ao.get('date_cloture'))}").props("outline").classes("ao-chip")

        ui.separator().classes("my-3")

        with ui.column().classes("w-full gap-2 ao-soft-section"):
            def field(k: str, v: Any) -> None:
                with ui.row().classes("w-full items-start gap-4"):
                    ui.label(k).classes("w-40 ao-field-key")
                    ui.label(_chip(v, "")).classes("flex-1 ao-field-value whitespace-pre-line")

            field("Acheteur", ao.get("acheteur"))
            field("Lieu", ao.get("lieu"))
            field("Type marché", ao.get("type_marche"))
            field("Budget", ao.get("budget"))
            field("Référence", ao.get("reference"))
            field("Secteur", ao.get("secteur"))
            field("Mot clé", ao.get("mot_cle"))
            field("Tags", ao.get("tags"))
            field("Raison", ao.get("raison"))

        lien = ao.get("lien")
        if lien:
            ui.separator().classes("my-3")
            ui.link("Ouvrir l'appel d'offre", str(lien)).classes("ao-link")

    return dlg


def build_ao_card(ao: Dict[str, Any], on_details_open=None, on_details_close=None) -> None:
    card = (
        ui.card()
        .classes("w-full ao-card")
        .props("flat bordered")
        .style("border-radius: 12px;")
    )

    with card:
        with ui.row().classes("w-full items-start justify-between gap-3 flex-nowrap"):
            ui.label(_chip(ao.get("titre"), "(sans titre)")).classes("ao-title flex-1 min-w-0")
            score_chip = ui.chip(f"score: {_chip(ao.get('score_ia'))}").props("outline")
            score_chip.classes("text-sm shrink-0")
            score_chip.style(_score_style(ao.get("score_ia")))

        sub = " · ".join(
            x
            for x in [
                _chip(ao.get("acheteur"), ""),
                _chip(ao.get("lieu"), ""),
                ("clôture: " + _chip(ao.get("date_cloture"), "")) if ao.get("date_cloture") else "",
            ]
            if x
        )
        if sub:
            ui.label(sub).classes("ao-meta text-sm")

        with ui.row().classes("w-full gap-2"):
            for badge in [ao.get("type_marche"), ao.get("secteur"), ao.get("tags")]:
                if badge:
                    ui.chip(str(badge)[:40]).props("outline").classes("text-xs ao-chip")

        with ui.row().classes("w-full items-center justify-end gap-2"):
            if ao.get("lien"):
                ui.link("Ouvrir", str(ao["lien"])).classes("ao-link")

            def open_details(_e=None, _ao=ao):
                d = make_ao_dialog(_ao, on_open=on_details_open, on_close=on_details_close)
                d.open()

            ui.button("Détails", on_click=open_details).props("flat").classes("ao-details-btn")


def render_empty_detail_panel() -> None:
    with ui.element("div").classes("argos-panel argos-empty-detail"):
        with ui.column().classes("items-center gap-2 p-6"):
            ui.icon("article").classes("text-gray-400 text-4xl")
            ui.label("Sélectionne une recherche").classes("argos-section-title")
            ui.label("Les détails et les appels d'offres s'afficheront ici.").classes("argos-muted text-sm")


def render_recherche_detail_panel(
    recherche_id: int,
    *,
    show_non_pertinent: bool = False,
    embedded: bool = False,
    on_close=None,
    on_toggle_non_pertinent=None,
) -> None:
    job = get_job(recherche_id)
    if not job:
        with ui.element("div").classes("argos-panel"):
            with ui.column().classes("w-full argos-panel-body gap-2"):
                ui.label("Recherche introuvable.").classes("text-red-600")
        return

    rid = int(job["id"])
    prompt_initial = _chip(job.get("prompt_initial"), "Prompt initial non stocké pour cet historique.")
    requete = _chip(job.get("requete"), "")
    params = _chip(job.get("params"), "")
    keywords_and_params = "\n\n".join(part for part in [f"Mots-clés\n{requete}" if requete else "", f"Paramètres\n{params}" if params else ""] if part)
    details_open = False
    score_desc = True

    with ui.element("div").classes("argos-panel"):
        with ui.row().classes("w-full argos-panel-header items-start justify-between gap-3"):
            with ui.column().classes("gap-1 min-w-0"):
                title = f"Recherche #{rid}"
                if show_non_pertinent:
                    title += " · non pertinents"
                ui.label(title).classes("argos-section-title")
                ui.label(f"{_source_label(job.get('source'))} · {_chip(job.get('date_lancement'))}").classes("argos-muted text-sm")
            with ui.row().classes("items-center gap-1 shrink-0"):
                _render_status_badges(job)
                if on_close:
                    ui.button(icon="close", on_click=lambda _e=None: on_close()).props("flat round dense")

        with ui.column().classes("w-full argos-panel-body gap-3"):
            with ui.element("div").classes("ao-soft-section"):
                ui.label("Prompt initial").classes("text-sm font-semibold")
                ui.label(prompt_initial).classes("text-sm whitespace-pre-line")

            with ui.element("div").classes("ao-soft-section"):
                ui.label("Mots-clés et paramètres").classes("text-sm font-semibold")
                ui.label(keywords_and_params or "Aucun mot-clé ou paramètre stocké.").classes("text-sm whitespace-pre-line")

            ui.label(
                f"{_chip(job.get('nb_trouves'), '0')} trouvés · {_chip(job.get('nb_insere'), '0')} insérés"
            ).classes("argos-muted text-sm")

    if not show_non_pertinent and _job_has_warning(job):
        warning_blob = (job.get("warnings_json") or "").strip()
        limited_searches: List[Dict[str, Any]] = []
        warning_message = (
            "Certaines recherches sont trop larges. Tous les avis disponibles ne sont peut-être pas affichés."
        )
        if warning_blob:
            try:
                parsed_warning = json.loads(warning_blob)
                if isinstance(parsed_warning, dict):
                    warning_message = (parsed_warning.get("message") or warning_message).strip()
                    if isinstance(parsed_warning.get("limited_searches"), list):
                        limited_searches = [
                            item for item in parsed_warning["limited_searches"] if isinstance(item, dict)
                        ]
            except Exception:
                limited_searches = []

        with ui.element("div").classes("argos-panel bg-yellow-50 border border-yellow-200"):
            with ui.column().classes("w-full argos-panel-body gap-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("warning").classes("text-yellow-700")
                    ui.label("Vérification recommandée").classes("text-yellow-900 font-semibold")
                ui.label(warning_message).classes("text-yellow-900 text-sm")
                if limited_searches:
                    with ui.column().classes("gap-1 mt-1"):
                        for info in limited_searches:
                            recherche = (info.get("recherche") or "").strip() or ", ".join(info.get("mots", []))
                            nb_listees = info.get("nb_offres_listees") or info.get("nb_offres_lues") or info.get("nb_inserts") or "?"
                            ui.label(f"{recherche} · {nb_listees} avis lus").classes("text-yellow-900 text-sm")

    with ui.element("div").classes("argos-panel"):
        with ui.row().classes("w-full argos-panel-header items-center justify-between"):
            titre_aos = "AOs non pertinents" if show_non_pertinent else "Appels d'offres"
            ui.label(titre_aos).classes("argos-section-title")
            with ui.row().classes("items-center gap-1"):
                sort_btn = None
                if not show_non_pertinent:
                    sort_btn = ui.button(icon="keyboard_arrow_down").props("flat round dense")

                toggle_label = "AOs pertinents" if show_non_pertinent else "AOs non pertinents"
                if embedded and on_toggle_non_pertinent:
                    ui.button(toggle_label, on_click=lambda _e=None: on_toggle_non_pertinent(not show_non_pertinent)).props("flat dense")
                else:
                    target = f"/recherche/{rid}" if show_non_pertinent else f"/recherche/{rid}/non-pertinent"
                    ui.button(toggle_label, on_click=lambda _e=None, _target=target: ui.navigate.to(_target)).props("flat dense")

                refresh_btn = ui.button(icon="refresh").props("flat round dense")

        with ui.column().classes("w-full argos-panel-body gap-2"):
            aos_container = ui.column().classes("w-full gap-2")

    def on_details_open():
        nonlocal details_open
        details_open = True

    def on_details_close():
        nonlocal details_open
        details_open = False
        refresh_aos()

    def refresh_aos() -> None:
        if details_open:
            return
        aos = list_aos_np(rid) if show_non_pertinent else list_aos_p(rid, score_desc=score_desc)
        aos_container.clear()
        with aos_container:
            if not aos:
                ui.label("Aucun AO pour cette recherche.").classes("text-gray-500")
                return
            for ao in aos:
                build_ao_card(ao, on_details_open=on_details_open, on_details_close=on_details_close)

    def toggle_sort() -> None:
        nonlocal score_desc
        score_desc = not score_desc
        if sort_btn is not None:
            sort_btn.props(add=f"icon={'keyboard_arrow_down' if score_desc else 'keyboard_arrow_up'}")
            sort_btn.update()
        refresh_aos()

    refresh_btn.on("click", lambda _e=None: refresh_aos())
    if not show_non_pertinent and sort_btn is not None:
        sort_btn.on("click", lambda _e=None: toggle_sort())
    refresh_aos()


###############################################################################
# Wizard mots-clés (dialog overlay)
###############################################################################


def _parse_groups_input(raw: str) -> List[List[str]]:
    # Support ',' ou ';' pour séparer les groupes
    groups = re.split(r"[;,]", raw)
    groups = [g.strip() for g in groups if g.strip()]
    out: List[List[str]] = []
    for g in groups:
        words = [w for w in g.split() if w]
        if words:
            out.append(words)
    return out

def _normalize_keyword_groups(raw_groups: Sequence[Any]) -> List[List[str]]:
    """Garantit un format homogène: List[List[str]] pour l'affichage et le pipeline."""
    normalized: List[List[str]] = []
    for group in raw_groups:
        if isinstance(group, str):
            words = [w for w in group.strip().split() if w]
        elif isinstance(group, Sequence):
            words = [str(w).strip() for w in group if str(w).strip()]
        else:
            continue

        if words:
            normalized.append(words)

    return normalized


class KeywordsWizard:
    def __init__(
        self,
        *,
        search_id: int,
        prompt_client: str,
        date_pub_min: str,
        date_pub_max: str,
        selected_sites: Sequence[str],
        source: str,
    ):
        self.search_id = search_id
        self.prompt_client = prompt_client
        self.source = source
        self.selected_sites = list(selected_sites)
        self.meta_prompt: Optional[str] = None
        self.date_pub_min = date_pub_min
        self.date_pub_max = date_pub_max
        self._loading_row = None
        self.mots_recherche: List[List[str]] = []

        self.dlg = ui.dialog()
        self._status_label = None
        self._progress_row = None
        self._keywords_container = None
        self._add_input = None
        self._poll_timer = None
        self._pipeline_task: Optional[asyncio.Task] = None
        self._closed: bool = False
        self._job_state = None  # tu l'utilises plus tard, autant l'init

        self._build_initial_ui()

    def open(self) -> None:
        self.dlg.open()

    def close(self) -> None:
        self._closed = True

        # Stop timer UI
        try:
            if self._poll_timer is not None:
                self._poll_timer.active = False
        except Exception:
            pass

        # Cancel pipeline task si elle tourne encore
        try:
            if self._pipeline_task is not None and not self._pipeline_task.done():
                self._pipeline_task.cancel()
        except Exception:
            pass

        self.dlg.close()

    def _build_initial_ui(self) -> None:
        with self.dlg, ui.card().classes("w-[min(860px,95vw)] argos-panel"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Nouvelle recherche").classes("text-xl font-bold")
                ui.button(icon="close", on_click=self.close).props("flat round")

            ui.separator().classes("my-2")

            self._status_label = ui.label("Génération des mots-clés…").classes("text-gray-700")
            
            self._loading_row = ui.row().classes("w-full items-center gap-3")
            with self._loading_row:
                ui.spinner(size="lg")
                ui.label("Le modèle réfléchit... Patience.").classes("text-gray-500")

            ui.separator().classes("my-3")
            self._keywords_container = ui.column().classes("w-full gap-2")

            self._progress_row = ui.row().classes("w-full items-center justify-between")

    def _render_keywords_editor(self) -> None:
        assert self._keywords_container is not None
        self._keywords_container.clear()

        with self._keywords_container:
            ui.label("Mots-clés (groupes)").classes("text-gray-600")

            if not self.mots_recherche:
                ui.label("(Vide)").classes("text-gray-500")
            else:
                for idx, group in enumerate(self.mots_recherche):
                    with ui.card().classes("w-full").props("flat bordered").style("border-radius: 12px;"):
                        with ui.row().classes("w-full items-center justify-between"):
                            with ui.row().classes("gap-2"):
                                for w in group:
                                    ui.chip(w).props("outline").classes("text-xs")
                            ui.button(
                                icon="delete",
                                on_click=lambda _e=None, i=idx: self._delete_group(i),
                            ).props("flat round").classes("text-red-600")

            ui.separator().classes("my-2")

            self._add_input = (
                ui.input(
                    label="Ajouter des groupes",
                    placeholder="Ex: moteurs electriques, vibration capteur; analyse numerique",
                )
                .props("outlined clearable")
                .classes("w-full")
            )
            with ui.row().classes("w-full items-center justify-between"):
                ui.button("Ajouter", on_click=self._add_groups).props("unelevated")
                ui.button("Valider et lancer", on_click=self._validate_and_launch).props("unelevated")

    def _delete_group(self, idx: int) -> None:
        if 0 <= idx < len(self.mots_recherche):
            self.mots_recherche.pop(idx)
            self._render_keywords_editor()

    def _add_groups(self) -> None:
        if not self._add_input:
            return
        raw = (self._add_input.value or "").strip()
        if not raw:
            ui.notify("Rien à ajouter.", type="warning")
            return
        groups = _parse_groups_input(raw)
        if not groups:
            ui.notify("Aucun groupe valide détecté.", type="warning")
            return
        self.mots_recherche.extend(groups)
        self._add_input.value = ""
        self._render_keywords_editor()
        

    async def start_generation(self) -> None:
        """Lance la génération mots-clés et bascule l'overlay en mode édition."""
        try:
            result: KeywordsResult = await generate_keywords(
                search_id=self.search_id,
                prompt_client=self.prompt_client,
            )
            self.mots_recherche = _normalize_keyword_groups(result.mots_recherche)
            self.meta_prompt = result.meta_prompt
            if self._loading_row is not None:
                self._loading_row.clear()
                with self._loading_row:
                    ui.icon("check_circle").classes("text-green-600")
                    ui.label("Mots-clés générés.").classes("text-gray-500")
            

            # Bascule UI
            if self._status_label is not None:
                self._status_label.set_text("Ajuste les mots-clés puis lance la recherche.")
            self._render_keywords_editor()

        except Exception as e:
            db_repository.update_recherche_job(self.search_id, statut="erreur_generation")
            ui.notify(f"Erreur génération mots-clés: {e}", type="negative")
            self.close()

    def _validate_and_launch(self) -> None:
        if not self.meta_prompt:
            ui.notify("meta_prompt manquant (génération pas terminée).", type="warning")
            return
        if not self.mots_recherche:
            ui.notify("Liste de mots-clés vide. Ce serait un peu court.", type="warning")
            return

        # Met à jour requête immédiatement
        requete_str = mots_recherche_to_requete(self.mots_recherche)
        db_repository.update_recherche_job(self.search_id, requete=requete_str)

        # UI: mode "running" (IMPORTANT: on se met dans le contexte du container)
        if self._keywords_container is not None:
            with self._keywords_container:
                self._keywords_container.clear()
                ui.label("Recherche lancée").classes("text-gray-600")
                ui.label("Scraping + tri IA en cours…").classes("text-gray-500")
                ui.spinner(size="lg")
                self._job_state = ui.label("").classes("text-gray-700")

                # IMPORTANT: créer le timer ici, pas dans le slot du bouton
                self._poll_timer = ui.timer(1.5, self._poll_job_state)

        # Background task
        self._pipeline_task = asyncio.create_task(self._run_pipeline_bg())

    async def _run_pipeline_bg(self) -> None:
        try:
            await run_full_pipeline(
                search_id=self.search_id,
                mots_recherche=self.mots_recherche,
                meta_prompt=self.meta_prompt or "",
                date_pub_min=self.date_pub_min,
                date_pub_max=self.date_pub_max,
                selected_sites=self.selected_sites,
            )

        except asyncio.CancelledError:
            # popup fermée => on arrête proprement
            return

        except Exception as e:
            # log serveur (pas d'UI ici)
            print(f"[PIPELINE] Erreur: {e!r}")
            # on marque le job en erreur pour que le poll UI l'affiche
            try:
                db_repository.update_recherche_job(self.search_id, statut="erreur_pipeline")
            except Exception:
                pass
            return

    def _poll_job_state(self) -> None:
        if self._closed:
            return

        job = get_job(self.search_id)
        if not job:
            return

        statut = (job.get("statut") or "").strip().lower()
        label, _cls = _status_badge(job.get("statut"))

        txt = (
            f"Statut: {label} · trouvés: {_chip(job.get('nb_trouves'))} · "
            f"insérés: {_chip(job.get('nb_insere'))}"
        )
        try:
            if self._job_state is not None:
                self._job_state.set_text(txt)
        except Exception:
            pass

        # Fin de job => on stop le timer et on clôture côté UI (SAFE)
        if statut in {"termine", "erreur_scraper", "erreur_generation", "erreur_pipeline"}:
            try:
                if self._poll_timer is not None:
                    self._poll_timer.active = False
            except Exception:
                pass

            if statut == "termine":
                ui.notify("Terminé.", type="positive")
            else:
                ui.notify(f"Job terminé avec erreur: {label}", type="negative")

            self.close()
            ui.navigate.to("/")

###############################################################################
# Pages
###############################################################################


@ui.page("/")
def page_home() -> None:
    db_repository.initialize_database()
    ui.page_title("Recherches")

    source_options = get_available_scrapers()
    history_page = 1
    selected_job_ids: set[int] = set()
    selected_detail_id: Optional[int] = None
    detail_show_non_pertinent = False

    with ui.element("div").classes("argos-page"):
        with ui.element("div").classes("argos-shell home-split"):
            with ui.row().classes("w-full argos-topbar items-center justify-between gap-4"):
                with ui.column().classes("gap-1"):
                    ui.label("Console Appels d'Offres").classes("argos-title")
                    ui.label(f"Recherche multi-sources via {_source_summary(source_options)}").classes("argos-subtitle")
                ui.chip(_source_summary(source_options)).props("outline").classes("bg-blue-50 text-blue-700")

            ui.space().classes("argos-left-gap")

            with ui.element("div").classes("argos-panel"):
                with ui.column().classes("w-full gap-0"):
                    with ui.row().classes("w-full argos-panel-header items-center justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label("Lancer une recherche").classes("argos-section-title")
                            ui.label("Décris ton besoin, choisis la période et les sources à interroger.").classes("argos-muted text-sm")

                    with ui.column().classes("w-full argos-panel-body gap-4"):
                        today = date.today()
                        default_pub_min = today - timedelta(days=7)
                        default_pub_max = today

                        prompt_input = (
                            ui.input(
                                label="Prompt",
                                placeholder="Ex: contrôle non destructif, instrumentation, maintenance prédictive...",
                            )
                            .props("outlined clearable")
                            .classes("w-full")
                        )

                        with ui.row().classes("w-full items-end justify-between gap-4"):
                            with ui.row().classes("items-end gap-3"):
                                pub_min_input = ui.input(
                                    label="Publication min",
                                    value=default_pub_min.isoformat(),
                                ).props("outlined readonly dense").classes("w-44")

                                pub_min_menu = ui.menu().props("no-parent-event")
                                with pub_min_menu:
                                    pub_min_picker = ui.date(value=default_pub_min.isoformat()).props('first-day-of-week="1"')
                                    pub_min_picker.on("update:model-value", lambda e: pub_min_menu.close())
                                    pub_min_picker.bind_value(pub_min_input)

                                pub_min_input.on("click", lambda e: pub_min_menu.open())

                                pub_max_input = ui.input(
                                    label="Publication max",
                                    value=default_pub_max.isoformat(),
                                ).props("outlined readonly dense").classes("w-44")

                                pub_max_menu = ui.menu().props("no-parent-event")
                                with pub_max_menu:
                                    pub_max_picker = ui.date(value=default_pub_max.isoformat()).props('first-day-of-week="1"')
                                    pub_max_picker.on("update:model-value", lambda e: pub_max_menu.close())
                                    pub_max_picker.bind_value(pub_max_input)

                                pub_max_input.on("click", lambda e: pub_max_menu.open())

                                ui.button(
                                    "7 derniers jours",
                                    on_click=lambda: (
                                        pub_min_input.set_value(default_pub_min.isoformat()),
                                        pub_max_input.set_value(default_pub_max.isoformat()),
                                    ),
                                ).props("flat dense").classes("text-xs")

                            launch_btn = ui.button("Rechercher", icon="search").props("unelevated").classes("px-6")
                            saved_prompts_btn = ui.button(icon="bookmark").props('flat round dense aria-label="Prompts sauvegardés" data-testid="saved-prompts-button"')
                            with saved_prompts_btn:
                                ui.tooltip("Prompts sauvegardés")

                        with ui.column().classes("w-full gap-2"):
                            ui.label("Sources").classes("argos-section-title")
                            source_checkboxes: Dict[str, Any] = {}
                            with ui.row().classes("w-full gap-3"):
                                if source_options:
                                    for option in source_options:
                                        code = option["code"]
                                        with ui.element("div").classes("argos-source-tile"):
                                            source_checkboxes[code] = ui.checkbox(option["label"], value=True).props("dense")
                                else:
                                    ui.label("Aucune source active dans le registre des scrapers.").classes("text-red-600 text-sm")

            ui.space().classes("argos-left-gap")

            with ui.element("div").classes("argos-panel"):
                with ui.row().classes("w-full argos-panel-header items-center justify-between gap-3"):
                    with ui.column().classes("gap-1"):
                        ui.label("Historique").classes("argos-section-title")
                        history_meta_label = ui.label("").classes("argos-muted text-sm")
                    with ui.row().classes("items-center gap-2"):
                        selection_label = ui.label("0 sélection").classes("argos-muted text-sm")
                        bulk_delete_btn = ui.button("Supprimer", icon="delete").props("flat dense").classes("text-red-600")

                with ui.column().classes("w-full argos-panel-body gap-3"):
                    list_container = ui.column().classes("w-full gap-2")
                    pager_container = ui.row().classes("w-full items-center justify-between")

            with ui.element("div").classes("argos-right-pane argos-detail-home"):
                detail_container = ui.column().classes("w-full gap-4")

    bulk_delete_btn.disable()

    def _render_selected_detail() -> None:
        detail_container.clear()
        with detail_container:
            if selected_detail_id is None:
                render_empty_detail_panel()
            else:
                render_recherche_detail_panel(
                    selected_detail_id,
                    show_non_pertinent=detail_show_non_pertinent,
                    embedded=True,
                    on_close=_close_detail,
                    on_toggle_non_pertinent=_toggle_detail_mode,
                )

    def _open_job_detail(job_id: int) -> None:
        nonlocal selected_detail_id, detail_show_non_pertinent
        selected_detail_id = int(job_id)
        detail_show_non_pertinent = False
        refresh()
        _render_selected_detail()

    def _close_detail() -> None:
        nonlocal selected_detail_id, detail_show_non_pertinent
        selected_detail_id = None
        detail_show_non_pertinent = False
        refresh()
        _render_selected_detail()

    def _toggle_detail_mode(show_non_pertinent: bool) -> None:
        nonlocal detail_show_non_pertinent
        detail_show_non_pertinent = bool(show_non_pertinent)
        _render_selected_detail()

    def _update_selection_controls() -> None:
        count = len(selected_job_ids)
        selection_label.set_text(f"{count} sélection" + ("s" if count > 1 else ""))
        if count:
            bulk_delete_btn.enable()
        else:
            bulk_delete_btn.disable()

    def _max_history_page(total: int) -> int:
        return max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)

    def _set_history_page(page: int) -> None:
        nonlocal history_page
        history_page = max(1, page)
        refresh()

    def _on_select_job(job_id: int, checked: bool) -> None:
        if checked:
            selected_job_ids.add(job_id)
        else:
            selected_job_ids.discard(job_id)
        _update_selection_controls()

    def _confirm_delete_jobs(job_ids: Sequence[int]) -> None:
        ids = sorted({int(job_id) for job_id in job_ids})
        if not ids:
            ui.notify("Aucune recherche sélectionnée.", type="warning")
            return

        active_ids = [
            job_id
            for job_id in ids
            if (job := get_job(job_id)) is not None and _job_is_active(job)
        ]
        if active_ids:
            ui.notify(
                f"Impossible de supprimer une recherche en cours: {', '.join(map(str, active_ids))}",
                type="warning",
            )
            return

        dlg = ui.dialog()
        with dlg, ui.card().classes("w-[min(520px,95vw)] argos-panel"):
            ui.label("Supprimer l'historique").classes("text-lg font-bold")
            ui.label(
                f"Supprimer {len(ids)} recherche" + ("s" if len(ids) > 1 else "") + " et ses données associées ?"
            ).classes("argos-muted")

            with ui.row().classes("w-full items-center justify-end gap-2"):
                ui.button("Annuler", on_click=dlg.close).props("flat")

                def delete_confirmed() -> None:
                    nonlocal selected_detail_id, detail_show_non_pertinent
                    deleted = db_repository.delete_recherche_jobs(ids)
                    selected_job_ids.difference_update(ids)
                    if selected_detail_id in ids:
                        selected_detail_id = None
                        detail_show_non_pertinent = False
                    dlg.close()
                    ui.notify(f"{deleted} recherche" + ("s" if deleted > 1 else "") + " supprimée" + ("s" if deleted > 1 else "") + ".")
                    refresh()
                    _render_selected_detail()

                ui.button("Supprimer", icon="delete", on_click=delete_confirmed).props("unelevated").classes("bg-red-600 text-white")

        dlg.open()

    bulk_delete_btn.on("click", lambda _e=None: _confirm_delete_jobs(sorted(selected_job_ids)))

    def refresh() -> None:
        nonlocal history_page
        total = count_jobs()
        max_page = _max_history_page(total)
        if history_page > max_page:
            history_page = max_page

        offset = (history_page - 1) * HISTORY_PAGE_SIZE
        jobs = list_jobs(limit=HISTORY_PAGE_SIZE, offset=offset)
        history_meta_label.set_text(f"{total} recherche" + ("s" if total > 1 else ""))

        list_container.clear()
        with list_container:
            if not jobs:
                ui.label("Aucune recherche pour le moment.").classes("argos-muted")
            else:
                for j in jobs:
                    build_job_card(
                        j,
                        selected=int(j["id"]) in selected_job_ids,
                        active=selected_detail_id == int(j["id"]),
                        on_open=_open_job_detail,
                        on_selection_change=_on_select_job,
                        on_delete=_confirm_delete_jobs,
                    )

        pager_container.clear()
        with pager_container:
            if total:
                start = offset + 1
                end = min(total, offset + len(jobs))
                ui.label(f"{start}-{end} sur {total}").classes("argos-muted text-sm")

                if total > HISTORY_PAGE_SIZE:
                    with ui.row().classes("items-center gap-2"):
                        prev_btn = ui.button(icon="chevron_left", on_click=lambda _e=None: _set_history_page(history_page - 1)).props("flat round dense")
                        if history_page <= 1:
                            prev_btn.disable()

                        ui.label(f"Page {history_page}/{max_page}").classes("argos-muted text-sm")

                        next_btn = ui.button(icon="chevron_right", on_click=lambda _e=None: _set_history_page(history_page + 1)).props("flat round dense")
                        if history_page >= max_page:
                            next_btn.disable()

        _update_selection_controls()

    async def launch_prompt(prompt: str, *, clear_prompt_input: bool = False) -> None:
        prompt = (prompt or "").strip()
        date_pub_min = pub_min_input.value
        date_pub_max = pub_max_input.value
        selected_sites = [code for code, checkbox in source_checkboxes.items() if checkbox.value]
        if not prompt:
            ui.notify("Prompt vide.", type="warning")
            return
        if not selected_sites:
            ui.notify("Sélectionne au moins une source.", type="warning")
            return

        # Créer job
        source = ",".join(selected_sites)
        try:
            search_id = create_job_for_prompt(source=source, statut="en_cours", prompt_initial=prompt)
        except Exception as e:
            ui.notify(f"Erreur création job: {e}", type="negative")
            return

        # Wizard overlay
        wiz = KeywordsWizard(
            search_id=search_id,
            prompt_client=prompt,
            date_pub_min=date_pub_min,
            date_pub_max=date_pub_max,
            selected_sites=selected_sites,
            source=source,
        )
        wiz.open()
        asyncio.create_task(wiz.start_generation())

        # UX: reset input + refresh
        if clear_prompt_input:
            prompt_input.value = ""
        refresh()

    async def on_launch(_e=None) -> None:
        await launch_prompt(prompt_input.value or "", clear_prompt_input=True)

    prompts_dlg = ui.dialog()
    with prompts_dlg, ui.card().classes("saved-prompts-dialog argos-panel"):
        with ui.row().classes("w-full items-start justify-between gap-4"):
            with ui.column().classes("gap-1"):
                ui.label("Prompts sauvegardés").classes("text-xl font-bold")
                saved_prompts_meta_label = ui.label("").classes("argos-muted text-sm")
            ui.button(icon="close", on_click=prompts_dlg.close).props("flat round")

        ui.separator().classes("my-3")

        with ui.element("div").classes("saved-prompts-grid saved-prompts-body w-full"):
            with ui.element("div").classes("ao-soft-section"):
                with ui.column().classes("w-full gap-3"):
                    ui.label("Ajouter un prompt").classes("argos-section-title")
                    saved_prompt_input = (
                        ui.textarea(
                            label="Prompt",
                            placeholder="Colle ou rédige un prompt réutilisable...",
                        )
                        .props("outlined autogrow")
                        .classes("w-full")
                    )
                    save_prompt_btn = ui.button("Sauvegarder", icon="save").props("unelevated").classes("w-full")

            with ui.column().classes("w-full gap-2 saved-prompts-list"):
                saved_prompts_container = ui.column().classes("w-full gap-2")

    def refresh_saved_prompts() -> None:
        prompts = list(db_repository.list_saved_prompts(limit=200))
        saved_prompts_meta_label.set_text(f"{len(prompts)} prompt" + ("s" if len(prompts) > 1 else ""))
        saved_prompts_container.clear()
        with saved_prompts_container:
            if not prompts:
                with ui.element("div").classes("ao-soft-section"):
                    ui.label("Aucun prompt sauvegardé.").classes("argos-muted text-sm")
                return

            for item in prompts:
                prompt = str(item.get("prompt") or "").strip()
                updated_at = _fmt_dt(item.get("updated_at"))

                async def launch_saved_prompt(_e=None, saved_prompt=prompt) -> None:
                    prompts_dlg.close()
                    await launch_prompt(saved_prompt)

                with ui.element("button").classes("saved-prompt-card w-full").on("click", launch_saved_prompt):
                    ui.label(prompt).classes("saved-prompt-text")
                    if updated_at:
                        ui.label(f"Mis à jour le {updated_at}").classes("argos-muted text-xs mt-2")

    def open_saved_prompts_dialog(_e=None) -> None:
        current_prompt = (prompt_input.value or "").strip()
        if current_prompt:
            saved_prompt_input.value = current_prompt
        refresh_saved_prompts()
        prompts_dlg.open()

    def save_prompt_from_dialog(_e=None) -> None:
        prompt = (saved_prompt_input.value or "").strip()
        if not prompt:
            ui.notify("Prompt vide.", type="warning")
            return
        try:
            db_repository.save_prompt(prompt)
        except Exception as e:
            ui.notify(f"Erreur sauvegarde prompt: {e}", type="negative")
            return
        saved_prompt_input.value = ""
        ui.notify("Prompt sauvegardé.", type="positive")
        refresh_saved_prompts()

    save_prompt_btn.on("click", save_prompt_from_dialog)
    saved_prompts_btn.on("click", open_saved_prompts_dialog)
    launch_btn.on("click", on_launch)
    prompt_input.on("keydown.enter", on_launch)

    refresh()
    _render_selected_detail()
    # auto refresh léger (statuts)
    t = ui.timer(3.0, refresh)
    client = ui.context.client
    client.on_disconnect(lambda: setattr(t, "active", False))


@ui.page("/recherche/{recherche_id}")
def page_recherche(recherche_id: str) -> None:
    _render_recherche_page(recherche_id, show_non_pertinent=False)


@ui.page("/recherche/{recherche_id}/non-pertinent")
def page_recherche_non_pertinent(recherche_id: str) -> None:
    _render_recherche_page(recherche_id, show_non_pertinent=True)


def _render_recherche_page(recherche_id: str, *, show_non_pertinent: bool) -> None:
    db_repository.initialize_database()

    try:
        rid = int(recherche_id)
    except ValueError:
        ui.label("ID recherche invalide.").classes("text-red-600")
        return

    job = get_job(rid)
    if not job:
        ui.label("Recherche introuvable.").classes("text-red-600")
        return

    suffix = " · non pertinents" if show_non_pertinent else ""
    ui.page_title(f"AO · recherche {rid}{suffix}")

    with ui.element("div").classes("argos-page"):
      with ui.element("div").classes("argos-detail-shell"):
        with ui.row().classes("w-full argos-topbar items-center justify-between gap-4"):
            back_target = f"/recherche/{rid}" if show_non_pertinent else "/"
            with ui.row().classes("items-center gap-3"):
                ui.button("Retour", icon="arrow_back", on_click=lambda _target=back_target: ui.navigate.to(_target)).props("flat")
                with ui.column().classes("gap-1"):
                    page_title = f"Recherche #{rid} · AOs non pertinents" if show_non_pertinent else f"Recherche #{rid}"
                    ui.label(page_title).classes("argos-title")
                    ui.label(f"{_source_label(job.get('source'))} · {_chip(job.get('date_lancement'))}").classes("argos-subtitle")
            with ui.row().classes("items-center gap-1"):
                _render_status_badges(job)

        ui.space().classes("h-5")

        with ui.element("div").classes("argos-panel"):
            with ui.row().classes("w-full argos-panel-header items-center justify-between"):
                ui.label("Détails").classes("argos-section-title")

            with ui.column().classes("w-full argos-panel-body gap-3"):
                with ui.element("div").classes("ao-soft-section"):
                    ui.label("Prompt initial").classes("text-sm font-semibold")
                    ui.label(_chip(job.get("prompt_initial"), "Prompt initial non stocké pour cet historique.")).classes("text-sm whitespace-pre-line")

                requete = _chip(job.get("requete"), "")
                params = _chip(job.get("params"), "")
                keywords_and_params = "\n\n".join(
                    part
                    for part in [
                        f"Mots-clés\n{requete}" if requete else "",
                        f"Paramètres\n{params}" if params else "",
                    ]
                    if part
                )
                with ui.element("div").classes("ao-soft-section"):
                    ui.label("Mots-clés et paramètres").classes("text-sm font-semibold")
                    ui.label(keywords_and_params or "Aucun mot-clé ou paramètre stocké.").classes("text-sm whitespace-pre-line")

                ui.label(
                    f"{_chip(job.get('nb_trouves'), '0')} trouvés · {_chip(job.get('nb_insere'), '0')} insérés"
                ).classes("argos-muted text-sm")


        ui.space().classes("h-4")

        if not show_non_pertinent:
            warning_blob = (job.get("warnings_json") or "").strip()
            limited_searches: List[Dict[str, Any]] = []
            warning_message = (
                "Certaines recherches sont trop larges. Tous les avis disponibles ne sont peut-être pas affichés."
            )
            if warning_blob:
                try:
                    parsed_warning = json.loads(warning_blob)
                    warning_message = (parsed_warning.get("message") or warning_message).strip()
                    if isinstance(parsed_warning.get("limited_searches"), list):
                        limited_searches = [
                            item for item in parsed_warning["limited_searches"] if isinstance(item, dict)
                        ]
                except Exception:
                    limited_searches = []

            if limited_searches:
                with ui.element("div").classes("argos-panel bg-yellow-50 border border-yellow-200"):
                    with ui.column().classes("w-full argos-panel-body gap-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("warning").classes("text-yellow-700")
                            ui.label("Vérification recommandée").classes("text-yellow-900 font-semibold")
                        ui.label(warning_message).classes("text-yellow-900 text-sm")
                        with ui.column().classes("gap-1 mt-1"):
                            for info in limited_searches:
                                recherche = (info.get("recherche") or "").strip() or ", ".join(info.get("mots", []))
                                nb_listees = info.get("nb_offres_listees") or info.get("nb_offres_lues") or info.get("nb_inserts") or "?"
                                ui.label(f"{recherche} · {nb_listees} avis lus").classes("text-yellow-900 text-sm")

                ui.space().classes("h-4")

        with ui.element("div").classes("argos-panel"):
            with ui.row().classes("w-full argos-panel-header items-center justify-between"):
                titre_aos = "AOs non pertinents" if show_non_pertinent else "Appels d'offres"
                ui.label(titre_aos).classes("argos-section-title")
                with ui.row().classes("items-center gap-1"):
                    sort_btn = None
                    if not show_non_pertinent:
                        sort_btn = ui.button(icon="keyboard_arrow_down").props("flat round")

                    with ui.button(icon="more_vert").props("flat round"):
                        with ui.menu().props("anchor=bottom right self=top right"):
                            if show_non_pertinent:
                                ui.menu_item("Afficher les AOs pertinents", on_click=lambda: ui.navigate.to(f"/recherche/{rid}"))
                            else:
                                ui.menu_item("Afficher les AOs non pertinents", on_click=lambda: ui.navigate.to(f"/recherche/{rid}/non-pertinent"))

                    refresh_btn = ui.button(icon="refresh").props("flat round")

            with ui.column().classes("w-full argos-panel-body gap-2"):
                aos_container = ui.column().classes("w-full gap-2")
    
    details_open = False
    refresh_timer = None
    score_desc = True
        
    def on_details_open():
        nonlocal details_open, refresh_timer
        details_open = True
        if refresh_timer is not None:
            refresh_timer.active = False

    def on_details_close():
        nonlocal details_open, refresh_timer
        details_open = False
        if refresh_timer is not None:
            refresh_timer.active = True
            refresh_aos()

    def refresh_aos() -> None:
        if details_open:
            return
        
        aos = list_aos_np(rid) if show_non_pertinent else list_aos_p(rid, score_desc=score_desc)
        aos_container.clear()
        with aos_container:
            if not aos:
                ui.label("Aucun AO pour cette recherche.").classes("text-gray-500")
                return
            for ao in aos:
                build_ao_card(ao, on_details_open=on_details_open, on_details_close=on_details_close)

    def toggle_sort() -> None:
        nonlocal score_desc
        score_desc = not score_desc
        if sort_btn is not None:
            sort_btn.props(add=f"icon={'keyboard_arrow_down' if score_desc else 'keyboard_arrow_up'}")
            sort_btn.update()
        refresh_aos()

    refresh_btn.on("click", lambda _e=None: refresh_aos())
    if not show_non_pertinent and sort_btn is not None:
        sort_btn.on("click", lambda _e=None: toggle_sort())
    refresh_aos()
    refresh_timer = ui.timer(5.0, refresh_aos)
    
    client = ui.context.client
    client.on_disconnect(lambda: setattr(refresh_timer, "active", False))


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(reload=True)
