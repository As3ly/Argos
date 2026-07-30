from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import requests
from bs4 import BeautifulSoup

import db.repository as repository
import Scrapers
from Scrapers.scrap_edf import (
    EdfCaptchaRequired,
    EdfAuthorizedSessionConfigError,
    EdfRobotsDenied,
    _captcha_is_present,
    _configure_authorized_session,
    _ensure_robots_allowed,
    _extract_records,
    _parse_portal_date,
    _record_in_period,
)


GRID_HTML = """
<html><body>
  <table id="body_x_grid_grd">
    <thead><tr>
      <th>Action</th>
      <th id="body_x_grid_grd__ctl0_txtBpmCodeCalculated">Code</th>
      <th id="body_x_grid_grd__ctl0_colLabel">Libellé</th>
      <th id="body_x_grid_grd__ctl0_colFamily">Famille</th>
      <th id="body_x_grid_grd__ctl0_colPubBeginDate">Date de publication</th>
      <th id="body_x_grid_grd__ctl0_colEndDate">Date limite</th>
    </tr></thead>
    <tbody><tr data-id="4242">
      <td><a iv-action="manage" href="/page.aspx/fr/bpm/process_manage_extranet/4242">Ouvrir</a></td>
      <td>RFx-2026-42</td>
      <td>Maintenance prédictive des moteurs</td>
      <td>Ingénierie</td>
      <td>10/07/2026 09:30</td>
      <td>31/07/2026 17:00</td>
    </tr></tbody>
  </table>
</body></html>
"""


class EdfHtmlTests(unittest.TestCase):
    def test_extracts_ivalua_grid(self) -> None:
        records = _extract_records(BeautifulSoup(GRID_HTML, "html.parser"))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["reference"], "RFx-2026-42")
        self.assertEqual(records[0]["title"], "Maintenance prédictive des moteurs")
        self.assertEqual(records[0]["publication_date"], "10/07/2026 09:30")
        self.assertTrue(records[0]["link"].endswith("/4242"))

    def test_parses_french_and_ivalua_dates(self) -> None:
        self.assertEqual(_parse_portal_date("10/07/2026 09:30"), date(2026, 7, 10))
        self.assertEqual(_parse_portal_date("7/10/2026 9:30:00 AM"), date(2026, 7, 10))
        record = {"publication_date": "10/07/2026 09:30"}
        self.assertTrue(_record_in_period(record, date(2026, 7, 1), date(2026, 7, 10)))
        self.assertFalse(_record_in_period(record, date(2026, 7, 11), date(2026, 7, 20)))

    def test_detects_browser_check_captcha(self) -> None:
        response = requests.Response()
        response.status_code = 200
        response.url = "https://pha2.edf.com/page.aspx/fr/bas/browser_check"
        response._content = b"<html><body><input name='captcha_response'></body></html>"
        soup = BeautifulSoup(response.content, "html.parser")

        self.assertTrue(_captcha_is_present(response, soup))

    def test_honors_robots_policy_without_explicit_authorization(self) -> None:
        response = requests.Response()
        response.status_code = 200
        response.url = "https://pha2.edf.com/robots.txt"
        response._content = b"User-agent: *\nDisallow: /\n"
        session = mock.Mock()
        session.get.return_value = response

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(EdfRobotsDenied):
                _ensure_robots_allowed(session)

    def test_explicit_owner_authorization_skips_robots_gate(self) -> None:
        session = mock.Mock()
        with mock.patch.dict("os.environ", {"ARGOS_EDF_SCRAPING_AUTHORIZED": "true"}, clear=True):
            _ensure_robots_allowed(session)
        session.get.assert_not_called()

    def test_prevalidated_session_requires_explicit_owner_authorization(self) -> None:
        session = requests.Session()
        env = {
            "ARGOS_EDF_CAPTCHA_MODE": "prevalidated_session",
            "ARGOS_EDF_AUTHORIZED_SESSION_COOKIE": "ASP.NET_SessionId=authorized-test",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(EdfAuthorizedSessionConfigError):
                _configure_authorized_session(session)

    def test_prevalidated_session_cookie_is_loaded_when_authorized(self) -> None:
        session = requests.Session()
        env = {
            "ARGOS_EDF_CAPTCHA_MODE": "prevalidated_session",
            "ARGOS_EDF_SCRAPING_AUTHORIZED": "true",
            "ARGOS_EDF_AUTHORIZED_SESSION_COOKIE": (
                "ASP.NET_SessionId=authorized-test; EDFBrowserCheck=validated"
            ),
        }
        with mock.patch.dict("os.environ", env, clear=True):
            _configure_authorized_session(session)

        self.assertEqual(session.cookies.get("ASP.NET_SessionId"), "authorized-test")
        self.assertEqual(session.cookies.get("EDFBrowserCheck"), "validated")


class NonBlockingOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = repository.DB_PATH
        repository.DB_PATH = Path(self.temp_dir.name) / "argos-test.db"
        repository.initialize_database()

    def tearDown(self) -> None:
        repository.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    def test_captcha_warning_is_persisted_and_next_source_runs(self) -> None:
        search_id = repository.create_recherche_job(requete="moteur", source="edf,ok")
        calls: list[str] = []

        def captcha_scraper(**_kwargs) -> None:
            raise EdfCaptchaRequired()

        def ok_scraper(**_kwargs) -> None:
            calls.append("ok")

        with (
            mock.patch.object(Scrapers, "SCRAPERS", [("edf", captcha_scraper), ("ok", ok_scraper)]),
            mock.patch.dict(Scrapers.SCRAPER_LABELS, {"ok": "Source test"}),
        ):
            errors = Scrapers.run_all_scrapers(
                search_id,
                [["moteur"]],
                date_pub_min=date(2026, 7, 1),
                date_pub_max=date(2026, 7, 10),
            )

        self.assertEqual(calls, ["ok"])
        self.assertEqual(len(errors), 1)
        job = next(repository.list_recherche_jobs(limit=1))
        warnings = json.loads(job["warnings_json"])
        self.assertEqual(warnings[0]["type"], "captcha_required")
        self.assertEqual(warnings[0]["source"], "edf")
        self.assertEqual(warnings[0]["severity"], "error")

    def test_append_warning_preserves_previous_sources(self) -> None:
        search_id = repository.create_recherche_job(requete="test")
        repository.append_recherche_job_warning(search_id, {"source": "boamp", "message": "première"})
        repository.append_recherche_job_warning(search_id, {"source": "edf", "message": "seconde"})

        job = next(repository.list_recherche_jobs(limit=1))
        warnings = json.loads(job["warnings_json"])
        self.assertEqual([item["source"] for item in warnings], ["boamp", "edf"])


if __name__ == "__main__":
    unittest.main()
