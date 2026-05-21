from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

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

API_URL = "https://api.ted.europa.eu/v3/notices/search"
DEFAULT_LIMIT = 100
MAX_OFFRES_PAR_RECHERCHE = 300
DEFAULT_SCOPE = "ACTIVE"
DEFAULT_CPV_PREFIX: str | None = None
DEFAULT_NOTICE_TYPES = ["cn-standard", "cn-social"]

TED_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "publication-date",
    "deadline-receipt-tender-date-lot",
    "classification-cpv",
    "notice-type",
    "place-of-performance",
    "links",
    "title-proc",
    "description-proc",
    "title-lot",
    "description-lot",
]


def _get_proxy_value(name: str) -> str | None:
    """Return proxy from framatome module first, then from environment variables."""
    if framatome is not None:
        value = getattr(framatome, name, None)
        if value:
            return value

    return os.environ.get(name)


TED_PROXIES = {
    "http": _get_proxy_value("HTTP_PROXY"),
    "https": _get_proxy_value("HTTPS_PROXY"),
}


def _clean_scalar(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        cleaned = [_clean_scalar(item).strip() for item in value]
        return ", ".join(item for item in cleaned if item)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _first_value(record: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value among several possible field names."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _escape_ted_term(value: str) -> str:
    sanitized = (value or "").replace('"', " ").replace("'", " ")
    sanitized = sanitized.replace("(", " ").replace(")", " ")
    return " ".join(sanitized.split())


def _build_ted_query(
    *,
    keywords: str,
    date_pub_min: date,
    date_pub_max: date,
    cpv_prefix: str | None = DEFAULT_CPV_PREFIX,
    country: str = "FRA",
    notice_types: list[str] | None = None,
) -> str:
    safe_keywords = _escape_ted_term(keywords)
    active_notice_types = notice_types or DEFAULT_NOTICE_TYPES

    parts = [
        f"FT~({safe_keywords})" if safe_keywords else "",
        f"place-of-performance IN ({_escape_ted_term(country)})",
        f"notice-type IN ({' '.join(_escape_ted_term(item) for item in active_notice_types if item)})",
        f"publication-date >= {date_pub_min.strftime('%Y%m%d')}",
        f"publication-date <= {date_pub_max.strftime('%Y%m%d')}",
    ]

    if cpv_prefix:
        parts.insert(2, f"classification-cpv = {_escape_ted_term(cpv_prefix)}")

    return " AND ".join(part for part in parts if part)


def _extract_notices(payload: Any) -> list[dict[str, Any]]:
    candidate: Any = None
    if isinstance(payload, dict):
        for key in ("notices", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                candidate = value
                break
    elif isinstance(payload, list):
        candidate = payload

    if candidate is None:
        _LOGGER.warning("Réponse TED inattendue: type=%s keys=%s", type(payload), list(payload.keys()) if isinstance(payload, dict) else "n/a")
        return []

    return [row for row in candidate if isinstance(row, dict)]


def _fetch_notices(
    session: requests.Session,
    *,
    query: str,
    page: int,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    if limit > 250:
        raise ValueError("L'API TED limite `limit` à 250 maximum.")

    payload = {
        "query": query,
        "fields": TED_FIELDS,
        "limit": limit,
        "scope": DEFAULT_SCOPE,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
        "page": page,
    }

    resp = session.post(
        API_URL,
        json=payload,
        timeout=30,
        headers={"Content-Type": "application/json"},
    )

    if not resp.ok:
        _LOGGER.error(
            "TED API error status=%s url=%s payload=%s body=%s",
            resp.status_code,
            resp.url,
            payload,
            resp.text[:2000],
        )

    resp.raise_for_status()
    return _extract_notices(resp.json())


def _build_ted_url(record: dict[str, Any]) -> str:
    links = record.get("links")
    if isinstance(links, list):
        for item in links:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                for key in ("url", "href", "link"):
                    link_value = item.get(key)
                    if isinstance(link_value, str) and link_value.startswith("http"):
                        return link_value
    elif isinstance(links, dict):
        for key in ("url", "href", "link"):
            link_value = links.get(key)
            if isinstance(link_value, str) and link_value.startswith("http"):
                return link_value

    publication_number = _clean_scalar(record.get("publication-number"))
    if publication_number:
        encoded = quote(publication_number, safe="")
        return f"https://ted.europa.eu/fr/notice/-/detail/{encoded}"

    return "https://ted.europa.eu/fr/search/home"


def _record_to_raw_text(record: dict[str, Any]) -> str:
    publication_number = _clean_scalar(record.get("publication-number"))
    lines = [
        "Source: TED / JOUE",
        f"Publication number: {publication_number}",
        f"Titre: {_clean_scalar(_first_value(record, 'notice-title', 'title-proc'))}",
        f"Acheteur: {_clean_scalar(record.get('buyer-name'))}",
        f"Pays acheteur: {_clean_scalar(record.get('buyer-country'))}",
        f"Date publication: {_clean_scalar(record.get('publication-date'))}",
        f"Date limite: {_clean_scalar(record.get('deadline-receipt-tender-date-lot'))}",
        f"CPV: {_clean_scalar(record.get('classification-cpv'))}",
        f"Type avis: {_clean_scalar(record.get('notice-type'))}",
        f"Lieu exécution: {_clean_scalar(record.get('place-of-performance'))}",
        f"Titre procédure: {_clean_scalar(record.get('title-proc'))}",
        f"Description procédure: {_clean_scalar(record.get('description-proc'))}",
        f"Titre lot: {_clean_scalar(record.get('title-lot'))}",
        f"Description lot: {_clean_scalar(record.get('description-lot'))}",
        f"URL: {_build_ted_url(record)}",
    ]
    return "\n".join(lines)


def scrape_ted_into_raw(
    search_id: int,
    mots_recherche: list,
    sess,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> None:
    """Scrape TED/JOUE notices and insert raw rows for downstream AI classification."""
    _ = sess

    local_sess = requests.Session()

    active_proxies = {key: value for key, value in TED_PROXIES.items() if value}
    if active_proxies:
        local_sess.proxies = active_proxies

    if date_pub_max is None:
        date_pub_max = date.today()
    if date_pub_min is None:
        date_pub_min = date_pub_max - timedelta(days=7)

    liens_uniques: set[str] = set()
    nb_inserts = 0
    recherches_limitees: list[dict[str, Any]] = []

    for mots in mots_recherche:
        keywords = " ".join(mots).strip() if isinstance(mots, list) else str(mots).strip()
        if not keywords:
            continue

        query = _build_ted_query(
            keywords=keywords,
            date_pub_min=date_pub_min,
            date_pub_max=date_pub_max,
            cpv_prefix=None,
        )

        page = 1
        nb_offres_lues = 0
        nb_inserts_pour_recherche = 0
        recherche_limitee = False

        while True:
            rows = _fetch_notices(local_sess, query=query, page=page, limit=DEFAULT_LIMIT)
            if not rows:
                break

            for row in rows:
                nb_offres_lues += 1

                lien = _build_ted_url(row)

                if lien not in liens_uniques and not raw_lien_existe(search_id, lien):
                    # source="ted" correspond aux avis JOUE/TED.
                    inserer_raw_recherche(
                        search_id=search_id,
                        source="ted",
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

            if len(rows) < DEFAULT_LIMIT:
                break

            page += 1

    warning_payload = {
        "type": "pagination_limit",
        "message": "Limite TED atteinte pour certaines recherches trop larges.",
        "limited_searches": recherches_limitees,
    }

    update_recherche_job(
        search_id,
        nb_trouves=nb_inserts,
        warnings_json=json.dumps(warning_payload, ensure_ascii=False),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    today = date.today()
    query = _build_ted_query(
        keywords="data ia",
        date_pub_min=today - timedelta(days=7),
        date_pub_max=today,
        cpv_prefix=None,
    )
    with requests.Session() as debug_sess:
        active_proxies = {key: value for key, value in TED_PROXIES.items() if value}
        if active_proxies:
            debug_sess.proxies = active_proxies
        notices = _fetch_notices(debug_sess, query=query, page=1, limit=10)
    print(f"Query TED: {query}")
    print(f"Notices récupérées: {len(notices)}")
    if notices:
        print(json.dumps(notices[0], ensure_ascii=False, indent=2)[:3000])
