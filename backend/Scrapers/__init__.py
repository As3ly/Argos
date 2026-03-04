from .scrap_francemarche import build_francemarche_session, scrape_francemarche_into_raw
from datetime import date
# from .boamp import scrape_boamp_into_raw
# from .aws import scrape_aws_into_raw

SCRAPERS = [
    ("francemarches", scrape_francemarche_into_raw),
    # ("boamp", scrape_boamp_into_raw),
    # ("aws", scrape_aws_into_raw),
]

def run_all_scrapers(search_id: int, mots_recherche: list, sess, *, continue_on_error: bool = True, date_pub_min: date, date_pub_max: date):
    """
    Lance tous les scrapers enregistrés.
    - continue_on_error=True: un site qui plante ne bloque pas les autres.
    """
    errors = []
    for name, func in SCRAPERS:
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