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


def test_search_endpoints_are_async():
    import inspect
    import rag_server_v2 as srv
    routes = {r.path: r.endpoint for r in srv.app.routes if hasattr(r, "endpoint")}
    assert inspect.iscoroutinefunction(routes["/api/search"])
    assert inspect.iscoroutinefunction(routes["/api/search_raw"])
    assert inspect.iscoroutinefunction(routes["/api/smart_search"])


def test_health_latency_while_search_blocked(monkeypatch):
    """慢检索进行时 /health 延迟仍很小（event loop 未被阻塞）。"""
    import asyncio, time, httpx
    import rag_server_v2 as srv

    class _SlowKB:
        def search(self, query, top_k=None, **kw):
            time.sleep(0.8)  # 模拟阻塞 IO
            return {"query": query, "answer": "A", "sources": []}

        def get_stats(self):
            return {"total_documents": 0}
    monkeypatch.setattr(srv, "get_kb", lambda: _SlowKB())

    async def _run():
        transport = httpx.ASGITransport(app=srv.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            task = asyncio.create_task(
                ac.post("/api/search", json={"query": "x", "top_k": 1})
            )
            await asyncio.sleep(0.05)  # 让 search 先进入阻塞
            t0 = time.perf_counter()
            r_health = await ac.get("/health")
            latency = time.perf_counter() - t0
            await task
            return r_health, latency

    r_health, latency = asyncio.run(_run())
    assert r_health.status_code == 200
    assert latency < 0.5  # health 不被 0.8s 的 search 拖住
