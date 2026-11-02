import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from fastapi.testclient import TestClient


def _client_with_kb(monkeypatch, kb):
    import rag_server_v2 as srv
    monkeypatch.setattr(srv, "get_kb", lambda: kb)
    return TestClient(srv.app)


class _FakeKB:
    def search_raw(self, query, top_k=None, **kw):
        return [{"source": "a.md", "content": "片段内容", "score": 0.9}]


def test_search_raw_returns_sources_without_answer(monkeypatch):
    client = _client_with_kb(monkeypatch, _FakeKB())
    r = client.post("/api/search_raw", json={"query": "你好", "top_k": 3})
    assert r.status_code == 200
    data = r.json()
    assert "answer" not in data
    assert data["query"] == "你好"
    assert data["sources"][0]["source"] == "a.md"


def test_search_raw_empty_query_returns_empty_sources(monkeypatch):
    class _EmptyKB:
        def search_raw(self, query, top_k=None, **kw):
            return []
    client = _client_with_kb(monkeypatch, _EmptyKB())
    r = client.post("/api/search_raw", json={"query": "", "top_k": 3})
    assert r.status_code == 200
    assert r.json()["sources"] == []
