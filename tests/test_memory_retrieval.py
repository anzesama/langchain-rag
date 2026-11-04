"""记忆感知检索（Phase 1 任务 6 / 验收 V4）

铁律：`RAG_MEMORY_ENABLED=0`（默认）时，行为与旧版**逐字节一致** ——
不重排、不加 metadata、**不写库**。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pytest

from rag_core.vector_store_libsql import VectorStoreManager

DIM = 512


@pytest.fixture
def store(tmp_path):
    return VectorStoreManager(persist_dir=tmp_path)


def _insert(vs, chunk_id, vector, importance=None, access_count=0, last_access=None,
            text="", source="doc.txt"):
    conn = sqlite3.connect(str(vs.db_path))
    conn.execute(
        "INSERT INTO chunks (chunk_id, text_content, vector, metadata, source, "
        "importance, access_count, last_access) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (chunk_id, text or f"text {chunk_id}", vs._vector_to_blob(vector),
         json.dumps({"source": source}), source,
         0.5 if importance is None else importance, access_count, last_access),
    )
    conn.commit()
    conn.close()


def _query_vector():
    v = np.zeros(DIM, dtype=np.float32)
    v[0] = 1.0
    return v


def _near_vector(sim):
    """构造与 query 余弦接近 sim 的向量（第一维为主）"""
    v = np.zeros(DIM, dtype=np.float32)
    v[0] = sim
    v[1] = float(np.sqrt(max(0.0, 1.0 - sim * sim)))
    return v


def _read_memory(vs, chunk_id):
    conn = sqlite3.connect(f"file:{vs.db_path}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT importance, access_count, last_access FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture
def memory_on(monkeypatch):
    monkeypatch.setenv("RAG_MEMORY_ENABLED", "1")


@pytest.fixture
def memory_off(monkeypatch):
    monkeypatch.delenv("RAG_MEMORY_ENABLED", raising=False)


# ------------------------------------------------------- V4：关闭时零变化

class TestDisabledIsInert:
    def test_order_and_scores_are_raw_similarity(self, store, memory_off):
        _insert(store, "low_imp_high_sim", _query_vector(), importance=0.0)
        _insert(store, "high_imp_low_sim", _near_vector(0.9), importance=1.0)

        res = store._cosine_similarity_query(_query_vector(), top_k=2)

        assert [r[0]["chunk_id"] for r in res] == ["low_imp_high_sim", "high_imp_low_sim"]
        assert res[0][1] == pytest.approx(1.0, abs=1e-5)
        assert res[1][1] == pytest.approx(0.9, abs=1e-5)

    def test_does_not_write_to_database(self, store, memory_off):
        _insert(store, "c1", _query_vector())
        store._cosine_similarity_query(_query_vector(), top_k=1)
        assert _read_memory(store, "c1") == (0.5, 0, None)

    def test_does_not_add_memory_metadata(self, store, memory_off):
        _insert(store, "c1", _query_vector())
        res = store._cosine_similarity_query(_query_vector(), top_k=1)
        assert "importance" not in res[0][0]["metadata"]


# --------------------------------------------------------- 启用时重排

class TestEnabledRerank:
    def test_importance_can_outrank_similarity(self, store, memory_on):
        _insert(store, "low_imp_high_sim", _query_vector(), importance=0.0)
        _insert(store, "high_imp_low_sim", _near_vector(0.9), importance=1.0)

        res = store._cosine_similarity_query(_query_vector(), top_k=2)

        assert [r[0]["chunk_id"] for r in res] == ["high_imp_low_sim", "low_imp_high_sim"]

    def test_returned_scores_are_descending(self, store, memory_on):
        for i, (imp, sim) in enumerate([(0.1, 1.0), (0.9, 0.95), (0.5, 0.99)]):
            _insert(store, f"c{i}", _near_vector(sim), importance=imp)
        res = store._cosine_similarity_query(_query_vector(), top_k=3)
        scores = [r[1] for r in res]
        assert scores == sorted(scores, reverse=True)

    def test_decay_lowers_old_chunks(self, store, memory_on):
        old = (datetime.utcnow() - timedelta(days=30)).isoformat(sep=" ")
        _insert(store, "stale", _query_vector(), importance=0.5, last_access=old)
        _insert(store, "fresh", _near_vector(0.9), importance=0.5)

        res = store._cosine_similarity_query(_query_vector(), top_k=2)

        assert [r[0]["chunk_id"] for r in res] == ["fresh", "stale"]

    def test_metadata_carries_memory_fields(self, store, memory_on):
        _insert(store, "c1", _query_vector(), importance=0.7, access_count=5)
        meta = store._cosine_similarity_query(_query_vector(), top_k=1)[0][0]["metadata"]
        assert meta["importance"] == pytest.approx(0.7)
        assert meta["access_count"] == 5
        assert "similarity" in meta

    def test_top_k_is_respected(self, store, memory_on):
        for i in range(10):
            _insert(store, f"c{i}", _near_vector(0.9), importance=i / 10)
        assert len(store._cosine_similarity_query(_query_vector(), top_k=3)) == 3


# --------------------------------------------------------- 检索即强化

class TestReinforcement:
    def test_hit_increments_access_count(self, store, memory_on):
        _insert(store, "c1", _query_vector(), importance=0.5)

        store._cosine_similarity_query(_query_vector(), top_k=1)

        importance, count, last_access = _read_memory(store, "c1")
        assert count == 1
        assert importance == pytest.approx(0.5 * 1.05)
        assert last_access is not None

    def test_non_hit_is_not_reinforced(self, store, memory_on):
        _insert(store, "hit", _query_vector(), importance=0.5)
        _insert(store, "miss", _near_vector(0.1), importance=0.5)

        store._cosine_similarity_query(_query_vector(), top_k=1)

        assert _read_memory(store, "miss")[1] == 0

    def test_repeated_retrieval_accumulates(self, store, memory_on):
        _insert(store, "c1", _query_vector(), importance=0.5)
        for _ in range(3):
            store._cosine_similarity_query(_query_vector(), top_k=1)

        importance, count, _ = _read_memory(store, "c1")
        assert count == 3
        assert importance <= 1.0

    def test_consolidation_flag_set_at_threshold(self, store, memory_on):
        _insert(store, "c1", _query_vector(), importance=0.5)
        for _ in range(3):
            store._cosine_similarity_query(_query_vector(), top_k=1)

        conn = sqlite3.connect(f"file:{store.db_path}?mode=ro", uri=True)
        try:
            consolidated = conn.execute(
                "SELECT consolidated FROM chunks WHERE chunk_id = 'c1'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert consolidated == 1
