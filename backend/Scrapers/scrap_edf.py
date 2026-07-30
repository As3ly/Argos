from __future__ import annotations

import logging
import os
import re
import unicodedata
from http.cookies import CookieError, SimpleCookie
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv

from db.repository import (
    append_recherche_job_warning,
    increment_recherche_job_counts,
    inserer_raw_recherche,
    raw_lien_existe,
)
from proxy_config import get_requests_proxies
from tls_config import inject_truststore_once

inject_truststore_once()
load_dotenv()


BASE_URL = "https://pha2.edf.com"
BROWSE_URL = f"{BASE_URL}/page.aspx/fr/rfp/request_browse_public"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
DEFAULT_TIMEOUT = 30
MAX_OFFRES_PAR_RECHERCHE = 300

# Le portail vérifie notamment que le client ressemble à un navigateur moderne.
# Edge est la référence retenue par la codebase quand un navigateur est nécessaire.
EDGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Edg/138.0.0.0 Safari/537.36"
)


class EdfCaptchaRequired(RuntimeError):
    """Le portail Ivalua exige une intervention humaine avant de servir les AO."""

    warning_type = "captcha_required"
    user_message = (
        "Le portail EDF a demandé un CAPTCHA. Argos ne le contourne pas : "
        "EDF a été ignoré pour cette recherche et les autres sources ont continué."
    )

    def __init__(self, message: str | None = None) -> None:
        self.user_message = message or type(self).user_message
        super().__init__(self.user_message)


class EdfRobotsDenied(RuntimeError):
    """La politique robots du portail n'autorise pas la collecte automatisée."""

    warning_type = "access_policy_denied"
    user_message = (
        "Le portail EDF interdit actuellement la collecte automatisée dans son fichier robots.txt. "
        "EDF n'a pas été interrogé ; une autorisation explicite d'EDF est nécessaire pour activer cette source."
    )

    def __init__(self) -> None:
        super().__init__(self.user_message)


class EdfPortalFormatError(RuntimeError):
    """La page publique EDF ne correspond plus au format Ivalua attendu."""

    warning_type = "portal_format_error"
    user_message = (
        "Le format du portail EDF a changé et sa liste d'appels d'offres n'a pas pu être lue."
    )


class EdfAuthorizedSessionConfigError(RuntimeError):
    """Le mode session prévalidée a été demandé sans configuration exploitable."""

    warning_type = "authorized_session_config_error"

    def __init__(self, message: str) -> None:
        self.user_message = message
        super().__init__(message)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).split())


def _response_soup(response: requests.Response) -> BeautifulSoup:
    # Utiliser les octets laisse BeautifulSoup respecter le <meta charset>, contrairement
    # à response.text lorsque le serveur Ivalua omet son charset HTTP.
    return BeautifulSoup(response.content, "html.parser")


def _captcha_is_present(response: requests.Response, soup: BeautifulSoup) -> bool:
    path = urlparse(response.url).path.lower()
    if path.endswith("/bas/browser_check"):
        return True
    if soup.select_one("input[name='captcha_response'], input[id*='captcha' i]"):
        return True
    text = _normalize(soup.get_text(" ", strip=True))
    return "resoudre ce captcha" in text or "solve this captcha" in text


def _raise_for_portal_response(response: requests.Response, soup: BeautifulSoup) -> None:
    response.raise_for_status()
    if _captcha_is_present(response, soup):
        if _captcha_mode() == "prevalidated_session":
            raise EdfCaptchaRequired(
                "La session EDF prévalidée a expiré ou a été refusée et le portail demande de nouveau "
                "un CAPTCHA. EDF a été ignoré ; renouvelez la session autorisée."
            )
        raise EdfCaptchaRequired()


def _captcha_mode() -> str:
    mode = os.getenv("ARGOS_EDF_CAPTCHA_MODE", "fail").strip().lower()
    if mode not in {"fail", "prevalidated_session"}:
        raise EdfAuthorizedSessionConfigError(
            "ARGOS_EDF_CAPTCHA_MODE doit valoir 'fail' ou 'prevalidated_session'."
        )
    return mode


