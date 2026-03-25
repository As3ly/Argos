"""Test intelligent des limites anti-bot FranceMarches.

Objectifs:
- Reprendre le même profil réseau que ``scrap_francemarche.py`` (proxy, headers, cookies de session).
- Mesurer les limites de requêtes/minute (RPM) sur:
  1) le moteur de recherche,
  2) les pages d'articles (avis).
- Comparer des variantes de headers pour identifier les profils plus/moins stables.

Exemple:
    python backend/Scrapers/test_limit_bot.py \
        --query "structure essais" \
        --search-rpm "6,12,20,30" \
        --article-rpm "6,12,20" \
        --article-sample-size 30
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


# Permet l'import de backend/inspect_db.py quand le script est lancé depuis la racine.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


try:
    from scrap_francemarche import (
        build_francemarche_session,
        extraire_liens_offres_frmar,
        generer_url,
        headers as BASE_HEADERS,
    )
except Exception as exc:  # pragma: no cover - script utilitaire
    raise SystemExit(f"Import impossible du scraper historique: {exc}")


DATADOME_MARKERS = [
    "please enable js and disable any ad blocker",
    "captcha-delivery.com",
    "x-datadome",
    "datadome",
]


@dataclass(slots=True)
class RequestResult:
    ok: bool
    status: int | None
    is_challenge: bool
    duration_s: float
    error: str | None = None


@dataclass(slots=True)
class StepReport:
    endpoint: str
    profile: str
    rpm_target: int
    total_requests: int
    success_count: int
    http_403_count: int
    challenge_count: int
    network_error_count: int
    avg_latency_s: float
    p95_latency_s: float
    success_rate: float

    @property
    def block_rate(self) -> float:
        blocked = self.http_403_count + self.challenge_count + self.network_error_count
        return blocked / self.total_requests if self.total_requests else 1.0


# Variantes intéressantes pour comparer contre le profil exact du scraper.
HEADER_VARIANTS: dict[str, dict[str, str]] = {
    "baseline": dict(BASE_HEADERS),
    "no_client_hints": {
        k: v
        for k, v in BASE_HEADERS.items()
        if not k.lower().startswith("sec-ch-")
    },
    "chrome_like_ua": {
        **BASE_HEADERS,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
        "sec-ch-ua-full-version-list": (
            '"Not(A:Brand";v="8.0.0.0", '
            '"Chromium";v="144.0.7559.97", '
            '"Google Chrome";v="144.0.7559.97"'
        ),
    },
}


def has_antibot_markers(html: str) -> bool:
    if not html:
        return False
    html_low = html.lower()
    return any(marker in html_low for marker in DATADOME_MARKERS)


def parse_rpm_list(raw: str) -> list[int]:
    values = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        rpm = int(chunk)
        if rpm <= 0:
            raise ValueError(f"RPM invalide: {rpm}")
        values.append(rpm)
    if not values:
        raise ValueError("Liste RPM vide")
    return sorted(set(values))


def configure_profile(session: requests.Session, profile_name: str) -> None:
    session.headers.clear()
    session.headers.update(HEADER_VARIANTS[profile_name])


def request_once(session: requests.Session, url: str, timeout_s: float) -> RequestResult:
    t0 = time.perf_counter()
    try:
        response = session.get(url, timeout=timeout_s)
        dt = time.perf_counter() - t0
        html = response.text or ""
        is_challenge = has_antibot_markers(html)
        ok = response.ok and not is_challenge and response.status_code != 403
        return RequestResult(
            ok=ok,
            status=response.status_code,
            is_challenge=is_challenge,
            duration_s=dt,
            error=None,
        )
    except requests.RequestException as exc:
        dt = time.perf_counter() - t0
        return RequestResult(
            ok=False,
            status=None,
            is_challenge=False,
            duration_s=dt,
            error=str(exc),
        )


def collect_article_urls(
    session: requests.Session,
    query: str,
    pages_to_scan: int,
    article_sample_size: int,
    timeout_s: float,
) -> list[str]:
    mots = query.split()
    found: list[str] = []
    seen: set[str] = set()

    for page in range(1, pages_to_scan + 1):
        url = generer_url(mots, page=page)
        try:
            response = session.get(url, timeout=timeout_s)
        except requests.RequestException:
            continue

        if response.status_code >= 400:
            continue
        html = response.text or ""
        if has_antibot_markers(html):
            continue

        links = extraire_liens_offres_frmar(html, mots)
        for _, link in links:
            if link not in seen:
                seen.add(link)
                found.append(link)
            if len(found) >= article_sample_size:
                return found

    return found


def run_rate_step(
    session: requests.Session,
    endpoint: str,
    profile_name: str,
    rpm_target: int,
    urls: list[str],
    timeout_s: float,
) -> StepReport:
    total_requests = max(1, rpm_target)
    interval_s = 60.0 / rpm_target
    results: list[RequestResult] = []

    for i in range(total_requests):
        planned_ts = time.perf_counter() + interval_s
        url = urls[i % len(urls)]
        result = request_once(session, url, timeout_s=timeout_s)
        results.append(result)

        remaining = planned_ts - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)

    durations = [r.duration_s for r in results] or [0.0]
    success_count = sum(1 for r in results if r.ok)
    http_403_count = sum(1 for r in results if r.status == 403)
    challenge_count = sum(1 for r in results if r.is_challenge)
    network_error_count = sum(1 for r in results if r.error is not None)

    return StepReport(
        endpoint=endpoint,
        profile=profile_name,
        rpm_target=rpm_target,
        total_requests=total_requests,
        success_count=success_count,
        http_403_count=http_403_count,
        challenge_count=challenge_count,
        network_error_count=network_error_count,
        avg_latency_s=statistics.mean(durations),
        p95_latency_s=statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
        success_rate=success_count / total_requests,
    )


def pick_recommended_rpm(reports: list[StepReport]) -> int:
    valid = [
        report
        for report in reports
        if report.success_rate >= 0.95 and report.block_rate <= 0.05
    ]
    if valid:
        return max(report.rpm_target for report in valid)
    return 0


def print_detailed_report(endpoint: str, profile_reports: dict[str, list[StepReport]]) -> None:
    print(f"\n========== RAPPORT {endpoint.upper()} ==========")
    for profile_name, reports in profile_reports.items():
        print(f"\n--- Profil headers: {profile_name} ---")
        print(
            "rpm | ok/total | success% | blocks% | 403 | challenge | net_err | "
            "lat_moy(s) | lat_p95(s)"
        )
        for r in sorted(reports, key=lambda x: x.rpm_target):
            print(
                f"{r.rpm_target:>3} | {r.success_count:>3}/{r.total_requests:<3} | "
                f"{r.success_rate:>7.2%} | {r.block_rate:>7.2%} | "
                f"{r.http_403_count:>3} | {r.challenge_count:>9} | {r.network_error_count:>7} | "
                f"{r.avg_latency_s:>10.2f} | {r.p95_latency_s:>9.2f}"
            )

        reco = pick_recommended_rpm(reports)
        if reco > 0:
            print(f"=> Recommandation profil '{profile_name}': ~{reco} requêtes/min stable.")
        else:
            print(
                "=> Recommandation profil '{profile_name}': aucune cadence stable "
                "selon les critères (>=95% succès, <=5% blocage)."
            )


def run_limits_benchmark(
    query: str,
    search_rpms: list[int],
    article_rpms: list[int],
    article_sample_size: int,
    seed_pages: int,
    timeout_s: float,
) -> dict[str, Any]:
    all_reports: dict[str, dict[str, list[StepReport]]] = {
        "search": {profile: [] for profile in HEADER_VARIANTS},
        "article": {profile: [] for profile in HEADER_VARIANTS},
    }

    # URLs de recherche (même pattern que le scraper)
    mots = query.split()
    search_urls = [generer_url(mots, page=i + 1) for i in range(max(search_rpms))]

    # Collecte de pages d'articles avec le profil baseline.
    baseline_sess = build_francemarche_session()
    configure_profile(baseline_sess, "baseline")
    article_urls = collect_article_urls(
        session=baseline_sess,
        query=query,
        pages_to_scan=max(1, seed_pages),
        article_sample_size=max(1, article_sample_size),
        timeout_s=timeout_s,
    )

    if not article_urls:
        raise RuntimeError(
            "Impossible de collecter des URLs d'articles. "
            "Augmente --seed-pages ou vérifie le réseau/proxy."
        )

    print(f"[info] URLs articles collectées: {len(article_urls)}")

    for profile_name in HEADER_VARIANTS:
        session = build_francemarche_session()
        configure_profile(session, profile_name)

        print(f"\n[info] Démarrage des tests profil={profile_name}")

        for rpm in search_rpms:
            report = run_rate_step(
                session=session,
                endpoint="search",
                profile_name=profile_name,
                rpm_target=rpm,
                urls=search_urls,
                timeout_s=timeout_s,
            )
            all_reports["search"][profile_name].append(report)
            print(
                f"  [search] rpm={rpm} success={report.success_rate:.1%} "
                f"block={report.block_rate:.1%}"
            )

        for rpm in article_rpms:
            report = run_rate_step(
                session=session,
                endpoint="article",
                profile_name=profile_name,
                rpm_target=rpm,
                urls=article_urls,
                timeout_s=timeout_s,
            )
            all_reports["article"][profile_name].append(report)
            print(
                f"  [article] rpm={rpm} success={report.success_rate:.1%} "
                f"block={report.block_rate:.1%}"
            )

    print_detailed_report("search", all_reports["search"])
    print_detailed_report("article", all_reports["article"])

    return {
        endpoint: {
            profile: [r.__dict__ | {"block_rate": r.block_rate} for r in reports]
            for profile, reports in profiles.items()
        }
        for endpoint, profiles in all_reports.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Test intelligent de limites anti-bot FranceMarches")
    parser.add_argument("--query", default="structure essais")
    parser.add_argument("--search-rpm", default="6,12,20,30")
    parser.add_argument("--article-rpm", default="6,12,20")
    parser.add_argument("--seed-pages", type=int, default=5)
    parser.add_argument("--article-sample-size", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--json-report",
        default="",
        help="Chemin de sortie JSON optionnel pour stocker le rapport détaillé.",
    )
    args = parser.parse_args()

    search_rpms = parse_rpm_list(args.search_rpm)
    article_rpms = parse_rpm_list(args.article_rpm)

    report = run_limits_benchmark(
        query=args.query,
        search_rpms=search_rpms,
        article_rpms=article_rpms,
        article_sample_size=args.article_sample_size,
        seed_pages=args.seed_pages,
        timeout_s=args.timeout,
    )

    if args.json_report:
        out = Path(args.json_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[info] Rapport JSON écrit: {out}")


if __name__ == "__main__":
    main()
