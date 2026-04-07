# scrap_francemarche.py
import time
import random
import re
import threading
from collections import deque

import requests
import truststore
import framatome

from urllib.parse import urlencode
from bs4 import BeautifulSoup
from datetime import date, timedelta

from db.repository import inserer_raw_recherche, raw_lien_existe, update_recherche_job


# ========================================================================
# CONFIG
# ========================================================================

proxies = {
    "http": framatome.HTTP_PROXY,
    "https": framatome.HTTPS_PROXY,
}

truststore.inject_into_ssl()

headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'fr,fr-FR;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0',
    'sec-ch-device-memory': '8',
    'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Microsoft Edge";v="144"',
    'sec-ch-ua-arch': '"x86"',
    'sec-ch-ua-full-version-list': '"Not(A:Brand";v="8.0.0.0", "Chromium";v="144.0.7559.97", "Microsoft Edge";v="144.0.3719.92"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

# ========================================================================
# RATE LIMITING GLOBAL
# ========================================================================

MAX_REQUESTS_PER_MINUTE = 100
RATE_WINDOW_SECONDS = 60.0

_request_timestamps = deque()
_rate_lock = threading.Lock()


def _wait_for_rate_limit() -> None:
    """
    Bloque jusqu'à ce qu'on puisse émettre une nouvelle requête
    sans dépasser MAX_REQUESTS_PER_MINUTE sur une fenêtre glissante de 60s.
    """
    while True:
        with _rate_lock:
            now = time.monotonic()

            # purge des timestamps hors fenêtre
            while _request_timestamps and (now - _request_timestamps[0]) >= RATE_WINDOW_SECONDS:
                _request_timestamps.popleft()

            if len(_request_timestamps) < MAX_REQUESTS_PER_MINUTE:
                _request_timestamps.append(now)
                return

            # temps d'attente avant que la plus vieille requête sorte de la fenêtre
            oldest = _request_timestamps[0]
            sleep_for = RATE_WINDOW_SECONDS - (now - oldest)

        # on dort hors lock
        sleep_for = max(sleep_for, 0.05)
        print(f"[rate-limit] plafond atteint ({MAX_REQUESTS_PER_MINUTE}/min), pause {sleep_for:.2f}s")
        time.sleep(sleep_for)


def build_francemarche_session() -> requests.Session:
    """Construit une session Requests configurée proxy + headers."""
    sess = requests.Session()
    sess.proxies = proxies
    sess.headers.update(headers)
    return sess


# ========================================================================
# FONCTIONS SCRAPING
# ========================================================================

def generer_url(mots, ordre="date-cloture-desc", page=1, date_pub_min: date | None = None, date_pub_max: date | None = None):
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


def recuperer_html(url, session_object):
    _wait_for_rate_limit()

    try:
        reponse = session_object.get(url, timeout=10)
        reponse.raise_for_status()
        return reponse.text

    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP : {url} -> {e}")
        return ""

    except requests.exceptions.RequestException as e:
        print(f"Erreur réseau : {url} -> {e}")
        return ""


def extraire_liens_offres_frmar(html_contenu, mot_cle):
    soup = BeautifulSoup(html_contenu, 'html.parser')
    liens = []

    conteneur_principal = soup.find('div', id='results')

    if conteneur_principal:
        balises_a = conteneur_principal.find_all('a', class_='offerResult')
        for a in balises_a:
            lien = a.get('href')
            if lien:
                if lien.startswith('/'):
                    lien = f"https://www.francemarches.com{lien}"
                liens.append([mot_cle, lien])
    else:
        print("Conteneur 'results' non trouvé.")

    return liens


def extraire_html_AO_frmar(lurl, sess_objct):
    html_contenu = recuperer_html(lurl, sess_objct)
    if not html_contenu:
        print(f"[Attention] HTML vide ou erreur réseau pour : {lurl}")
        return None

    soup = BeautifulSoup(html_contenu, 'html.parser')
    principal = soup.select_one("div.avis__content.avis__block")
    sidebar = soup.select_one("div.avisSidebarInfos.avis__block")

    if not principal and not sidebar:
        print(f"[Attention] Problème de parsing, ni bloc principal ni sidebar trouvés sur : {lurl}")
        return "Aucun avis d'appel d'offre n'a été détécté sur cette page."

    for tag in (principal, sidebar):
        if tag is None:
            continue
        for t in tag(["script", "style", "noscript"]):
            t.decompose()

    for tag in (principal, sidebar):
        if tag is None:
            continue
        for br in tag.find_all("br"):
            br.replace_with("\n")

    for tag in (principal, sidebar):
        if tag is None:
            continue
        for li in tag.find_all("li"):
            li.insert_before("\n- ")

    for tag in (principal, sidebar):
        if tag is None:
            continue
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

    if texte_principal and texte_sidebar:
        combined = f"{texte_principal}\n\n{texte_sidebar}"
    else:
        combined = texte_principal or texte_sidebar

    if combined:
        combined = re.sub(r"\n{3,}", "\n\n", combined).strip()

    if not combined:
        print(f"[Attention] Aucun texte exploitable après nettoyage pour : {lurl}")
        return None

    return combined


# ========================================================================
# FONCTION "FAÇADE"
# ========================================================================

def scrape_francemarche_into_raw(
    search_id: int,
    mots_recherche: list,
    sess: requests.Session,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None
) -> None:
    """
    Prend la liste de mots-clés, scrape FranceMarches, puis insère le texte
    nettoyé dans raw_recherches.
    Met aussi à jour nb_trouves dans recherches_jobs.
    """
    liens_finaux = []

    for mots in mots_recherche:
        flag = True
        i = 0
        while flag:
            cible = generer_url(mots, page=i + 1, date_pub_min=date_pub_min, date_pub_max=date_pub_max)
            print(cible)

            html = recuperer_html(cible, sess)

            # petit jitter facultatif, mais léger
            time.sleep(random.uniform(0.05, 0.2))

            soup = BeautifulSoup(html, 'html.parser')
            if soup.find('div', class_='messageCloture'):
                flag = False
                continue

            liens = extraire_liens_offres_frmar(html, mots)
            print(f"Nombre d'offres trouvées à la page {i + 1} pour la recherche {mots} : {len(liens)}")

            if not liens:
                print("Aucun lien trouvé sur cette page -> arrêt de la pagination pour cette recherche.")
                flag = False
                continue

            liens_finaux.extend(liens)
            i += 1

    seen = set()
    liens_uniques = []
    for mot, lien in liens_finaux:
        if lien not in seen:
            liens_uniques.append([mot, lien])
            seen.add(lien)

    update_recherche_job(search_id, nb_trouves=len(liens_uniques))

    for links in liens_uniques[:30]:
        print("Lien:", links)

    for i, (mot, lien) in enumerate(liens_uniques, start=1):
        if raw_lien_existe(search_id, lien):
            print(f"[info] Lien déjà présent, on saute : {lien}")
            continue

        texte_clean = extraire_html_AO_frmar(lien, sess)
        inserer_raw_recherche(
            search_id=search_id,
            source="francemarches",
            mot_cle=mot,
            html_contenu=texte_clean,
            lien=lien
        )

        if i % 10 == 0:
            print("[info] Scrapping des AO... Avancement :", round(i * 100 / len(liens_uniques), 2), "%")
