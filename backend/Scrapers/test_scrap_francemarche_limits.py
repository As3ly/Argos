"""Test de charge basique du scraper historique.

But: estimer les limites actuelles (pages récupérées vs pages vides/erreurs).
"""

from __future__ import annotations

import argparse
import sys
import statistics
import time
from pathlib import Path

import requests


# Permet l'import de backend/inspect_db.py quand le script est lancé depuis la racine.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


try:
    from scrap_francemarche import build_francemarche_session, generer_url
except Exception as exc:  # pragma: no cover - script utilitaire
    raise SystemExit(f"Import impossible du scraper historique: {exc}")


DATADOME_MARKERS = [
    "Please enable JS and disable any ad blocker",
    "captcha-delivery.com",
    "x-datadome",
    "datadome",
]


def has_datadome_markers(html: str) -> bool:
    if not html:
        return False
    html_low = html.lower()
    return any(marker.lower() in html_low for marker in DATADOME_MARKERS)


def run_benchmark(query: str, pages: int, delay_s: float) -> None:
    mots = query.split()
    sess = build_francemarche_session()

    durations = []
    status_2xx = 0
    status_403 = 0
    challenge_pages = 0
    profile_id = "historique-default"

    for page in range(1, pages + 1):
        url = generer_url(mots, page=page)
        t0 = time.perf_counter()
        status_code = None
        html = ""

        try:
            response = sess.get(url, timeout=10)
            status_code = response.status_code
            html = response.text
        except requests.RequestException as exc:
            print(f"[ERR] page={page} erreur_reseau={exc}")

        dt = time.perf_counter() - t0
        durations.append(dt)
        has_challenge = has_datadome_markers(html)

        if status_code is not None and 200 <= status_code < 300:
            status_2xx += 1
        if status_code == 403:
            status_403 += 1
        if has_challenge:
            challenge_pages += 1

        if html:
            print(
                f"[OK] page={page} status={status_code} datadome={has_challenge} "
                f"t={dt:.2f}s profile={profile_id} len={len(html)}"
            )
        else:
            print(
                f"[KO] page={page} status={status_code} datadome={has_challenge} "
                f"t={dt:.2f}s profile={profile_id} html vide"
            )

        time.sleep(delay_s)

    print("\n=== Résultat scraper historique ===")
    print(f"pages_testees={pages}")
    print(f"taux_2xx={status_2xx / pages:.2%}")
    print(f"taux_403={status_403 / pages:.2%}")
    print(f"taux_pages_challenge={challenge_pages / pages:.2%}")
    print(f"t_moyen_s={statistics.mean(durations):.2f}")
    print(f"t_mediane_s={statistics.median(durations):.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="structure essais")
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    run_benchmark(query=args.query, pages=args.pages, delay_s=args.delay)
