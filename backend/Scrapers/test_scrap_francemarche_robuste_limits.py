"""Test de charge basique du scraper robuste (gestion anti-403)."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import requests


# Permet l'import de backend/inspect_db.py quand le script est lancé depuis la racine.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


try:
    from scrap_francemarche_robuste import (
        HEADER_PROFILES,
        ScrapeConfig,
        _looks_like_antibot_page,
        build_resilient_session,
        generer_url,
    )
except Exception as exc:  # pragma: no cover - script utilitaire
    raise SystemExit(f"Import impossible du scraper robuste: {exc}")


def current_profile_id(session: requests.Session) -> str:
    active = getattr(session, "_argos_header_profile", None)
    if not isinstance(active, dict):
        return "unknown"

    active_ua = active.get("User-Agent")
    for index, profile in enumerate(HEADER_PROFILES, start=1):
        if profile.get("User-Agent") == active_ua:
            return f"profile-{index}"
    return "profile-custom"


def run_benchmark(query: str, pages: int, base_delay_s: float) -> None:
    mots = query.split()
    cfg = ScrapeConfig(base_delay_s=base_delay_s)
    sess = build_resilient_session()

    durations: list[float] = []
    status_2xx = 0
    status_403 = 0
    challenge_pages = 0

    for page in range(1, pages + 1):
        url = generer_url(mots, page=page)
        t0 = time.perf_counter()
        status_code = None
        html = ""

        for attempt in range(1, cfg.retries + 1):
            sess.headers.clear()
            sess.headers.update(sess._argos_header_profile)
            try:
                response = sess.get(url, timeout=cfg.timeout_s)
                status_code = response.status_code
                html = response.text
            except requests.RequestException as exc:
                print(f"[ERR] page={page} tentative={attempt}/{cfg.retries} erreur_reseau={exc}")
                time.sleep(cfg.base_delay_s)
                continue

            if response.status_code == 403 or _looks_like_antibot_page(html):
                time.sleep(cfg.base_delay_s)
                continue

            break

        dt = time.perf_counter() - t0
        durations.append(dt)
        has_challenge = _looks_like_antibot_page(html)
        profile_id = current_profile_id(sess)

        if status_code is not None and 200 <= status_code < 300:
            status_2xx += 1
        if status_code == 403:
            status_403 += 1
        if has_challenge:
            challenge_pages += 1

        if html and status_code is not None and status_code < 400:
            print(
                f"[OK] page={page} status={status_code} datadome={has_challenge} "
                f"t={dt:.2f}s profile={profile_id} len={len(html)}"
            )
        else:
            print(
                f"[KO] page={page} status={status_code} datadome={has_challenge} "
                f"t={dt:.2f}s profile={profile_id} html vide (bloqué ou erreur)"
            )

        time.sleep(base_delay_s)

    print("\n=== Résultat scraper robuste ===")
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
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()
    run_benchmark(query=args.query, pages=args.pages, base_delay_s=args.delay)
