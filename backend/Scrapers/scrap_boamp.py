from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from urllib.parse import quote
from typing import Any

import requests

from db.repository import inserer_raw_recherche, raw_lien_existe, update_recherche_job

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    # En local hors environnement entreprise, le script doit rester importable.
    pass

try:
    import framatome
except ImportError:
    framatome = None


_LOGGER = logging.getLogger(__name__)

# Domaine public du site BOAMP utilisé uniquement pour construire les liens lisibles.
BASE_URL = "https://www.boamp.fr"

# API OpenDataSoft/Huwise réelle du dataset BOAMP.
# L'ancien code tapait https://www.boamp.fr/api/... + dataset "avis",
# ce qui est la source principale des 404/400.
API_BASE = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1"
DEFAULT_DATASET = "boamp"

DEFAULT_LIMIT = 100
MAX_OFFRES_PAR_RECHERCHE = 300

# Champs stables et utiles du dataset BOAMP.
# Certains anciens champs du script initial n'existent pas/plus :
# ville, departement, typeavis, procedure, datelimite.
BOAMP_SELECT_FIELDS = [
    "id",
    "idweb",
    "objet",
    "nomacheteur",
    "dateparution",
    "datelimitereponse",
    "etat",
    "type_marche",
    "procedure_libelle",
    "code_departement",
    "descripteur_code",
    "descripteur_libelle",
    "url_avis",
]


def _get_proxy_value(name: str) -> str | None:
    """Return proxy from framatome module first, then from environment variables."""
    if framatome is not None:
        value = getattr(framatome, name, None)
        if value:
            return value

    return os.environ.get(name)


# Proxy entreprise BOAMP.
BOAMP_PROXIES = {
    "http": _get_proxy_value("HTTP_PROXY"),
    "https": _get_proxy_value("HTTPS_PROXY"),
}


def _escape_odsql_string(value: str) -> str:
    """Escape a Python string for use inside an ODSQL double-quoted string."""
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _build_where_clause(*, keywords: str, date_pub_min: date, date_pub_max: date) -> str:
    """
    Build ODSQL WHERE clause.

    Important :
    - search(*, "...") cherche sur les champs texte indexés.
    - search(_full_text, "...") est fragile/invalide selon les datasets ODS.
    """
    escaped_keywords = _escape_odsql_string(keywords)

    parts = [
        f'search(*, "{escaped_keywords}")',
        f"dateparution >= date'{date_pub_min.isoformat()}'",
        f"dateparution <= date'{date_pub_max.isoformat()}'",
    ]

    return " AND ".join(parts)


