"""关系抽取唯一入口（全离线：fake refiner）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_skip_llm_does_not_construct_refiner(monkeypatch):
    """SKIP_LLM=1 → 完全不构造 LLMRefiner，且标记 skipped"""
    import rag_core.relation_extractor as rx

    built = []
    monkeypatch.setattr(rx, "LLMRefiner", lambda *a, **k: built.append(1))
    monkeypatch.setenv("SKIP_LLM", "1")

    res = rx.extract_relations_for_source("_pytest_rx_skip.md", chunks=[{"chunk_text": "x"}])

    assert built == [], "SKIP_LLM=1 时不得构造 LLMRefiner（不得打网络）"
    assert res["skipped"] is True
    assert res["relations_imported"] == 0
    assert res["error"] is None


def _fake_refiner(relations):
    """构造一个不联网的 LLMRefiner 替身"""

    class _Fake:
        def __init__(self, endpoint, api_key, model, domain="machine-learning"):
            self.endpoint, self.api_key, self.model, self.domain = endpoint, api_key, model, domain

        def extract_relations(self, chunks, entities):
            return {"relations": relations, "count": len(relations)}

    return _Fake


def test_extract_and_import_relations(monkeypatch):
    """正常路径：1 条关系被抽取并写入 WikiDB（实体自动创建）"""
    import rag_core.relation_extractor as rx
    from rag_core.wiki_db_libsql import get_wiki_db

    monkeypatch.delenv("SKIP_LLM", raising=False)
    monkeypatch.setattr(rx, "LLMRefiner", _fake_refiner([{"source": "甲", "target": "乙", "type": "关联"}]))
    monkeypatch.setattr(rx, "_load_entities", lambda source: [{"name": "甲", "type": "概念"}])

    res = rx.extract_relations_for_source("_pytest_rx_ok.md", chunks=[{"chunk_text": "甲与乙相关"}])

    assert res["skipped"] is False
    assert res["error"] is None
    assert res["relations_extracted"] == 1
    assert res["relations_imported"] == 1

    db = get_wiki_db()
    assert db.get_entity_id("甲") is not None
    assert db.get_entity_id("乙") is not None


def test_fetches_chunks_from_store_when_none(monkeypatch):
    """chunks=None 时必须用 VectorStoreManager.get_chunks_by_source 查库"""
    import rag_core.relation_extractor as rx

    seen = {}

    class _VS:
        def get_chunks_by_source(self, source, limit=None):
            seen["source"] = source
            return [{"chunk_text": "甲与乙相关"}]

    monkeypatch.delenv("SKIP_LLM", raising=False)
    monkeypatch.setattr(rx, "VectorStoreManager", lambda *a, **k: _VS())
    monkeypatch.setattr(rx, "_load_entities", lambda source: [{"name": "甲"}])
    monkeypatch.setattr(rx, "LLMRefiner", _fake_refiner([]))

    res = rx.extract_relations_for_source("_pytest_rx_fetch.md")

    assert seen["source"] == "_pytest_rx_fetch.md"
    assert res["error"] is None
    assert res["relations_extracted"] == 0


def test_no_entities_returns_error_not_crash(monkeypatch):
    """回归：无实体时必须返回 error，且不得 NameError（旧代码在 chunks 赋值前 return 会崩）"""
    import rag_core.relation_extractor as rx

    monkeypatch.delenv("SKIP_LLM", raising=False)
    res = rx.extract_relations_for_source(
        "_pytest_rx_no_entities_xyz.md", chunks=[{"chunk_text": "text"}]
    )

    assert res["error"] == "No entities found"
    assert res["relations_imported"] == 0
    assert res["relations_extracted"] == 0


def test_refiner_exception_becomes_error_field(monkeypatch):
    """refiner 抛异常 → 转为 error 字段，不向上抛"""
    import rag_core.relation_extractor as rx

    class _Boom(_fake_refiner([])):
        def extract_relations(self, chunks, entities):
            raise RuntimeError("模拟 429")

    monkeypatch.delenv("SKIP_LLM", raising=False)
    monkeypatch.setattr(rx, "_load_entities", lambda source: [{"name": "甲"}])
    monkeypatch.setattr(rx, "LLMRefiner", _Boom)

    res = rx.extract_relations_for_source("_pytest_rx_boom.md", chunks=[{"chunk_text": "t"}])

    assert "RuntimeError" in (res["error"] or "")
    assert res["relations_imported"] == 0


def test_llm_called_exactly_once(monkeypatch):
    """回归：曾因 finally 中的重复块导致 LLM 跑两遍"""
    import rag_core.relation_extractor as rx

    calls = []

    class _Counting(_fake_refiner([])):
        def extract_relations(self, chunks, entities):
            calls.append(1)
            return {"relations": [{"source": "甲", "target": "乙", "type": "关联"}], "count": 1}

    monkeypatch.delenv("SKIP_LLM", raising=False)
    monkeypatch.setattr(rx, "_load_entities", lambda source: [{"name": "甲"}])
    monkeypatch.setattr(rx, "LLMRefiner", _Counting)

    rx.extract_relations_for_source("_pytest_rx_once.md", chunks=[{"chunk_text": "t"}])

    assert len(calls) == 1, f"LLM 必须恰好调用 1 次，实际 {len(calls)} 次"


def test_normalize_chunks_accepts_document():
    """Document 与 dict 都要能接受（回归旧代码 c.get(...) 对 Document 报错）"""
    import rag_core.relation_extractor as rx
    from langchain_core.documents import Document

    out = rx._normalize_chunks([Document(page_content="doc text"), {"page_content": "dict text"}])

    assert [c["chunk_text"] for c in out] == ["doc text", "dict text"]


def test_extract_all_sources_iterates_and_limits(monkeypatch):
    """--all 走唯一入口，且 limit 生效；不直接访问 DB"""
    import rag_core.relation_extractor as rx

    class _VS:
        def list_sources(self):
            return ["_pytest_all_1.md", "_pytest_all_2.md", "_pytest_all_3.md"]

    monkeypatch.setattr(rx, "VectorStoreManager", lambda *a, **k: _VS())
    monkeypatch.setattr(
        rx,
        "extract_relations_for_source",
        lambda source, domain=None, chunks=None: {"source": source, "skipped": True},
    )

    out = rx.extract_all_sources(limit=2)
    assert list(out.keys()) == ["_pytest_all_1.md", "_pytest_all_2.md"]

    # limit=0 必须"处理 0 个"，而不是被当作 falsy 忽略（同类边界 bug 已在本项目出现过）
    assert rx.extract_all_sources(limit=0) == {}

    out_all = rx.extract_all_sources()
    assert len(out_all) == 3
