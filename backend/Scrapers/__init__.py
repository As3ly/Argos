from .scrap_boamp import scrape_boamp_into_raw
from .scrap_edf import scrape_edf_into_raw
from .scrap_ted import scrape_ted_into_raw
from datetime import date
from typing import Any, Sequence

from db.repository import append_recherche_job_warning

SCRAPER_LABELS = {
    "boamp": "BOAMP",
    "edf": "EDF - Portail fournisseurs",
    "ted": "TED / JOUE",
}

SCRAPERS = [
    ("boamp", scrape_boamp_into_raw),
    ("edf", scrape_edf_into_raw),
    ("ted", scrape_ted_into_raw),
]


def list_scraper_names() -> list[str]:
    return [name for name, _func in SCRAPERS]


def list_scraper_options() -> list[dict[str, str]]:
    return [{"code": name, "label": SCRAPER_LABELS.get(name, name)} for name, _func in SCRAPERS]


def run_all_scrapers(
    search_id: int,
    mots_recherche: list,
    sess: Any = None,
    *,
    continue_on_error: bool = True,
    date_pub_min: date | None,
    date_pub_max: date | None,
    selected_sites: Sequence[str] | None = None,
):
    """
    Lance tous les scrapers enregistrés.
    - continue_on_error=True: un site qui plante ne bloque pas les autres.
    """
    selected_set = set(list_scraper_names() if selected_sites is None else selected_sites)
    available = {name for name, _func in SCRAPERS}
    unknown = selected_set - available
    if unknown:
        raise ValueError(f"Scraper(s) inconnu(s): {', '.join(sorted(unknown))}")

    errors = []
    for name, func in SCRAPERS:
        if name not in selected_set:
            print(f"[SCRAPER] Ignoré: {name}")
            continue

        try:
            print(f"[SCRAPER] Début: {name}")
            func(search_id=search_id, mots_recherche=mots_recherche, sess=sess, date_pub_min=date_pub_min, date_pub_max=date_pub_max)
            print(f"[SCRAPER] OK: {name}")
        except Exception as e:
            print(f"[SCRAPER] ERREUR: {name} -> {e}")
            errors.append((name, repr(e)))
            warning_type = getattr(e, "warning_type", "scraper_error")
            detail = str(getattr(e, "user_message", "") or "").strip()
            message = detail or (
                f"La source {SCRAPER_LABELS.get(name, name)} n'a pas pu être interrogée "
                f"({type(e).__name__}). La recherche a continué avec les autres sources."
            )
            try:
                append_recherche_job_warning(
                    search_id,
                    {
                        "type": warning_type,
                        "severity": "error",
                        "source": name,
                        "message": message,
                    },
                )
            except Exception as warning_error:
                # Une base momentanément verrouillée ne doit pas transformer une erreur
                # de source partielle en arrêt complet de la recherche multi-source.
                print(f"[SCRAPER] Impossible de persister l'alerte {name}: {warning_error}")
            if not continue_on_error:
                raise

    return errors