def _first_value(record: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value among several possible field names."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _record_to_raw_text(record: dict[str, Any]) -> str:
    fields = [
        ("ID", _first_value(record, "idweb", "id")),
        ("Titre", record.get("objet")),
        ("Acheteur", record.get("nomacheteur")),
        ("Département", _first_value(record, "code_departement", "departement")),
        ("Type marché", _first_value(record, "type_marche", "typeavis", "famille")),
        ("Procédure", _first_value(record, "procedure_libelle", "procedure")),
        ("Descripteur code", record.get("descripteur_code")),
        ("Descripteur", record.get("descripteur_libelle")),
        ("État", record.get("etat")),
        ("Date parution", record.get("dateparution")),
        ("Date limite", _first_value(record, "datelimitereponse", "datelimite")),
        ("URL", _first_value(record, "_boamp_url", "url_avis")),
    ]

    return "\n".join(f"{label}: {value}" for label, value in fields if value)


def _build_boamp_url(record: dict[str, Any]) -> str:
    """
    Build a BOAMP-readable URL.

    Priority:
    1. url_avis from API, when present.
    2. BOAMP search URL by idweb.
    3. API record URL fallback.
    """
    existing_url = _first_value(record, "_boamp_url", "url_avis")
    if existing_url:
        return str(existing_url)

    avis_id = record.get("idweb")
    if avis_id:
        query = quote(f'idweb:"{avis_id}"', safe="")
        return f"{BASE_URL}/pages/avis/?q={query}"

    identifier = record.get("id") or record.get("uid") or ""
    safe_identifier = quote(str(identifier), safe="")
    return f"{API_BASE}/catalog/datasets/{DEFAULT_DATASET}/records/{safe_identifier}"


def _fetch_records(
    session: requests.Session,
    *,
    where: str,
    offset: int,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    if limit > DEFAULT_LIMIT:
        raise ValueError("L'API records OpenDataSoft limite généralement limit à 100 sans group_by.")

    resp = session.get(
        f"{API_BASE}/catalog/datasets/{DEFAULT_DATASET}/records",
        params={
            "where": where,
            "limit": limit,
            "offset": offset,
            "order_by": "dateparution desc",
            "select": ",".join(BOAMP_SELECT_FIELDS),
        },
        timeout=30,
    )

    if not resp.ok:
        # Debug volontairement bavard : indispensable pour voir le vrai message ODSQL.
        _LOGGER.error("BOAMP API error status=%s url=%s body=%s", resp.status_code, resp.url, resp.text[:2000])
        print("URL appelée:", resp.url)
        print("STATUS:", resp.status_code)
        print("BODY:", resp.text[:2000])

    resp.raise_for_status()
    payload = resp.json()
    return payload.get("results", [])


def scrape_boamp_into_raw(
    search_id: int,
    mots_recherche: list,
    sess,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> None:
    """
    Scrape BOAMP API results into the raw search table.

    `sess` is kept for compatibility with the existing caller, but this scraper
    uses its own requests.Session because it does not use the FranceMarchés session.
    """
    _ = sess

    local_sess = requests.Session()

    active_proxies = {key: value for key, value in BOAMP_PROXIES.items() if value}
    if active_proxies:
        local_sess.proxies = active_proxies

    today = date.today()
    if date_pub_max is None:
        date_pub_max = today
    if date_pub_min is None:
        date_pub_min = date_pub_max - timedelta(days=7)

    liens_uniques: set[str] = set()
    nb_inserts = 0
    recherches_limitees: list[dict[str, Any]] = []

    for mots in mots_recherche:
        query = " ".join(mots).strip() if isinstance(mots, list) else str(mots).strip()
        if not query:
            continue

        where_clause = _build_where_clause(
            keywords=query,
            date_pub_min=date_pub_min,
            date_pub_max=date_pub_max,
        )

        offset = 0
        nb_offres_lues = 0
        nb_inserts_pour_recherche = 0
        recherche_limitee = False

        while True:
            rows = _fetch_records(local_sess, where=where_clause, offset=offset)
            if not rows:
                break

            for row in rows:
                nb_offres_lues += 1

                row["_boamp_url"] = _build_boamp_url(row)
                lien = row["_boamp_url"]

                if lien not in liens_uniques and not raw_lien_existe(search_id, lien):
                    inserer_raw_recherche(
                        search_id=search_id,
                        source="boamp",
                        mot_cle=query,
                        html_contenu=_record_to_raw_text(row),
                        lien=lien,
                    )
                    liens_uniques.add(lien)
                    nb_inserts += 1
                    nb_inserts_pour_recherche += 1

                if nb_offres_lues >= MAX_OFFRES_PAR_RECHERCHE:
                    recherche_limitee = True
                    break

            if recherche_limitee:
                recherches_limitees.append(
                    {
                        "recherche": query,
                        "nb_offres_lues": nb_offres_lues,
                        "nb_inserts": nb_inserts_pour_recherche,
                        "seuil": MAX_OFFRES_PAR_RECHERCHE,
                    }
                )
                break

            # Pagination normale. Si l'API renvoie moins que la limite,
            # il n'y a logiquement plus de page suivante.
            if len(rows) < DEFAULT_LIMIT:
                break

            offset += len(rows)

    warning_payload = {
        "type": "pagination_limit",
        "message": "Limite BOAMP atteinte pour certaines recherches trop larges.",
        "limited_searches": recherches_limitees,
    }

    update_recherche_job(
        search_id,
        nb_trouves=nb_inserts,
        warnings_json=json.dumps(warning_payload, ensure_ascii=False),
    )
