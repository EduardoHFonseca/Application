import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import crawler
import database
from sources import registry
from sources.base import JobPosting, JobSource, canonicalize_url, normalize_text
from sources.remotive import RemotiveSource
from sources.rss import RSSSource
from sources.workingnomads import WorkingNomadsSource

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(BASE_DIR, "tests", "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as handle:
        return handle.read()


class FakeSource(JobSource):
    name = "fake"
    label = "Fake"
    min_interval_hours = 0

    def fetch(self, keywords=None, locations=None, limit=50):
        return [
            JobPosting(
                fonte="fake",
                source_job_id="1",
                url="https://example.com/jobs/1",
                titulo="Senior Product Manager",
                empresa="Fake Co",
                localizacao="Remote",
                descricao="Product role",
            ),
            JobPosting(
                fonte="fake",
                source_job_id="2",
                url="https://example.com/jobs/2",
                titulo="Backend Engineer",
                empresa="Fake Co",
                localizacao="USA Only",
                descricao="Backend role",
            ),
        ]


class TestParsers(unittest.TestCase):
    def test_remotive_parse_payload(self):
        payload = json.loads(fixture("remotive.json"))
        postings = RemotiveSource.parse_payload(payload)
        self.assertEqual(len(postings), 2)
        first = postings[0]
        self.assertEqual(first.fonte, "remotive")
        self.assertEqual(first.source_job_id, "2091161")
        self.assertEqual(first.titulo, "Senior Product Manager")
        self.assertEqual(first.empresa, "Acme Remote")
        self.assertEqual(first.localizacao, "Worldwide")
        self.assertEqual(first.tags, ["product", "saas", "agile"])
        self.assertNotIn("<p>", first.descricao)
        self.assertIn("Senior Product Manager", first.descricao)
        self.assertEqual(postings[1].tags, ["design", "ux"])

    def test_wwr_parse_feed(self):
        postings = RSSSource.parse_feed(fixture("wwr.rss"))
        self.assertEqual(len(postings), 2)
        first = postings[0]
        self.assertEqual(first.fonte, "wwr")
        self.assertEqual(first.empresa, "Acme Remote")
        self.assertEqual(first.titulo, "Senior Product Manager")
        self.assertEqual(first.source_job_id, "acme-remote-senior-product-manager-1")
        self.assertIn("Anywhere in the World", first.localizacao)
        self.assertIn("Product Management", first.tags)
        self.assertIn("Agile", first.tags)
        self.assertNotIn("&lt;", first.descricao)
        self.assertIn("Product Manager", first.descricao)

    def test_workingnomads_parse_payload(self):
        postings = WorkingNomadsSource.parse_payload(json.loads(fixture("workingnomads.json")))
        self.assertEqual(len(postings), 2)
        first = postings[0]
        self.assertEqual(first.fonte, "workingnomads")
        self.assertEqual(first.source_job_id, "1960693")
        self.assertEqual(first.titulo, "Senior Product Owner")
        self.assertEqual(first.empresa, "Nomad Labs")
        self.assertEqual(first.tags, ["product", "agile", "scrum"])
        self.assertIn("LATAM", first.localizacao)
        self.assertNotIn("<p>", first.descricao)

    def test_parser_ignores_invalid_entries(self):
        payload = {"jobs": [{"id": 1, "url": "", "title": "Sem URL"}]}
        self.assertEqual(RemotiveSource.parse_payload(payload), [])


class TestNormalizationAndFiltering(unittest.TestCase):
    def test_canonicalize_url(self):
        url = "https://www.Example.com/jobs/123/?utm_source=x&b=2&a=1#frag"
        self.assertEqual(canonicalize_url(url), "https://example.com/jobs/123?a=1&b=2")

    def test_normalize_text_removes_accents(self):
        self.assertEqual(normalize_text("Gerência de Produtos"), "gerencia de produtos")

    def test_dedupe_hash_ignores_case_and_accents(self):
        a = JobPosting(fonte="a", source_job_id="1", url="https://a.com/1",
                       titulo="Gerente de Projetos", empresa="ACME")
        b = JobPosting(fonte="b", source_job_id="2", url="https://b.com/2",
                       titulo="gerente de projetos", empresa="acme")
        self.assertEqual(a.hash_dedupe, b.hash_dedupe)

    def test_keyword_and_location_filters(self):
        posting = JobPosting(
            fonte="remotive",
            source_job_id="1",
            url="https://remotive.com/jobs/1",
            titulo="Senior Product Manager",
            empresa="Acme",
            localizacao="USA Only",
            descricao="Remote product role",
        )
        self.assertTrue(JobSource.matches_keywords(posting, ["product manager"]))
        self.assertFalse(JobSource.matches_keywords(posting, ["data engineer"]))
        self.assertFalse(JobSource.matches_locations(posting, ["Brazil", "LATAM"]))
        self.assertFalse(JobSource.matches_locations(posting, ["Remote"]))
        posting.localizacao = "Remote (Brazil)"
        self.assertTrue(JobSource.matches_locations(posting, ["Remote"]))
        posting.localizacao = "Anywhere in the World"
        self.assertTrue(JobSource.matches_locations(posting, ["Brazil"]))

    def test_keyword_requires_title_or_two_description_hits(self):
        posting = JobPosting(
            fonte="x",
            source_job_id="1",
            url="https://x.com/1",
            titulo="Compliance Lead",
            empresa="X",
            descricao="Works closely with the product manager",
        )
        self.assertFalse(JobSource.matches_keywords(posting, ["product manager", "project manager"]))
        posting.descricao = "Works with the product manager, the project manager and the program manager"
        self.assertTrue(
            JobSource.matches_keywords(
                posting, ["product manager", "project manager", "program manager"]
            )
        )

    def test_fit_score_prioritizes_title(self):
        title_match = JobPosting(fonte="x", source_job_id="1", url="https://x.com/1",
                                 titulo="Product Manager", empresa="X")
        desc_match = JobPosting(fonte="x", source_job_id="2", url="https://x.com/2",
                                titulo="Engineer", empresa="X",
                                descricao="We need a product manager")
        self.assertGreater(
            crawler.fit_score(title_match, ["product manager"]),
            crawler.fit_score(desc_match, ["product manager"]),
        )

    def test_dedupe_postings_batch(self):
        a = JobPosting(fonte="x", source_job_id="1", url="https://x.com/1",
                       titulo="Product Manager", empresa="Acme")
        b = JobPosting(fonte="y", source_job_id="2", url="https://y.com/2",
                       titulo="product manager", empresa="acme")
        c = JobPosting(fonte="x", source_job_id="3", url="https://x.com/3",
                       titulo="Data Engineer", empresa="Acme")
        self.assertEqual(len(crawler.dedupe_postings([a, b, c])), 2)

    def test_source_is_due(self):
        now = datetime.now(timezone.utc)
        state = {"last_run": {"remotive": (now - timedelta(hours=1)).isoformat()}}
        self.assertFalse(crawler.source_is_due("remotive", 6, state, now=now))
        self.assertTrue(crawler.source_is_due("remotive", 0.5, state, now=now))
        self.assertTrue(crawler.source_is_due("wwr", 6, state, now=now))


class TestRegistry(unittest.TestCase):
    def test_load_config_and_enabled_sources(self):
        config = registry.load_config()
        self.assertIn("remotive", config["sources"])
        self.assertIn("wwr", config["sources"])
        self.assertIn("workingnomads", config["sources"])
        self.assertGreaterEqual(len(config["discarded"]), 10)
        with patch.dict(os.environ, {"CRAWLER_SOURCES": ""}):
            enabled = registry.enabled_source_names(config)
        for name in ("remotive", "wwr", "workingnomads", "linkedin"):
            self.assertIn(name, enabled)

    def test_build_implemented_source(self):
        source = registry.build_source("remotive")
        self.assertEqual(source.name, "remotive")
        self.assertEqual(source.apply_mode, "assisted")
        source.close()

    def test_build_unknown_source(self):
        with self.assertRaises(KeyError):
            registry.build_source("nao_existe")

    def test_unimplemented_source_raises(self):
        with self.assertRaises(NotImplementedError):
            registry.build_source("jobspresso")


class TestDatabaseSources(unittest.TestCase):
    def setUp(self):
        self.db_url = os.getenv("DATABASE_URL")
        database.init_db(self.db_url)
        self.run_id = uuid.uuid4().hex[:10]

    def tearDown(self):
        conn = database.get_connection(self.db_url)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM vagas WHERE fonte LIKE 'teste_%' OR fonte = 'fake' OR titulo LIKE 'UNITTEST%'"
        )
        conn.commit()
        cursor.close()
        conn.close()

    def _posting(self, fonte, source_id, title, company):
        return JobPosting(
            fonte=fonte,
            source_job_id=source_id,
            url=f"https://example.com/{fonte}/{source_id}",
            titulo=title,
            empresa=company,
            localizacao="Remote",
            descricao="desc",
        )

    def test_save_posting_is_idempotent(self):
        title = f"UNITTEST Idempotent {self.run_id}"
        company = f"UNITTEST Co {self.run_id}"
        posting = self._posting("teste_idem", f"id-{self.run_id}", title, company)
        first_id, created_first = database.save_posting(posting, db_url=self.db_url)
        second_id, created_second = database.save_posting(posting, db_url=self.db_url)
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first_id, second_id)

    def test_cross_source_dedupe(self):
        title = f"UNITTEST Cross {self.run_id}"
        company = f"UNITTEST Co {self.run_id}"
        a = self._posting("teste_a", f"a-{self.run_id}", title, company)
        b = self._posting("teste_b", f"b-{self.run_id}", title, company)
        id_a, created_a = database.save_posting(a, db_url=self.db_url)
        id_b, created_b = database.save_posting(b, db_url=self.db_url)
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(id_a, id_b)

    def test_collect_dry_run_with_fake_source(self):
        config = {
            "defaults": {"limit": 10, "keywords": [], "locations": []},
            "sources": {"fake": {"name": "fake", "enabled": True}},
            "discarded": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("crawler.build_source", return_value=FakeSource({"name": "fake"})):
                summary = crawler.collect(
                    source_names=["fake"],
                    keywords=["product manager"],
                    locations=["Remote"],
                    dry_run=True,
                    notify=False,
                    config=config,
                    state_path=os.path.join(tmp, "state.json"),
                )
        self.assertEqual(summary["sources"]["fake"]["fetched"], 2)
        self.assertEqual(summary["sources"]["fake"]["matched"], 1)
        self.assertEqual(len(summary["postings"]), 1)
        self.assertEqual(summary["new"], 0)


if __name__ == "__main__":
    unittest.main()
