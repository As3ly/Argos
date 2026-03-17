"""Scraper FranceMarches plus robuste face aux blocages HTTP 403.

Objectifs:
- Éviter le mode "bourrin" : pacing adaptatif + retry intelligent.
- Rotation de profils de headers réalistes.
- Détection explicite des pages de challenge Datadome / antibot.
- Garder la même logique d'extraction HTML que le scraper actuel.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import truststore
from bs4 import BeautifulSoup

import framatome
from inspect_db import inserer_raw_recherche, raw_lien_existe, update_recherche_job


truststore.inject_into_ssl()

proxies = {
    "http": framatome.HTTP_PROXY,
    "https": framatome.HTTPS_PROXY,
}


@dataclass
class ScrapeConfig:
    timeout_s: int = 20
    retries: int = 5
    base_delay_s: float = 1.3
    jitter_min_s: float = 0.4
    jitter_max_s: float = 1.6
    max_blocked_pages: int = 3
    rotate_after_consecutive_403: int = 3


HEADER_TEMPLATE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-device-memory": "8",
    "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-full-version-list": '"Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.97", "Microsoft Edge";v="144.0.3719.92"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


HEADER_PROFILES = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
        ),
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-full-version-list": (
            '"Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.97", '
            '"Microsoft Edge";v="144.0.3719.92"'
        ),
        "sec-ch-ua-arch": '"x86"',
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "sec-ch-device-memory": "8",
        "Sec-Fetch-Site": "none",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
        ),
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-full-version-list": (
            '"Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.101", '
            '"Microsoft Edge";v="144.0.3721.6"'
        ),
        "sec-ch-ua-arch": '"x86"',
        "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8,en-US;q=0.6",
        "sec-ch-device-memory": "16",
        "Sec-Fetch-Site": "same-origin",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
        ),
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-full-version-list": (
            '"Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.105", '
            '"Microsoft Edge";v="144.0.3723.0"'
        ),
        "sec-ch-ua-arch": '"x86"',
        "Accept-Language": "fr,fr-FR;q=0.9,en-GB;q=0.7,en-US;q=0.6",
        "sec-ch-device-memory": "8",
        "Sec-Fetch-Site": "none",
    },
]


def _is_search_request(url: str) -> bool:
    return urlparse(url).path == "/recherche"


def _is_initial_search_page(url: str) -> bool:
    if not _is_search_request(url):
        return False
    page_values = parse_qs(urlparse(url).query).get("page", ["1"])
    return page_values[0] == "1"


def _build_stable_header_profile() -> dict[str, str]:
    profile = random.choice(HEADER_PROFILES)

    headers = HEADER_TEMPLATE.copy()
    headers.update(
        {
            "Accept-Language": profile["Accept-Language"],
            "sec-ch-ua": profile["sec-ch-ua"],
            "sec-ch-ua-platform": profile["sec-ch-ua-platform"],
            "sec-ch-ua-full-version-list": profile["sec-ch-ua-full-version-list"],
            "sec-ch-ua-arch": profile["sec-ch-ua-arch"],
            "User-Agent": profile["User-Agent"],
        }
    )

    if random.random() < 0.35:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"

    if "sec-ch-device-memory" in profile:
        headers["sec-ch-device-memory"] = profile["sec-ch-device-memory"]
    if "Sec-Fetch-Site" in profile:
        headers["Sec-Fetch-Site"] = profile["Sec-Fetch-Site"]

    return headers


def _build_request_headers(
    base_headers: dict[str, str],
    *,
    url: str | None = None,
    is_first_request: bool = False,
) -> dict[str, str]:
    headers = base_headers.copy()

    if is_first_request:
        headers["Sec-Fetch-Site"] = "none"

    if not is_first_request and url and _is_search_request(url) and not _is_initial_search_page(url):
        headers["Referer"] = "https://www.francemarches.com/recherche"

    return headers


def _rotate_session_profile(session: requests.Session) -> None:
    session._argos_header_profile = _build_stable_header_profile()


def build_resilient_session(datadome_cookie: str | None = None) -> requests.Session:
    sess = requests.Session()
    sess.proxies = proxies
    _rotate_session_profile(sess)
    sess._argos_first_navigation_done = False
    sess._argos_consecutive_403 = 0
    sess.headers.clear()
    sess.headers.update(_build_request_headers(sess._argos_header_profile, is_first_request=True))

    cookie = datadome_cookie or os.getenv("FM_DATADOME_COOKIE")
    if cookie:
        sess.cookies.set("datadome", cookie, domain=".francemarches.com", path="/")

    return sess


def generer_url(
    mots: Iterable[str],
    ordre: str = "date-cloture-desc",
    page: int = 1,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> str:
    base_url = "https://www.francemarches.com/recherche"

    today = date.today()
    if date_pub_max is None:
        date_pub_max = today
    if date_pub_min is None:
        date_pub_min = date_pub_max - timedelta(days=7)

    date_range = f"{date_pub_min:%d/%m/%Y} - {date_pub_max:%d/%m/%Y}"

    params = {
        "q": " ".join(mots),
        "date-publication": date_range,
        "etat": "en-cours",
        "ordre": ordre,
        "page": page,
    }
    return f"{base_url}?{urlencode(params)}"


def _looks_like_antibot_page(html: str) -> bool:
    if not html:
        return False
    markers = [
        "Please enable JS and disable any ad blocker",
        "captcha-delivery.com",
        "x-datadome",
        "datadome",
    ]
    html_low = html.lower()
    return any(marker.lower() in html_low for marker in markers)


def resilient_get(url: str, session: requests.Session, cfg: ScrapeConfig) -> str:
    if not hasattr(session, "_argos_header_profile"):
        _rotate_session_profile(session)
    if not hasattr(session, "_argos_first_navigation_done"):
        session._argos_first_navigation_done = False
    if not hasattr(session, "_argos_consecutive_403"):
        session._argos_consecutive_403 = 0

    for attempt in range(1, cfg.retries + 1):
        is_first_request = not getattr(session, "_argos_first_navigation_done", False)
        session.headers.clear()
        session.headers.update(
            _build_request_headers(session._argos_header_profile, url=url, is_first_request=is_first_request)
        )
        try:
            response = session.get(url, timeout=cfg.timeout_s)
            session._argos_first_navigation_done = True
        except requests.RequestException as exc:
            wait_s = min(20.0, cfg.base_delay_s * (2 ** (attempt - 1))) + random.uniform(0.0, 1.2)
            print(f"[retry] Erreur réseau sur tentative {attempt}/{cfg.retries}: {exc}. Pause {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        blocked = response.status_code == 403 or _looks_like_antibot_page(response.text)
        if blocked:
            if response.status_code == 403:
                session._argos_consecutive_403 += 1
                if session._argos_consecutive_403 >= cfg.rotate_after_consecutive_403:
                    _rotate_session_profile(session)
                    session._argos_consecutive_403 = 0
                    print("[403] Rotation du profil de headers après blocages consécutifs")
            else:
                session._argos_consecutive_403 = 0

            wait_s = min(45.0, cfg.base_delay_s * (2 ** attempt)) + random.uniform(2.0, 6.0)
            print(f"[403] Bloqué (tentative {attempt}/{cfg.retries}) - pause longue {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        session._argos_consecutive_403 = 0

        if response.status_code >= 400:
            print(f"[warn] HTTP {response.status_code} sur {url}")
            return ""

        return response.text

    print(f"[stop] Impossible de récupérer la page après {cfg.retries} tentatives: {url}")
    return ""


def extraire_liens_offres_frmar(html_contenu: str, mot_cle: list[str]) -> list[list[str]]:
    soup = BeautifulSoup(html_contenu, "html.parser")
    liens: list[list[str]] = []
    conteneur_principal = soup.find("div", id="results")

    if not conteneur_principal:
        return liens

    for a in conteneur_principal.find_all("a", class_="offerResult"):
        lien = a.get("href")
        if not lien:
            continue
        if lien.startswith("/"):
            lien = f"https://www.francemarches.com{lien}"
        liens.append([" ".join(mot_cle), lien])

    return liens


def extraire_html_AO_frmar(lurl: str, sess_objct: requests.Session, cfg: ScrapeConfig) -> str | None:
    html_contenu = resilient_get(lurl, sess_objct, cfg)
    if not html_contenu:
        return None

    soup = BeautifulSoup(html_contenu, "html.parser")
    principal = soup.select_one("div.avis__content.avis__block")
    sidebar = soup.select_one("div.avisSidebarInfos.avis__block")

    if not principal and not sidebar:
        return "Aucun avis d'appel d'offre n'a été détécté sur cette page."

    for tag in (principal, sidebar):
        if tag is None:
            continue
        for t in tag(["script", "style", "noscript"]):
            t.decompose()
        for br in tag.find_all("br"):
            br.replace_with("\n")
        for li in tag.find_all("li"):
            li.insert_before("\n- ")
        for dl in tag.find_all("dl"):
            lignes = []
            for dt in dl.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                cle = dt.get_text(" ", strip=True)
                val = dd.get_text(" ", strip=True) if dd else ""
                lignes.append(f"{cle} : {val}")
            dl.replace_with("\n".join(lignes))

    texte_principal = principal.get_text(separator="\n", strip=True) if principal else ""
    texte_sidebar = sidebar.get_text(separator="\n", strip=True) if sidebar else ""
    combined = f"{texte_principal}\n\n{texte_sidebar}" if texte_principal and texte_sidebar else (texte_principal or texte_sidebar)

    if combined:
        combined = re.sub(r"\n{3,}", "\n\n", combined).strip()

    return combined or None


def scrape_francemarche_into_raw_robuste(
    search_id: int,
    mots_recherche: list[list[str]],
    sess: requests.Session,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
    cfg: ScrapeConfig | None = None,
) -> None:
    cfg = cfg or ScrapeConfig()
    liens_finaux: list[list[str]] = []

    for mots in mots_recherche:
        blocked_pages = 0
        page = 1

        while True:
            cible = generer_url(mots, page=page, date_pub_min=date_pub_min, date_pub_max=date_pub_max)
            print(f"[search] {cible}")
            html = resilient_get(cible, sess, cfg)

            if not html:
                blocked_pages += 1
                if blocked_pages >= cfg.max_blocked_pages:
                    print(f"[stop] Trop de pages bloquées pour {' '.join(mots)}")
                    break
                page += 1
                continue

            blocked_pages = 0
            soup = BeautifulSoup(html, "html.parser")
            if soup.find("div", class_="messageCloture"):
                break

            liens = extraire_liens_offres_frmar(html, mots)
            if not liens:
                break

            liens_finaux.extend(liens)
            page += 1
            time.sleep(cfg.base_delay_s + random.uniform(cfg.jitter_min_s, cfg.jitter_max_s))

    seen = set()
    liens_uniques = []
    for mot, lien in liens_finaux:
        if lien in seen:
            continue
        liens_uniques.append([mot, lien])
        seen.add(lien)

    update_recherche_job(search_id, nb_trouves=len(liens_uniques))

    for i, (mot, lien) in enumerate(liens_uniques, start=1):
        if raw_lien_existe(search_id, lien):
            continue

        texte_clean = extraire_html_AO_frmar(lien, sess, cfg)
        inserer_raw_recherche(search_id=search_id, mot_cle=mot, html_contenu=texte_clean, lien=lien)

        if i % 10 == 0:
            print("[info] Scrapping robuste...", round(i * 100 / len(liens_uniques), 2), "%")


def plan_anti_blocage() -> list[str]:
    """Plan synthétique à appliquer avant un scraping grand volume."""
    return [
        "Démarrer avec des lots de pages modestes (10-20 pages), mesurer le taux de 403 et ajuster le pacing.",
        "Utiliser une session persistante + profil de headers stable; ne le faire tourner qu'après N erreurs 403 consécutives.",
        "Détecter explicitement Datadome/antibot et appliquer backoff exponentiel long (pas de retry agressif).",
        "Répartir la charge temporellement (batching) plutôt qu'un pic continu.",
        "Superviser en continu: ratio 2xx/403, temps moyen, pages vides, puis couper automatiquement en cas d'emballement.",
    ]
