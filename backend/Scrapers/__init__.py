from .scrap_francemarche import build_francemarche_session, scrape_francemarche_into_raw
from datetime import date
from typing import Sequence
# from .boamp import scrape_boamp_into_raw
# from .aws import scrape_aws_into_raw

SCRAPERS = [
    ("francemarches", scrape_francemarche_into_raw),
    # ("boamp", scrape_boamp_into_raw),
    # ("aws", scrape_aws_into_raw),
]


def list_scraper_names() -> list[str]:
    return [name for name, _func in SCRAPERS]


def run_all_scrapers(
    search_id: int,
    mots_recherche: list,
    sess,
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
            if not continue_on_error:
                raise

    return errors
