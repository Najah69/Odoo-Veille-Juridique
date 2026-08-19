from unittest.mock import patch

from ..services.base_connector import BaseConnector, CandidateItem, FetchResult
from .common import LegalWatchTransactionCase

_PATCH_TARGET = "odoo.addons.legal_knowledge_watch.services.connector_registry.get_connector"


class _FakeConnector(BaseConnector):
    code = "fake"
    items = []

    def validate_configuration(self):
        pass

    def fetch(self, cursor, limit=100):
        return FetchResult(
            items=list(self.__class__.items), next_cursor="fake-cursor",
            diagnostics={"item_errors": []},
        )


def _item(**overrides):
    defaults = dict(
        source_url="https://exemple.gouv.example.org/a",
        canonical_url="https://exemple.gouv.example.org/a",
        title="Item de test",
        external_id="EXT-A",
        raw_content=None,
        plain_text="Texte de l'item de test.",
        published_at=None,
        updated_at=None,
        content_type="text/html",
        language="fr_FR",
        source_metadata={},
    )
    defaults.update(overrides)
    return CandidateItem(**defaults)


class TestWatchIngestionOrchestration(LegalWatchTransactionCase):
    def _make_rss_watch(self, rule_vals=None):
        watch = self.env["legal.watch"].create({
            "name": "RSS Test Watch",
            "source_id": self.source.id,
            "connector_code": "rss",
            "configuration_json": '{"feed_url": "https://exemple.gouv.example.org/feed.rss"}',
        })
        if rule_vals:
            self.env["legal.watch.rule"].create({**rule_vals, "watch_id": watch.id})
        return watch

    def test_run_creates_run_and_documents(self):
        # EN: Distinct plain_text on each item: two items with identical
        # content (even under different external_id/URL) are legitimately
        # caught by the content_hash dedup fallback and would collapse
        # into 1 created + 1 duplicate, not 2 created — see
        # test_dedup_across_two_runs.
        # FR : plain_text distinct pour chaque item : deux items au
        # contenu identique (même avec external_id/URL différents) sont
        # légitimement rattrapés par le repli de dédup sur content_hash et
        # fusionneraient en 1 créé + 1 doublon, pas 2 créés — voir
        # test_dedup_across_two_runs.
        _FakeConnector.items = [
            _item(external_id="EXT-1", canonical_url="https://exemple.gouv.example.org/1",
                  title="Item un", plain_text="Contenu du premier item de test."),
            _item(external_id="EXT-2", canonical_url="https://exemple.gouv.example.org/2",
                  title="Item deux", plain_text="Contenu du second item de test."),
        ]
        watch = self._make_rss_watch()
        with patch(_PATCH_TARGET, return_value=_FakeConnector):
            run = watch._run_ingestion(trigger="manual")

        self.assertEqual(run.state, "success")
        self.assertEqual(run.created_count, 2)
        self.assertEqual(run.fetched_count, 2)
        self.assertEqual(watch.document_count, 2)
        self.assertTrue(watch.last_success_at)
        self.assertEqual(watch.last_cursor, "fake-cursor")

    def test_dedup_across_two_runs(self):
        _FakeConnector.items = [
            _item(external_id="EXT-1", canonical_url="https://exemple.gouv.example.org/1"),
        ]
        watch = self._make_rss_watch()
        with patch(_PATCH_TARGET, return_value=_FakeConnector):
            first_run = watch._run_ingestion(trigger="manual")
            second_run = watch._run_ingestion(trigger="manual")

        self.assertEqual(first_run.created_count, 1)
        self.assertEqual(second_run.created_count, 0)
        self.assertEqual(second_run.duplicate_count, 1)
        self.assertEqual(watch.document_count, 1)

    def test_partial_run_when_one_item_fails(self):
        _FakeConnector.items = [
            _item(external_id="EXT-OK", canonical_url="https://exemple.gouv.example.org/ok",
                  title="Item valide", plain_text="Contenu de l'item valide."),
            _item(external_id="EXT-BAD", canonical_url="https://exemple.gouv.example.org/bad",
                  title=None, plain_text="Contenu distinct de l'item en échec."),
            # EN: None title -> ORM required-field violation on create();
            # a distinct plain_text avoids being caught as a content_hash
            # duplicate of the first item before ever reaching create().
            # FR : title=None -> violation ORM de champ requis lors du
            # create() ; un plain_text distinct évite d'être rattrapé
            # comme doublon content_hash du premier item avant même
            # d'atteindre le create().
        ]
        watch = self._make_rss_watch()
        with patch(_PATCH_TARGET, return_value=_FakeConnector):
            run = watch._run_ingestion(trigger="manual")

        self.assertEqual(run.state, "partial")
        self.assertEqual(run.created_count, 1)
        self.assertEqual(run.error_count, 1)

    def test_exclude_rule_filters_item_before_ingestion(self):
        _FakeConnector.items = [
            _item(external_id="EXT-KEEP", canonical_url="https://exemple.gouv.example.org/keep",
                  title="À conserver"),
            _item(external_id="EXT-DROP", canonical_url="https://exemple.gouv.example.org/drop",
                  title="Communiqué publicitaire à exclure"),
        ]
        watch = self._make_rss_watch(rule_vals={
            "name": "Exclude ads", "rule_type": "keyword", "target_field": "title",
            "operator": "contains", "value": "publicitaire", "effect": "exclude",
        })
        with patch(_PATCH_TARGET, return_value=_FakeConnector):
            run = watch._run_ingestion(trigger="manual")

        self.assertEqual(run.created_count, 1)
        self.assertEqual(run.filtered_count, 1)
        self.assertEqual(watch.document_count, 1)

    def test_try_lock_succeeds_when_uncontended(self):
        # EN: Odoo's TestCursor.commit() only releases a savepoint (it
        # never truly commits), so a genuinely separate DB connection
        # can't see this test's data — a real cross-session lock test is
        # not possible inside a single TransactionCase. Instead we test
        # the two halves separately: the SQL/exception-handling path
        # below (with the lock query's failure simulated), and the
        # orchestration branch in test_run_skipped_when_lock_unavailable.
        # FR : Le commit() de TestCursor d'Odoo ne fait que libérer un
        # savepoint (il ne commit jamais vraiment), donc une connexion DB
        # réellement séparée ne peut pas voir les données de ce test — un
        # vrai test de verrou inter-session est impossible dans un seul
        # TransactionCase. On teste donc les deux moitiés séparément : le
        # chemin SQL/gestion d'exception ci-dessous (avec l'échec de la
        # requête de verrou simulé), et la branche d'orchestration dans
        # test_run_skipped_when_lock_unavailable.
        watch = self._make_rss_watch()
        self.assertTrue(watch._try_lock_for_run())
        # EN: FOR UPDATE NOWAIT never self-blocks on a lock already held
        # by the same transaction.
        # FR : FOR UPDATE NOWAIT ne se bloque jamais lui-même sur un
        # verrou déjà détenu par la même transaction.
        self.assertTrue(watch._try_lock_for_run())

    def test_try_lock_returns_false_on_lock_not_available(self):
        from psycopg2 import errors as psycopg2_errors

        watch = self._make_rss_watch()
        real_execute = type(self.env.cr).execute

        def fake_execute(cr_self, *args, **kwargs):
            if args and "FOR UPDATE NOWAIT" in str(args[0]):
                raise psycopg2_errors.LockNotAvailable("simulated: row already locked")
            return real_execute(cr_self, *args, **kwargs)

        with patch.object(type(self.env.cr), "execute", fake_execute):
            self.assertFalse(watch._try_lock_for_run())
        # EN: The failed attempt must not have poisoned the transaction:
        # normal queries still work afterwards.
        # FR : La tentative échouée ne doit pas avoir empoisonné la
        # transaction : les requêtes normales fonctionnent toujours
        # ensuite.
        self.assertTrue(watch._try_lock_for_run())

    def test_run_skipped_when_lock_unavailable(self):
        watch = self._make_rss_watch()
        with patch.object(type(watch), "_try_lock_for_run", return_value=False):
            run = watch._run_ingestion(trigger="manual")
        self.assertEqual(run.state, "skipped")