def _configure_authorized_session(session: requests.Session) -> None:
    """Charge uniquement une session déjà validée par un administrateur EDF."""
    if _captcha_mode() == "fail":
        return
    if not _explicit_owner_authorization():
        raise EdfAuthorizedSessionConfigError(
            "Le mode de session EDF prévalidée exige ARGOS_EDF_SCRAPING_AUTHORIZED=true."
        )

    raw_cookie = os.getenv("ARGOS_EDF_AUTHORIZED_SESSION_COOKIE", "").strip()
    if not raw_cookie:
        raise EdfAuthorizedSessionConfigError(
            "Le mode de session EDF prévalidée exige ARGOS_EDF_AUTHORIZED_SESSION_COOKIE."
        )

    parsed = SimpleCookie()
    try:
        parsed.load(raw_cookie)
    except CookieError as exc:
        raise EdfAuthorizedSessionConfigError(
            "ARGOS_EDF_AUTHORIZED_SESSION_COOKIE n'est pas un en-tête Cookie valide."
        ) from exc
    if not parsed:
        raise EdfAuthorizedSessionConfigError(
            "ARGOS_EDF_AUTHORIZED_SESSION_COOKIE ne contient aucun cookie valide."
        )

    for name, morsel in parsed.items():
        session.cookies.set(name, morsel.value, domain="pha2.edf.com", path="/")


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": EDGE_USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        }
    )
    proxies = get_requests_proxies()
    if proxies:
        session.proxies.update(proxies)
    _configure_authorized_session(session)
    return session


