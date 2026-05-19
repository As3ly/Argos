import json
from datetime import date, timedelta
from urllib.parse import quote

import requests

from db.repository import inserer_raw_recherche, raw_lien_existe, update_recherche_job

BASE_URL = "https://www.boamp.fr"
API_BASE = f"{BASE_URL}/api/explore/v2.1"
DEFAULT_DATASET = "avis"
DEFAULT_LIMIT = 100
MAX_OFFRES_PAR_RECHERCHE = 300
# Proxy entreprise BOAMP (à personnaliser localement si nécessaire)
BOAMP_PROXIES = {
    "http": "",
    "https": "",
}


def _build_where_clause(*, keywords: str, date_pub_min: date, date_pub_max: date) -> str:
    # ODSQL date literal format: date'YYYY-MM-DD'
    escaped_keywords = keywords.replace('"', '\\"')
    return (
        f'search(_full_text, "{escaped_keywords}") '
        f"AND dateparution >= date'{date_pub_min.isoformat()}' "
        f"AND dateparution <= date'{date_pub_max.isoformat()}'"
    )


def _record_to_raw_text(record: dict) -> str:
    fields = [
        ("ID", record.get("idweb")),
        ("Titre", record.get("objet")),
        ("Acheteur", record.get("nomacheteur")),
        ("Ville", record.get("ville")),
        ("Département", record.get("departement")),
        ("Type d'avis", record.get("typeavis")),
        ("Famille", record.get("famille")),
        ("Procédure", record.get("procedure")),
        ("Date parution", record.get("dateparution")),
        ("Date limite", record.get("datelimite")),
        ("URL", record.get("_boamp_url")),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if value)


def _build_boamp_url(record: dict) -> str:
    if record.get("_boamp_url"):
        return str(record["_boamp_url"])

    avis_id = record.get("idweb")
    if avis_id:
        return f"{BASE_URL}/avis/detail/{avis_id}"

    identifier = record.get("id") or record.get("uid") or ""
    safe_identifier = quote(str(identifier), safe="")
    return f"{BASE_URL}/api/explore/v2.1/catalog/datasets/{DEFAULT_DATASET}/records/{safe_identifier}"


def _fetch_records(session: requests.Session, *, where: str, offset: int, limit: int = DEFAULT_LIMIT) -> list[dict]:
    resp = session.get(
        f"{API_BASE}/catalog/datasets/{DEFAULT_DATASET}/records",
        params={
            "where": where,
            "limit": limit,
            "offset": offset,
            "order_by": "dateparution desc",
            "select": "id,idweb,objet,nomacheteur,ville,departement,typeavis,famille,procedure,dateparution,datelimite",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def scrape_boamp_into_raw(
    search_id: int,
    mots_recherche: list,
    sess,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> None:
    # Session locale: ce scraper n'utilise pas la session FranceMarchés.
    local_sess = requests.Session()
    if BOAMP_PROXIES.get("http") or BOAMP_PROXIES.get("https"):
        local_sess.proxies = BOAMP_PROXIES
    today = date.today()
    if date_pub_max is None:
        date_pub_max = today
    if date_pub_min is None:
        date_pub_min = date_pub_max - timedelta(days=7)

    liens_uniques = set()
    nb_inserts = 0
    recherches_limitees = []

    for mots in mots_recherche:
        query = " ".join(mots).strip() if isinstance(mots, list) else str(mots).strip()
        if not query:
            continue

        where_clause = _build_where_clause(keywords=query, date_pub_min=date_pub_min, date_pub_max=date_pub_max)
        offset = 0
        total_group = 0

        while True:
            rows = _fetch_records(local_sess, where=where_clause, offset=offset)
            if not rows:
                break

            for row in rows:
                row["_boamp_url"] = _build_boamp_url(row)
                lien = row["_boamp_url"]
                if lien in liens_uniques or raw_lien_existe(search_id, lien):
                    continue

                inserer_raw_recherche(
                    search_id=search_id,
                    source="boamp",
                    mot_cle=query,
                    html_contenu=_record_to_raw_text(row),
                    lien=lien,
                )
                liens_uniques.add(lien)
                nb_inserts += 1
                total_group += 1

                if total_group >= MAX_OFFRES_PAR_RECHERCHE:
                    recherches_limitees.append(
                        {
                            "recherche": query,
                            "nb_offres_listees": total_group,
                            "seuil": MAX_OFFRES_PAR_RECHERCHE,
                        }
                    )
                    break

            if total_group >= MAX_OFFRES_PAR_RECHERCHE:
                break

            offset += len(rows)

    warning_payload = {
        "type": "pagination_limit",
        "message": "Limite BOAMP atteinte pour certaines recherches (requête trop large).",
        "limited_searches": recherches_limitees,
    }

    update_recherche_job(
        search_id,
        nb_trouves=nb_inserts,
        warnings_json=json.dumps(warning_payload, ensure_ascii=False),
    )
