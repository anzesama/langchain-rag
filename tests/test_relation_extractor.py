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
