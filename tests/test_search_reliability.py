from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import db.repository as repository
import pipeline
from Scrapers.scrap_boamp import _build_where_clause, _fetch_records
from Scrapers.scrap_ted import _build_ted_query, _fetch_notices
from proxy_config import get_requests_proxies


class _Response:
    ok = True
    status_code = 200
    url = "https://example.test/api"
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class ProxyConfigurationTests(unittest.TestCase):
    def test_no_hardcoded_proxy_is_used(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("proxy_config._framatome_proxy", return_value=None):
                self.assertEqual(get_requests_proxies(), {})

    def test_explicit_argos_proxy_is_preserved(self) -> None:
        env = {
            "ARGOS_HTTP_PROXY": "http://proxy.test:8080",
            "ARGOS_HTTPS_PROXY": "http://proxy.test:8080",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("proxy_config._framatome_proxy", return_value=None):
                self.assertEqual(get_requests_proxies(), {"http": env["ARGOS_HTTP_PROXY"], "https": env["ARGOS_HTTPS_PROXY"]})

    def test_explicit_argos_proxy_overrides_internal_module(self) -> None:
        with mock.patch.dict(os.environ, {"ARGOS_HTTPS_PROXY": "http://new.test:8080"}, clear=True):
            with mock.patch("proxy_config._framatome_proxy", return_value="http://old.test:8080"):
                self.assertEqual(get_requests_proxies()["https"], "http://new.test:8080")


class PublicApiContractTests(unittest.TestCase):
    def test_boamp_request_uses_current_dataset_and_date_syntax(self) -> None:
        session = mock.Mock()
        session.get.return_value = _Response({"results": [{"id": "26_1"}]})
        where = _build_where_clause(
            keywords='maintenance "moteur"',
            date_pub_min=date(2026, 7, 1),
            date_pub_max=date(2026, 7, 31),
        )
        rows = _fetch_records(session, where=where, offset=0, limit=10)
        self.assertEqual(rows, [{"id": "26_1"}])
        url = session.get.call_args.args[0]
        params = session.get.call_args.kwargs["params"]
        self.assertIn("/catalog/datasets/boamp/records", url)
        self.assertIn("dateparution >= date'2026-07-01'", params["where"])
        self.assertIn('maintenance \\"moteur\\"', params["where"])

    def test_ted_request_uses_v3_post_contract(self) -> None:
        session = mock.Mock()
        session.post.return_value = _Response({"notices": [{"publication-number": "1-2026"}]})
        query = _build_ted_query(
            keywords="maintenance moteur",
            date_pub_min=date(2026, 7, 1),
            date_pub_max=date(2026, 7, 31),
            cpv_prefix=None,
        )
        rows = _fetch_notices(session, query=query, page=1, limit=10)
        self.assertEqual(rows[0]["publication-number"], "1-2026")
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["paginationMode"], "PAGE_NUMBER")
        self.assertEqual(payload["page"], 1)
        self.assertIn("publication-date >= 20260701", payload["query"])


class PipelineOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = repository.DB_PATH
        repository.DB_PATH = Path(self.temp_dir.name) / "argos.db"
        repository.initialize_database()

    def tearDown(self) -> None:
        repository.DB_PATH = self.previous_db_path
        self.temp_dir.cleanup()

    async def test_successful_scraping_and_ai_marks_job_complete(self) -> None:
        search_id = repository.create_recherche_job(requete="test", source="boamp,ted")
        with (
            mock.patch.object(pipeline, "run_all_scrapers") as scrapers,
            mock.patch.object(pipeline, "process_search_id_async", new=mock.AsyncMock()) as ai,
        ):
            await pipeline.run_full_pipeline(
                search_id=search_id,
                mots_recherche=[["maintenance"]],
                meta_prompt="critères",
                date_pub_min="2026-07-01",
                date_pub_max="2026-07-31",
                selected_sites=["boamp", "ted"],
            )
        job = next(repository.list_recherche_jobs(limit=1))
        self.assertEqual(job["statut"], "termine")
        scrapers.assert_called_once()
        ai.assert_awaited_once_with(search_id, "critères")

    async def test_inverted_period_stops_before_network(self) -> None:
        search_id = repository.create_recherche_job(requete="test", source="boamp")
        with mock.patch.object(pipeline, "run_all_scrapers") as scrapers:
            with self.assertRaisesRegex(ValueError, "date de début"):
                await pipeline.run_full_pipeline(
                    search_id=search_id,
                    mots_recherche=[["maintenance"]],
                    meta_prompt="critères",
                    date_pub_min="2026-07-31",
                    date_pub_max="2026-07-01",
                    selected_sites=["boamp"],
                )
        scrapers.assert_not_called()


if __name__ == "__main__":
    unittest.main()
