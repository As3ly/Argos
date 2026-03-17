"""Test de charge basique du scraper historique.

But: estimer les limites actuelles (pages récupérées vs pages vides/erreurs).
"""

from __future__ import annotations

import argparse
import sys
import statistics
import time
from pathlib import Path


# Permet l'import de backend/inspect_db.py quand le script est lancé depuis la racine.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


try:
    from scrap_francemarche import build_francemarche_session, generer_url, recuperer_html
except Exception as exc:  # pragma: no cover - script utilitaire
    raise SystemExit(f"Import impossible du scraper historique: {exc}")


def run_benchmark(query: str, pages: int, delay_s: float) -> None:
    mots = query.split()
    sess = build_francemarche_session()

    durations = []
    success = 0
    empty = 0

    for page in range(1, pages + 1):
        url = generer_url(mots, page=page)
        t0 = time.perf_counter()
        html = recuperer_html(url, sess)
        dt = time.perf_counter() - t0
        durations.append(dt)

        if html:
            success += 1
            print(f"[OK] page={page} t={dt:.2f}s len={len(html)}")
        else:
            empty += 1
            print(f"[KO] page={page} t={dt:.2f}s html vide")

        time.sleep(delay_s)

    print("\n=== Résultat scraper historique ===")
    print(f"pages_testees={pages}")
    print(f"success_html={success}")
    print(f"html_vides={empty}")
    print(f"t_moyen_s={statistics.mean(durations):.2f}")
    print(f"t_mediane_s={statistics.median(durations):.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="structure essais")
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    run_benchmark(query=args.query, pages=args.pages, delay_s=args.delay)
