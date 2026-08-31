from app.services import search_index


class _FakeClient:
    def __init__(self, hits=None):
        self.hits = hits or []
        self.body = None

    def search(self, *, index, body):
        self.body = body
        return {"hits": {"hits": self.hits}}


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
