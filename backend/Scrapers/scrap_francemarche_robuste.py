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
from urllib.parse import urlencode

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


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

LANGS = [
    "fr-FR,fr;q=0.9,en;q=0.7",
    "fr-FR,fr;q=0.8,en-US;q=0.6,en;q=0.5",
    "fr,fr-FR;q=0.9,en-GB;q=0.6,en-US;q=0.5",
]


def _build_dynamic_headers() -> dict[str, str]:
    ua = random.choice(USER_AGENTS)
    lang = random.choice(LANGS)
    chromium_major = random.choice([123, 124, 125])

    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": lang,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": f'"Chromium";v="{chromium_major}", "Not.A/Brand";v="8"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": random.choice(['"Windows"', '"Linux"', '"macOS"']),
        "User-Agent": ua,
        "Referer": "https://www.francemarches.com/recherche",
    }


def build_resilient_session(datadome_cookie: str | None = None) -> requests.Session:
    sess = requests.Session()
    sess.proxies = proxies
    sess.headers.update(_build_dynamic_headers())

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
    for attempt in range(1, cfg.retries + 1):
        session.headers.update(_build_dynamic_headers())
        try:
            response = session.get(url, timeout=cfg.timeout_s)
        except requests.RequestException as exc:
            wait_s = min(20.0, cfg.base_delay_s * (2 ** (attempt - 1))) + random.uniform(0.0, 1.2)
            print(f"[retry] Erreur réseau sur tentative {attempt}/{cfg.retries}: {exc}. Pause {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

        blocked = response.status_code == 403 or _looks_like_antibot_page(response.text)
        if blocked:
            wait_s = min(45.0, cfg.base_delay_s * (2 ** attempt)) + random.uniform(2.0, 6.0)
            print(f"[403] Bloqué (tentative {attempt}/{cfg.retries}) - pause longue {wait_s:.1f}s")
            time.sleep(wait_s)
            continue

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
        "Utiliser une session persistante + rotation de headers réalistes à chaque requête.",
        "Détecter explicitement Datadome/antibot et appliquer backoff exponentiel long (pas de retry agressif).",
        "Répartir la charge temporellement (batching) plutôt qu'un pic continu.",
        "Superviser en continu: ratio 2xx/403, temps moyen, pages vides, puis couper automatiquement en cas d'emballement.",
    ]
