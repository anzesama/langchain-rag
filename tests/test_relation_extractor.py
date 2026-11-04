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
