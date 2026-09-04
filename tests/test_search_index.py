from app.services import search_index
from app.database.models import SystemState
from app.utils.search_normalizer import keyboard_layout_query


class _FakeClient:
    def __init__(self, hits=None):
        self.hits = hits or []
        self.body = None

    def search(self, *, index, body):
        self.body = body
        return {"hits": {"hits": self.hits}}


class _FakeStateDb:
    def __init__(self):
        self.rows = {}

    def get(self, model, key):
        assert model is SystemState
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.key] = row


class _EmptyMappingsResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _CaptureRowsDb:
    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _EmptyMappingsResult()


def _multi_match_clauses(client):
    scored = client.body["query"]["function_score"]["query"]
    return [item["multi_match"] for item in scored["bool"]["should"] if "multi_match" in item]


def test_multiword_search_requires_every_word(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(search_index, "_get_shared_es_client", lambda: client)
    monkeypatch.setattr(search_index.settings, "ELASTICSEARCH_FUZZY_SEARCH", False)

    assert search_index.search_companies("Минск Строй", 5) == []

    clauses = _multi_match_clauses(client)
    assert clauses
    assert all(clause["operator"] == "and" for clause in clauses)
    assert {clause["_name"] for clause in clauses} >= {
        "current_normalized",
        "historical_normalized",
    }


def test_raw_legal_form_is_used_as_secondary_ranking_signal(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(search_index, "_get_shared_es_client", lambda: client)
    monkeypatch.setattr(search_index.settings, "ELASTICSEARCH_FUZZY_SEARCH", False)

    search_index.search_companies('ООО "Ромашка"', 5)

    clauses = _multi_match_clauses(client)
    by_name = {clause["_name"]: clause for clause in clauses}
    assert by_name["current_normalized"]["query"] == "ромашка"
    assert by_name["current_raw"]["query"] == 'ооо "ромашка"'
    assert "search_name^8" not in by_name["current_raw"]["fields"]


def test_historical_match_is_reported_only_for_historical_only_hit(monkeypatch):
    client = _FakeClient(
        [
            {
                "_source": {
                    "unp": "123456789",
                    "full_name_ru": "ООО Новое имя",
                    "short_name_ru": None,
                    "full_name_by": None,
                    "all_names": ["ООО Новое имя", "ООО Старое имя"],
                    "historical_names": ["ООО Старое имя"],
                },
                "matched_queries": ["historical_normalized"],
            }
        ]
    )
    monkeypatch.setattr(search_index, "_get_shared_es_client", lambda: client)
    monkeypatch.setattr(search_index.settings, "ELASTICSEARCH_FUZZY_SEARCH", False)

    results = search_index.search_companies("Старое имя", 5)

    assert results[0]["matched_name"] == "ООО Старое имя"
    assert results[0]["matched_historical_name"] is True


def test_wrong_keyboard_layout_is_added_without_replacing_latin_query(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(search_index, "_get_shared_es_client", lambda: client)
    monkeypatch.setattr(search_index.settings, "ELASTICSEARCH_FUZZY_SEARCH", False)

    search_index.search_companies("vbycr", 5)

    clauses = _multi_match_clauses(client)
    by_name = {clause["_name"]: clause for clause in clauses}
    assert by_name["current_normalized"]["query"] == "vbycr"
    assert by_name["current_keyboard"]["query"] == "минск"
    assert keyboard_layout_query("ntp") == "тез"


def test_index_is_not_ready_without_completed_full_pass():
    db = _FakeStateDb()

    assert search_index.is_index_ready_for_search(db) is False

    search_index._save_reindex_state(
        db,
        {
            "index": search_index.settings.ELASTICSEARCH_INDEX,
            "status": "running",
            "synced": False,
            "last_unp": 123,
        },
    )

    assert search_index.is_index_ready_for_search(db) is False


def test_index_is_ready_only_after_verified_full_pass():
    db = _FakeStateDb()
    search_index._save_reindex_state(
        db,
        {
            "index": search_index.settings.ELASTICSEARCH_INDEX,
            "status": "complete",
            "synced": True,
            "last_unp": 999999999,
        },
    )

    assert search_index.is_index_ready_for_search(db) is True


def test_reindex_pages_companies_before_history_joins():
    db = _CaptureRowsDb()

    assert search_index._company_rows(db, last_unp=100, limit=25) == []
    assert "WITH company_page AS MATERIALIZED" in db.statement
    assert "FROM company_page c" in db.statement
    assert db.params == {"last_unp": 100, "limit": 25}
