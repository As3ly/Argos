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
    mots_recherche_to_requete,
    run_full_pipeline,
)

PALETTE = {
    "blue": "#1057CC",
    "blue_dark": "#001A70",
    "blue_light": "#1089FF",
    "orange": "#FF861C",
    "orange_dark": "#E58115",
    "orange_light": "#FFB210",
    "green": "#8BD910",
    "green_dark": "#4F9E30",
    "green_light": "#C0E410",
}


def _score_style(score: Any) -> str:
    try:
        value = float(str(score).replace(",", "."))
    except (TypeError, ValueError):
        value = 0.0

    if value >= 0.85:
        fg, bg = PALETTE["green_dark"], "#F2FAE9"
    elif value >= 0.7:
        fg, bg = PALETTE["orange_dark"], "#FFF4E8"
    else:
        fg, bg = PALETTE["blue_dark"], "#EEF4FF"

    return f"border-color: {fg}; color: {fg}; background: {bg}; font-weight: 600;"


ui.add_head_html(
    f"""
    <style>
      .ao-card {{ border-radius: 14px; border: 1px solid #E8EEF7; background: #FFFFFF; transition: box-shadow .2s ease, border-color .2s ease; }}
      .ao-card:hover {{ box-shadow: 0 10px 26px rgba(0, 26, 112, 0.08); border-color: #D7E3F7; }}
      .ao-title {{ font-size: 1.04rem; font-weight: 600; color: {PALETTE["blue_dark"]}; line-height: 1.4; white-space: normal; overflow-wrap: anywhere; }}
      .ao-meta {{ color: #5E6A7D; }}
      .ao-chip {{ border-color: {PALETTE["blue_light"]}; color: {PALETTE["blue"]}; background: #F5FAFF; }}
      .ao-link {{ color: {PALETTE["blue"]}; font-weight: 600; }}
      .ao-link:hover {{ color: {PALETTE["blue_dark"]}; }}
      .ao-details-btn {{ color: {PALETTE["orange_dark"]}; font-weight: 600; }}
      .ao-details-btn:hover {{ color: {PALETTE["orange"]}; }}
      .ao-dialog {{ border-radius: 18px; border: 1px solid #E7EEF9; box-shadow: 0 24px 54px rgba(0, 26, 112, 0.15); }}
      .ao-dialog-title {{ font-size: 1.2rem; font-weight: 600; color: {PALETTE["blue_dark"]}; line-height: 1.4; }}
      .ao-field-key {{ color: #6B7485; font-weight: 500; }}
      .ao-field-value {{ color: #222E43; }}
      .ao-soft-section {{ background: #F8FAFF; border: 1px solid #ECF1FA; border-radius: 12px; padding: .75rem; }}
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


def list_jobs(limit: int = 200) -> List[Dict[str, Any]]:
    with closing(_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titre, requete, source, params, warnings_json, date_lancement, statut, nb_trouves, nb_insere
            FROM recherches_jobs
            ORDER BY date_lancement DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_job(search_id: int) -> Optional[Dict[str, Any]]:
    with closing(_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, titre, requete, source, params, warnings_json, date_lancement, statut, nb_trouves, nb_insere
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


def build_job_card(job: Dict[str, Any]) -> None:
    label, cls = _status_badge(job.get("statut"))
    rid = job["id"]
    titre_card = job.get("titre") or ""
    source = job.get("source") or ""
    dt = job.get("date_lancement")

    card = (
        ui.card()
        .classes("w-full cursor-pointer hover:shadow")
        .props("flat bordered")
        .style("border-radius: 12px;")
    )
    with card:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(titre_card).classes("text-base font-medium")
            ui.chip(label).classes(f"text-sm {cls}").props("outline")

        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"#{rid} · {source} · {_fmt_dt(dt)}").classes("text-gray-500 text-sm")
            ui.label(
                f"trouvés: {_chip(job.get('nb_trouves'))} · insérés: {_chip(job.get('nb_insere'))}"
            ).classes("text-gray-500 text-sm")

    card.on("click", lambda _e, _rid=rid: ui.navigate.to(f"/recherche/{_rid}"))


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
    def __init__(self, *, search_id: int, prompt_client: str, date_pub_min: str, date_pub_max: str,source: str = "francemarches"):
        self.search_id = search_id
        self.prompt_client = prompt_client
        self.source = source
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
        with self.dlg, ui.card().classes("w-[min(860px,95vw)]").style("border-radius: 16px;"):
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

    header = ui.row().classes("w-full items-center justify-between")

    with ui.column().classes("w-full items-center"):
        ui.space().classes("h-8")
        ui.label("Console Appels d'Offres").classes("text-2xl font-bold")

        with ui.card().classes("w-full max-w-4xl").style("border-radius: 16px;"):
            ui.label("Lancer une recherche").classes("text-gray-600")

            today = date.today()
            default_pub_min = today - timedelta(days=7)
            default_pub_max = today

            # --- Prompt (ligne 1)
            with ui.row().classes("w-full items-center gap-3"):
                prompt_input = (
                    ui.input(
                        label="Prompt",
                        placeholder="Décris ton besoin (le backend s'occupe du reste)",
                    )
                    .props("outlined clearable")
                    .classes("w-full")
                )

            # --- Dates + bouton (ligne 2) : dates à gauche, bouton à droite
            with ui.row().classes("w-full items-center justify-between gap-3"):

                # bloc dates à gauche
                with ui.row().classes("items-center gap-3"):
                    # Champ + popup calendrier: Publication min
                    pub_min_input = ui.input(
                        label="Publication min",
                        value=default_pub_min.isoformat(),
                    ).props("outlined readonly dense").classes("w-52")
                    
                    pub_min_menu = ui.menu().props("no-parent-event")
                    with pub_min_menu:
                        pub_min_picker = ui.date(value=default_pub_min.isoformat()).props('first-day-of-week="1"')
                        pub_min_picker.on("update:model-value", lambda e: pub_min_menu.close())
                        pub_min_picker.bind_value(pub_min_input)

                    pub_min_input.on("click", lambda e: pub_min_menu.open())  # ouvre le popup

                    # Champ + popup calendrier: Publication max
                    pub_max_input = ui.input(
                        label="Publication max",
                        value=default_pub_max.isoformat(),
                    ).props("outlined readonly dense").classes("w-52")

                    pub_max_menu = ui.menu().props("no-parent-event")
                    with pub_max_menu:
                        pub_max_picker = ui.date(value=default_pub_max.isoformat()).props('first-day-of-week="1"')
                        pub_max_picker.on("update:model-value", lambda e: pub_max_menu.close())
                        pub_max_picker.bind_value(pub_max_input)

                    pub_max_input.on("click", lambda e: pub_max_menu.open())

                    # Reset rapide
                    ui.button(
                        "Semaine dernière",
                        on_click=lambda: (
                            pub_min_input.set_value(default_pub_min.isoformat()),
                            pub_max_input.set_value(default_pub_max.isoformat()),
                        ),
                    ).props("flat dense").classes("text-xs")

                # bouton à droite
                launch_btn = ui.button("Rechercher", icon="search").props("unelevated").classes("px-6")

            ui.separator().classes("my-3")
            ui.label("Historique").classes("text-gray-600")
            list_container = ui.column().classes("w-full gap-2")

    def refresh() -> None:
        jobs = list_jobs()
        list_container.clear()
        with list_container:
            if not jobs:
                ui.label("Aucune recherche. Le calme avant la tempête.").classes("text-gray-500")
                return
            for j in jobs:
                build_job_card(j)

    async def on_launch(_e=None) -> None:
        prompt = (prompt_input.value or "").strip()
        date_pub_min = pub_min_input.value
        date_pub_max = pub_max_input.value
        if not prompt:
            ui.notify("Prompt vide.", type="warning")
            return

        # Créer job
        try:
            search_id = create_job_for_prompt(source="francemarches", statut="en_cours")
        except Exception as e:
            ui.notify(f"Erreur création job: {e}", type="negative")
            return

        # Wizard overlay
        wiz = KeywordsWizard(search_id=search_id, prompt_client=prompt, date_pub_min=date_pub_min, date_pub_max=date_pub_max)
        wiz.open()
        asyncio.create_task(wiz.start_generation())

        # UX: reset input + refresh
        prompt_input.value = ""
        refresh()

    launch_btn.on("click", on_launch)
    prompt_input.on("keydown.enter", on_launch)

    refresh()
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

    label, cls = _status_badge(job.get("statut"))

    with ui.column().classes("w-full items-center"):
        ui.space().classes("h-6")

        with ui.row().classes("w-full max-w-5xl items-center justify-between"):
            back_target = f"/recherche/{rid}" if show_non_pertinent else "/"
            ui.button("← Retour", on_click=lambda _target=back_target: ui.navigate.to(_target)).props("flat")
            page_title = f"Recherche #{rid} · AOs non pertinents" if show_non_pertinent else f"Recherche #{rid}"
            ui.label(page_title).classes("text-xl font-bold")
            ui.chip(label).classes(f"text-sm {cls}").props("outline")
            
        show_params = False
        with ui.card().classes("w-full max-w-5xl").style("border-radius: 16px;"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Détails").classes("text-gray-600")
                details_switch_btn = ui.button("Afficher params").props("flat dense")

            details_value_label = ui.label(_chip(job.get("requete"), "")).classes("text-sm")
            ui.label(
                f"source: {_chip(job.get('source'))} · lancé: {_chip(job.get('date_lancement'))} · "
                f"trouvés: {_chip(job.get('nb_trouves'))} · insérés: {_chip(job.get('nb_insere'))}"
            ).classes("text-gray-500 text-sm")
            
            def toggle_details_value() -> None:
                nonlocal show_params
                show_params = not show_params
                if show_params:
                    details_value_label.set_text(_chip(job.get("params"), ""))
                    details_switch_btn.set_text("Afficher requête")
                else:
                    details_value_label.set_text(_chip(job.get("requete"), ""))
                    details_switch_btn.set_text("Afficher params")

            details_switch_btn.on("click", lambda _e=None: toggle_details_value())


        ui.space().classes("h-4")

        if not show_non_pertinent:
            warning_blob = (job.get("warnings_json") or "").strip()
            limited_searches: List[Dict[str, Any]] = []
            warning_message = (
                "Attention possibilité que tout les appels d'offres ne s'affiche pas car "
                "une de vos recherche n'est pas assez précise et à générer trop d'appels "
                "d'offres différents."
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
                with ui.card().classes("w-full max-w-5xl bg-yellow-50 border border-yellow-200").style("border-radius: 12px;"):
                    ui.label("⚠️ Attention").classes("text-yellow-900 font-semibold")
                    ui.label(warning_message).classes("text-yellow-900 text-sm")
                    with ui.column().classes("gap-1 mt-2"):
                        for info in limited_searches:
                            recherche = (info.get("recherche") or "").strip() or ", ".join(info.get("mots", []))
                            nb_listees = info.get("nb_offres_listees")
                            ui.label(f"• {recherche} ({nb_listees} offres listées)").classes("text-yellow-900 text-sm")

                ui.space().classes("h-4")

        with ui.card().classes("w-full max-w-5xl").style("border-radius: 16px;"):
            with ui.row().classes("w-full items-center justify-between"):
                titre_aos = "AOs non pertinents" if show_non_pertinent else "Appels d'offres"
                ui.label(titre_aos).classes("text-gray-600")
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

            ui.separator().classes("my-2")
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


ui.run(reload=True)