def _explicit_owner_authorization() -> bool:
    """Un administrateur ne peut lever le garde-fou qu'après autorisation d'EDF."""
    return os.getenv("ARGOS_EDF_SCRAPING_AUTHORIZED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _ensure_robots_allowed(session: requests.Session) -> None:
    if _explicit_owner_authorization():
        return

    response = session.get(ROBOTS_URL, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.parse(response.text.splitlines())
    if not parser.can_fetch("Argos", BROWSE_URL):
        raise EdfRobotsDenied()


def _fetch_page(session: requests.Session) -> tuple[requests.Response, BeautifulSoup]:
    response = session.get(BROWSE_URL, timeout=DEFAULT_TIMEOUT)
    soup = _response_soup(response)
    _raise_for_portal_response(response, soup)
    return response, soup


def _form_values(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Reproduit les champs transmis par un formulaire HTML classique."""
    form = soup.select_one("form#mainForm") or soup.find("form")
    if not isinstance(form, Tag):
        raise EdfPortalFormatError("Formulaire principal Ivalua introuvable.")

    values: list[tuple[str, str]] = []
    for control in form.select("input[name], select[name], textarea[name]"):
        if control.has_attr("disabled"):
            continue

        name = str(control.get("name") or "")
        control_type = str(control.get("type") or "text").lower()
        if control.name == "input" and control_type in {"button", "submit", "reset", "image", "file"}:
            continue
        if control.name == "input" and control_type in {"checkbox", "radio"} and not control.has_attr("checked"):
            continue

        if control.name == "select":
            options = control.select("option[selected]") or control.select("option")[:1]
            values.extend((name, str(option.get("value", option.get_text()))) for option in options)
        else:
            values.append((name, str(control.get("value") or "")))
    return values


def _replace_form_value(
    values: Iterable[tuple[str, str]],
    *,
    predicate,
    value: str,
) -> tuple[list[tuple[str, str]], bool]:
    replaced = False
    result: list[tuple[str, str]] = []
    for name, current in values:
        if predicate(name):
            if not replaced:
                result.append((name, value))
                replaced = True
            continue
        result.append((name, current))
    return result, replaced


def _post_form(
    session: requests.Session,
    soup: BeautifulSoup,
    *,
    extra_values: Iterable[tuple[str, str]],
) -> tuple[requests.Response, BeautifulSoup]:
    form = soup.select_one("form#mainForm") or soup.find("form")
    if not isinstance(form, Tag):
        raise EdfPortalFormatError("Formulaire principal Ivalua introuvable.")
    action = urljoin(BROWSE_URL, str(form.get("action") or BROWSE_URL))
    values = _form_values(soup)
    extra_values = list(extra_values)
    extra_names = {name for name, _value in extra_values}
    values = [(name, value) for name, value in values if name not in extra_names]
    values.extend(extra_values)

    response = session.post(action, data=values, timeout=DEFAULT_TIMEOUT)
    result_soup = _response_soup(response)
    _raise_for_portal_response(response, result_soup)
    return response, result_soup


def _submit_search(
    session: requests.Session,
    soup: BeautifulSoup,
    query: str,
) -> tuple[requests.Response, BeautifulSoup]:
    values = _form_values(soup)
    values, found_query = _replace_form_value(
        values,
        predicate=lambda name: name.lower().endswith(":txtquery"),
        value=query,
    )
    if not found_query:
        raise EdfPortalFormatError("Champ de recherche EDF introuvable.")

    search_button = soup.select_one("button[name$=':cmdSearchBtn']")
    if not isinstance(search_button, Tag) or not search_button.get("name"):
        raise EdfPortalFormatError("Bouton de recherche EDF introuvable.")

    # _post_form reconstruit les valeurs depuis soup : transmettre explicitement la
    # requête remplacée et le bouton submit évite de dépendre de l'ordre des champs.
    query_name = next(name for name, value in values if value == query and name.lower().endswith(":txtquery"))
    return _post_form(
        session,
        soup,
        extra_values=[(query_name, query), (str(search_button["name"]), "")],
    )


def _page_number(soup: BeautifulSoup, input_prefix: str, default: int) -> int:
    control = soup.select_one(f"input[id^='{input_prefix}']")
    try:
        return int(str(control.get("value"))) if isinstance(control, Tag) else default
    except (TypeError, ValueError):
        return default


def _submit_page(
    session: requests.Session,
    soup: BeautifulSoup,
    page_index: int,
) -> tuple[requests.Response, BeautifulSoup]:
    table = soup.select_one("table[id$='_grid_grd']")
    if not isinstance(table, Tag) or not table.get("id"):
        raise EdfPortalFormatError("Grille des appels d'offres EDF introuvable.")
    return _post_form(
        session,
        soup,
        extra_values=[
            ("__EVENTTARGET", str(table["id"])),
            ("__EVENTARGUMENT", f"Page|{page_index}"),
        ],
    )


def _field_kind(header_id: str, label: str) -> str | None:
    header = _normalize(header_id)
    text = _normalize(label)
    compact_id = re.sub(r"[^a-z0-9]", "", header_id.lower())

    if "bpmcode" in compact_id or text in {"code", "reference", "numero", "n consultation"}:
        return "reference"
    if "collabel" in compact_id or any(token in text for token in ("libelle", "intitule", "titre", "objet", "label")):
        return "title"
    if "colpubbegindate" in compact_id or ("publication" in text and any(token in text for token in ("debut", "date"))):
        return "publication_date"
    if "colbegindate" in compact_id or text in {"debut", "date de debut", "begin", "begin utc 7"}:
        return "start_date"
    if "colenddate" in compact_id or text in {"fin", "date de fin", "end", "date limite", "echeance"}:
        return "end_date"
    if "colfamily" in compact_id or any(token in text for token in ("famille", "categorie", "segment", "commodity")):
        return "category"
    if "statuscode" in compact_id or text in {"statut", "status"}:
        return "status"
    if any(token in text for token in ("acheteur", "entite", "agency", "organisation")):
        return "buyer"
    return None


def _extract_records(soup: BeautifulSoup) -> list[dict[str, Any]]:
    table = soup.select_one("table[id$='_grid_grd']")
    if not isinstance(table, Tag):
        raise EdfPortalFormatError("Grille des appels d'offres EDF introuvable.")

    headers: list[tuple[str, str, str | None]] = []
    for index, th in enumerate(table.select("thead tr:first-child > th")):
        label = " ".join(th.get_text(" ", strip=True).split()) or f"Colonne {index + 1}"
        headers.append((label, str(th.get("id") or ""), _field_kind(str(th.get("id") or ""), label)))

    records: list[dict[str, Any]] = []
    for row in table.select("tbody > tr[data-id]"):
        cells = row.select(":scope > td")
        if not cells:
            continue

        record: dict[str, Any] = {
            "row_id": str(row.get("data-id") or "").strip(),
            "fields": [],
        }
        for index, cell in enumerate(cells):
            label, _header_id, kind = headers[index] if index < len(headers) else (f"Colonne {index + 1}", "", None)
            value = " ".join(cell.get_text(" ", strip=True).split())
            if value:
                record["fields"].append((label, value))
            if kind and value and not record.get(kind):
                record[kind] = value

        manage_link = row.select_one("a[iv-action='manage'][href]") or row.select_one("a[href*='/bpm/'][href]")
        if isinstance(manage_link, Tag):
            record["link"] = urljoin(BASE_URL, str(manage_link.get("href") or ""))
        elif record["row_id"]:
            record["link"] = f"{BASE_URL}/page.aspx/fr/bpm/process_manage_extranet/{record['row_id']}"

        if record.get("link"):
            records.append(record)
    return records


def _parse_portal_date(value: str | None) -> date | None:
    raw = " ".join(str(value or "").strip().split())
    if not raw:
        return None
    raw = re.sub(r"\s+(UTC|GMT)([+-]\d+(?::\d+)?)?$", "", raw, flags=re.IGNORECASE)
    candidates = [raw, raw.split(" ", 1)[0]]
    formats = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
    )
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _record_in_period(record: dict[str, Any], minimum: date, maximum: date) -> bool:
    publication_date = _parse_portal_date(record.get("publication_date") or record.get("start_date"))
    # Ne pas perdre un AO si EDF retire/renomme sa colonne de publication : l'IA
    # recevra quand même la ligne et la page signalera un changement de format si la grille disparaît.
    return publication_date is None or minimum <= publication_date <= maximum


def _record_to_raw_text(record: dict[str, Any]) -> str:
    lines = ["Source: Portail fournisseurs EDF"]
    seen: set[tuple[str, str]] = set()
    for label, value in record.get("fields", []):
        pair = (str(label), str(value))
        if pair not in seen:
            lines.append(f"{pair[0]}: {pair[1]}")
            seen.add(pair)
    if record.get("link"):
        lines.append(f"URL: {record['link']}")
    return "\n".join(lines)


def scrape_edf_into_raw(
    search_id: int,
    mots_recherche: list,
    sess,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> None:
    """Interroge la liste publique Ivalua d'EDF et alimente les raws Argos."""
    _ = sess
    date_pub_max = date_pub_max or date.today()
    date_pub_min = date_pub_min or (date_pub_max - timedelta(days=7))

    nb_inserts = 0
    liens_uniques: set[str] = set()
    recherches_limitees: list[dict[str, Any]] = []

    with _new_session() as session:
        _ensure_robots_allowed(session)
        for mots in mots_recherche:
            query = " ".join(mots).strip() if isinstance(mots, list) else str(mots).strip()
            if not query:
                continue

            _response, soup = _fetch_page(session)
            _response, soup = _submit_search(session, soup, query)
            max_page_index = _page_number(soup, "maxpageindex", 0)
            page_index = _page_number(soup, "hdnCurrentPageIndex", 0)
            nb_offres_lues = 0
            nb_inserts_pour_recherche = 0
            limite_atteinte = False

            while True:
                records = _extract_records(soup)
                for record in records:
                    nb_offres_lues += 1
                    if _record_in_period(record, date_pub_min, date_pub_max):
                        link = str(record["link"])
                        if link not in liens_uniques and not raw_lien_existe(search_id, link):
                            inserer_raw_recherche(
                                search_id=search_id,
                                source="edf",
                                mot_cle=query,
                                html_contenu=_record_to_raw_text(record),
                                lien=link,
                            )
                            liens_uniques.add(link)
                            nb_inserts += 1
                            nb_inserts_pour_recherche += 1

                    if nb_offres_lues >= MAX_OFFRES_PAR_RECHERCHE:
                        limite_atteinte = True
                        break

                if limite_atteinte or page_index >= max_page_index or not records:
                    break
                page_index += 1
                _response, soup = _submit_page(session, soup, page_index)

            if limite_atteinte:
                recherches_limitees.append(
                    {
                        "recherche": query,
                        "nb_offres_lues": nb_offres_lues,
                        "nb_inserts": nb_inserts_pour_recherche,
                        "seuil": MAX_OFFRES_PAR_RECHERCHE,
                    }
                )

    if recherches_limitees:
        append_recherche_job_warning(
            search_id,
            {
                "type": "pagination_limit",
                "severity": "warning",
                "source": "edf",
                "message": "Limite EDF atteinte pour certaines recherches trop larges.",
                "limited_searches": recherches_limitees,
            },
        )
    increment_recherche_job_counts(search_id, nb_trouves_delta=nb_inserts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with _new_session() as debug_session:
        response, debug_soup = _fetch_page(debug_session)
        print(response.url)
        print(f"Lignes visibles: {len(_extract_records(debug_soup))}")
