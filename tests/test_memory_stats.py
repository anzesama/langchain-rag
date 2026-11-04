"""记忆可观测性（Phase 1 任务 7 / 验收 V6）

`VectorStoreManager.get_memories_stats()` 提供聚合数据，
`GET /api/memories/stats` 暴露为只读端点（供观察「知识飞轮」效果）。
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from rag_core.vector_store_libsql import VectorStoreManager

DIM = 512


def _vec():
    v = np.zeros(DIM, dtype=np.float32)
    v[0] = 1.0
    return v


def _insert(vs, chunk_id, importance=0.5, access_count=0, last_access=None,
            memory_type="semantic", consolidated=0, source="doc.txt"):
    conn = sqlite3.connect(str(vs.db_path))
    conn.execute(
        "INSERT INTO chunks (chunk_id, text_content, vector, metadata, source, "
        "importance, access_count, last_access, memory_type, consolidated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (chunk_id, f"text {chunk_id}", vs._vector_to_blob(_vec()),
         json.dumps({"source": source}), source,
         importance, access_count, last_access, memory_type, consolidated),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def store(tmp_path):
    return VectorStoreManager(persist_dir=tmp_path)


class TestMemoriesStats:
    def test_empty_store_does_not_crash(self, store):
        stats = store.get_memories_stats()
        assert stats["total"] == 0
        assert stats["avg_importance"] == 0.0
        assert stats["top_accessed"] == []

    def test_counts_by_memory_type(self, store):
        _insert(store, "c1", memory_type="semantic")
        _insert(store, "c2", memory_type="episodic")
        _insert(store, "c3", memory_type="episodic")

        stats = store.get_memories_stats()

        assert stats["total"] == 3
        assert stats["semantic"] == 1
        assert stats["episodic"] == 2

    def test_average_importance(self, store):
        for i, imp in enumerate([0.9, 0.5, 0.3, 0.7]):
            _insert(store, f"c{i}", importance=imp)
        assert store.get_memories_stats()["avg_importance"] == pytest.approx(0.6)

    def test_top_accessed_is_sorted_and_capped(self, store):
        for i in range(15):
            _insert(store, f"c{i}", access_count=i)
        top = store.get_memories_stats()["top_accessed"]
        assert len(top) == 10
        counts = [t["access_count"] for t in top]
        assert counts == sorted(counts, reverse=True)
        assert top[0]["chunk_id"] == "c14"

    def test_top_accessed_entries_have_expected_keys(self, store):
        _insert(store, "c1", access_count=7, importance=0.8, source="a.md")
        entry = store.get_memories_stats()["top_accessed"][0]
        assert set(entry) >= {"chunk_id", "source", "access_count", "importance"}
        assert entry["source"] == "a.md"

    def test_labels_decayed_chunks(self, store):
        old = (datetime.utcnow() - timedelta(days=60)).isoformat(sep=" ")
        _insert(store, "stale", last_access=old)
        _insert(store, "fresh", last_access=datetime.utcnow().isoformat(sep=" "))
        _insert(store, "never", last_access=None)

        stats = store.get_memories_stats()

        assert stats["decayed_below_threshold"] == 1

    def test_consolidated_count(self, store):
        _insert(store, "c1", access_count=5, consolidated=1)
        _insert(store, "c2", access_count=0, consolidated=0)
        assert store.get_memories_stats()["consolidated"] == 1

    def test_reports_switch_state(self, store, monkeypatch):
        monkeypatch.delenv("RAG_MEMORY_ENABLED", raising=False)
        assert store.get_memories_stats()["memory_enabled"] is False
        monkeypatch.setenv("RAG_MEMORY_ENABLED", "1")
        assert store.get_memories_stats()["memory_enabled"] is True


class TestMemoriesStatsEndpoint:
    def _client(self, monkeypatch, kb):
        import rag_server_v2 as srv
        from fastapi.testclient import TestClient
        monkeypatch.setattr(srv, "get_kb", lambda: kb)
        return TestClient(srv.app)

    def test_returns_stats_payload(self, monkeypatch):
        payload = {
            "total": 3, "semantic": 2, "episodic": 1, "consolidated": 0,
            "avg_importance": 0.5, "top_accessed": [], "decayed_below_threshold": 0,
            "memory_enabled": False,
        }

        class _VS:
            def get_memories_stats(self):
                return payload

        class _KB:
            vector_store = _VS()

        r = self._client(monkeypatch, _KB()).get("/api/memories/stats")

        assert r.status_code == 200
        assert r.json() == payload

    def test_is_read_only(self, monkeypatch):
        """端点不触发导入/重建（纯读）"""
        class _VS:
            def get_memories_stats(self):
                return {"total": 0}

        class _KB:
            vector_store = _VS()
            def __getattr__(self, name):
                raise AssertionError(f"端点不应访问 kb.{name}")

        r = self._client(monkeypatch, _KB()).get("/api/memories/stats")
        assert r.status_code == 200
