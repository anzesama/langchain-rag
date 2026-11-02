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


def test_ask_degrades_on_generate_timeout(monkeypatch):
    import rag_core.rag_pipeline as rp
    from langchain_core.documents import Document

    class _Router:
        def route(self, q):
            return "rag"
    monkeypatch.setattr(rp, "get_wiki_db", lambda: object())
    monkeypatch.setattr(rp, "get_wiki_router", lambda: _Router())

    # 真实构造 + 注入 fake vector_store：__init__ 内 `vector_store or VectorStoreManager()`
    # 会短路，既不加载重模型，又保证 4 个属性齐全（不依赖 __new__ 的隐性假设）
    pipe = rp.RagPipeline(vector_store=object())
    monkeypatch.setattr(
        pipe, "retrieve",
        lambda *a, **k: [(Document(page_content="x", metadata={"source": "a.md"}), 0.9)],
    )
    def _boom(*a, **k):
        raise TimeoutError("llm timeout")
    monkeypatch.setattr(pipe, "generate_answer", _boom)

    result = pipe.ask("问题", top_k=3)
    assert result["degraded"] is True
    assert result["sources"][0]["source"] == "a.md"
    assert "超时" in result["answer"]


def test_get_llm_has_timeout(monkeypatch):
    import rag_core.rag_pipeline as rp
    monkeypatch.setenv("RAG_AGNES_API_KEY", "test-key")
    llm = rp.get_llm()
    # ChatOpenAI 不同版本字段名不同（request_timeout / timeout），做兼容断言
    val = getattr(llm, "request_timeout", None) or getattr(llm, "timeout", None)
    assert val is not None
