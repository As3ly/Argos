# scrap_francemarche.py
import time
import random
import re
import requests
import truststore
import framatome

from urllib.parse import urlencode
from bs4 import BeautifulSoup
from datetime import date, timedelta

from db.repository import inserer_raw_recherche, raw_lien_existe, update_recherche_job


# ========================================================================
# CONFIG (extrait de main.py)
# ========================================================================

proxies = {
    "http": framatome.HTTP_PROXY,
    "https": framatome.HTTPS_PROXY,
}

truststore.inject_into_ssl()

# Headers extrait de la requete sur Edge
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


def build_francemarche_session() -> requests.Session:
    """Construit une session Requests configurée proxy + headers, comme dans main.py."""
    sess = requests.Session()
    sess.proxies = proxies
    sess.headers.update(headers)
    return sess


# ========================================================================
# FONCTIONS SCRAPING (extraites de main.py)
# ========================================================================

def generer_url( mots, ordre="date-cloture-desc", page=1, date_pub_min: date | None = None, date_pub_max: date | None = None):
    base_url = "https://www.francemarches.com/recherche"

    # Defaults: dernière semaine (min = J-7, max = J)
    today = date.today()
    if date_pub_max is None:
        date_pub_max = today
    if date_pub_min is None:
        date_pub_min = date_pub_max - timedelta(days=7)

    # Format attendu: "20/02/2026 - 27/02/2026"
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
    try:
        reponse = session_object.get(url, timeout=10)
        reponse.raise_for_status()
        return reponse.text
    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP : {url} -> {e}")
        return ""  # On renvoie une chaîne vide pour ne pas faire planter la fonction


def extraire_liens_offres_frmar(html_contenu, mot_cle):
    soup = BeautifulSoup(html_contenu, 'html.parser')
    liens = []

    # On cible le conteneur principal
    conteneur_principal = soup.find('div', id='results')

    if conteneur_principal:
        # On cherche tous les <a> avec la classe 'offerResult'
        balises_a = conteneur_principal.find_all('a', class_='offerResult')
        for a in balises_a:
            lien = a.get('href')
            if lien:
                # On ajoute le domaine si c'est un lien relatif
                if lien.startswith('/'):
                    lien = f"https://www.francemarches.com{lien}"
                liens.append([mot_cle, lien])
    else:
        print("Conteneur 'results' non trouvé.")

    return liens


def extraire_html_AO_frmar(lurl, sess_objct):
    # récupération du HTML
    html_contenu = recuperer_html(lurl, sess_objct)
    if not html_contenu:
        print(f"[Attention] HTML vide ou erreur réseau pour : {lurl}")
        return None

    soup = BeautifulSoup(html_contenu, 'html.parser')
    principal = soup.select_one("div.avis__content.avis__block")  # + fallback possible si besoin
    sidebar = soup.select_one("div.avisSidebarInfos.avis__block")

    if not principal and not sidebar:
        print(f"[Attention] Problème de parsing, ni bloc principal ni sidebar trouvés sur : {lurl}")
        return "Aucun avis d'appel d'offre n'a été détécté sur cette page."

    # 1) Supprimer script/style/noscript dans principal et sidebar
    for tag in (principal, sidebar):
        if tag is None:
            continue
        for t in tag(["script", "style", "noscript"]):
            t.decompose()

    # 2) Remplacer <br> par des retours à la ligne
    for tag in (principal, sidebar):
        if tag is None:
            continue
        for br in tag.find_all("br"):
            br.replace_with("\n")

    # 3) Rendre les listes <li> lisibles avec une puce "- "
    for tag in (principal, sidebar):
        if tag is None:
            continue
        for li in tag.find_all("li"):
            li.insert_before("\n- ")

    # 4) Aplatir les <dl><dt><dd> en lignes "Clé : Valeur"
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

    # 5) Extraire le texte (principal → sidebar), puis normaliser
    texte_principal = principal.get_text(separator="\n", strip=True) if principal else ""
    texte_sidebar = sidebar.get_text(separator="\n", strip=True) if sidebar else ""

    # 6) Concaténation: toujours principal puis sidebar
    if texte_principal and texte_sidebar:
        combined = f"{texte_principal}\n\n{texte_sidebar}"
    else:
        combined = texte_principal or texte_sidebar

    # 7) Normalisation des sauts de ligne (compresser 3+ \n en 2)
    if combined:
        combined = re.sub(r"\n{3,}", "\n\n", combined).strip()

    if not combined:
        print(f"[Attention] Aucun texte exploitable après nettoyage pour : {lurl}")
        return None

    return combined


# ========================================================================
# FONCTION "FAÇADE" POUR TON MAIN
# ========================================================================

def scrape_francemarche_into_raw(search_id: int, mots_recherche: list, sess: requests.Session, date_pub_min: date | None= None, date_pub_max: date | None= None) -> None:
    """
    Prend la liste de mots-clés (format identique à main.py),
    scrappe FranceMarches, puis insère le texte nettoyé dans raw_recherches.
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
            time.sleep(1.5 + random.uniform(0.7, 1.8))

            # On vérifie qu'il y a des annonces sur cette page sinon on a fini
            soup = BeautifulSoup(html, 'html.parser')
            if soup.find('div', class_='messageCloture'):
                flag = False
                continue

            # On récupère tous les liens de la page
            liens = extraire_liens_offres_frmar(html, mots)
            print(f"Nombre d'offres trouvées à la page {i+1} pour la recherche {mots} : {len(liens)}")

            if not liens:  # sécurité si le message de clôture n’est pas présent
                print("Aucun lien trouvé sur cette page -> arrêt de la pagination pour cette recherche.")
                flag = False
                continue

            liens_finaux.extend(liens)
            i += 1

    # Dédoublonnage
    seen = set()
    liens_uniques = []
    for mot, lien in liens_finaux:
        if lien not in seen:
            liens_uniques.append([mot, lien])
            seen.add(lien)

    update_recherche_job(search_id, nb_trouves=len(liens_uniques))

    # Débogage (comme dans main.py)
    for links in liens_uniques[:30]:
        print("Lien:", links)

    # Récupération + insertion RAW
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
