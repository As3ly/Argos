"""pipeline.py

Pont propre entre le backend (scrapers + IA + DB) et une UI (NiceGUI ou autre).

Objectifs:
- Zéro asyncio.run() (interdit côté serveur async).
- Les fonctions bloquantes (scraping requests, etc.) partent en thread via asyncio.to_thread.
- On centralise les updates de statut du job pour que l'UI puisse suivre.

Ce module est volontairement "thin": il orchestre, il ne ré-implémente pas.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Sequence
from datetime import date, datetime

from IAfiltre_async import generate_criteres_prompt_json, process_search_id_async
from db.repository import initialize_database, create_recherche_job, update_recherche_job


# Les scrapers existent dans ton repo. En sandbox ils ne sont pas fournis,
# donc on garde un import tolérant et un message d'erreur lisible.
try:
    from Scrapers import run_all_scrapers, build_francemarche_session
except Exception:  # pragma: no cover
    run_all_scrapers = None
    build_francemarche_session = None


MotsRecherche = List[List[str]]

def _coerce_date(value: date | str | None) -> date | None:
    """Normalise une date venant de l'UI (date object ou string ISO)."""
    if value is None or isinstance(value, date):
        return value

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        for parser in (date.fromisoformat, lambda s: datetime.strptime(s, "%d/%m/%Y").date()):
            try:
                return parser(raw)
            except ValueError:
                continue

    raise ValueError(f"Format de date invalide: {value!r}")


@dataclass(frozen=True)
class KeywordsResult:
    search_id: int
    mots_recherche: MotsRecherche
    meta_prompt: str
    titre_recherche: str = ""


def create_job_for_prompt(*, source: str, statut: str = "en_cours") -> int:
    """Crée un job DB minimal. La requête sera remplie après validation des mots-clés."""
    initialize_database()
    return create_recherche_job(
        requete="en cours de génération",
        source=source,
        statut=statut,
    )


async def generate_keywords(*, search_id: int, prompt_client: str) -> KeywordsResult:
    """Appel LLM async: génère mots-clés + meta_prompt."""
    update_recherche_job(search_id, statut="generation_mots_cle")
    mots_recherche, meta_prompt, titre_recherche = await generate_criteres_prompt_json(search_id, prompt_client)
    return KeywordsResult(
        search_id=search_id,
        mots_recherche=mots_recherche,
        meta_prompt=meta_prompt,
        titre_recherche=titre_recherche,
    )


def mots_recherche_to_requete(mots_recherche: Sequence[Sequence[str]]) -> str:
    """Reproduit la concat du main: 'mot1 mot2,mot3 mot4,...'"""
    return ",".join(" ".join(g).strip() for g in mots_recherche if g)


async def run_full_pipeline(
    *,
    search_id: int,
    mots_recherche: MotsRecherche,
    meta_prompt: str,
    date_pub_min: date | str | None = None,
    date_pub_max: date | str | None = None,
) -> None:
    """Lance scraping + tri IA sans bloquer l'event loop."""

    if run_all_scrapers is None or build_francemarche_session is None:
        update_recherche_job(search_id, statut="erreur_scraper")
        raise RuntimeError(
            "Module 'Scrapers' introuvable. Vérifie que ton projet contient Scrapers.py / package Scrapers."
        )

    # 1) persist requête + statut
    requete_str = mots_recherche_to_requete(mots_recherche)
    update_recherche_job(search_id, requete=requete_str, statut="scraping")
    
    parsed_date_pub_min = _coerce_date(date_pub_min)
    parsed_date_pub_max = _coerce_date(date_pub_max)

    # 2) scraping (bloquant) -> thread
    sess = await asyncio.to_thread(build_francemarche_session)
    await asyncio.to_thread(
        run_all_scrapers,
        search_id=search_id,
        mots_recherche=mots_recherche,
        sess=sess,
        date_pub_min=parsed_date_pub_min,
        date_pub_max=parsed_date_pub_max,
    )

    # 3) tri IA (async)
    update_recherche_job(search_id, statut="tri_ia")
    await process_search_id_async(search_id, meta_prompt)

    # 4) fin
    update_recherche_job(search_id, statut="termine")
