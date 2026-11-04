"""记忆字段的 DB 迁移（Phase 1 任务 1 / 验收 V1）

零侵入原则：`ALTER TABLE ADD COLUMN`，全部带默认值 → 可回滚、无需重建表。
迁移必须**幂等**，且**不丢数据**（这是 2026-11-03 数据事故的直接教训）。
"""
import sqlite3

import pytest

from rag_core.vector_store_libsql import VectorStoreManager

MEMORY_COLUMNS = {"importance", "access_count", "last_access", "memory_type", "consolidated"}

LEGACY_SCHEMA = """
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    text_content TEXT NOT NULL,
    vector BLOB NOT NULL,
    metadata TEXT,
    source TEXT,
    page_number TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _columns(db_path) -> set:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    finally:
        conn.close()


def _make_legacy_db(db_path, rows=1):
    conn = sqlite3.connect(str(db_path))
    conn.execute(LEGACY_SCHEMA)
    for i in range(rows):
        conn.execute(
            "INSERT INTO chunks (chunk_id, text_content, vector) VALUES (?, ?, ?)",
            (f"old_{i}", f"legacy text {i}", b"\x00" * 2048),
        )
    conn.commit()
    conn.close()


class TestFreshDatabase:
    def test_has_memory_columns(self, tmp_path):
        vs = VectorStoreManager(persist_dir=tmp_path)
        assert MEMORY_COLUMNS <= _columns(vs.db_path)

    def test_new_row_gets_defaults(self, tmp_path):
        vs = VectorStoreManager(persist_dir=tmp_path)
        conn = sqlite3.connect(str(vs.db_path))
        conn.execute(
            "INSERT INTO chunks (chunk_id, text_content, vector) VALUES (?, ?, ?)",
            ("c1", "hello", vs._vector_to_blob([0.0] * 512)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT importance, access_count, last_access, memory_type, consolidated "
            "FROM chunks WHERE chunk_id = 'c1'"
        ).fetchone()
        conn.close()

        assert row[0] == pytest.approx(0.5)   # importance
        assert row[1] == 0                    # access_count
        assert row[2] is None                 # last_access
        assert row[3] == "semantic"           # memory_type
        assert row[4] == 0                    # consolidated


class TestLegacyMigration:
    def test_adds_memory_columns(self, tmp_path):
        _make_legacy_db(tmp_path / "knowledge_base.db")
        vs = VectorStoreManager(persist_dir=tmp_path)
        assert MEMORY_COLUMNS <= _columns(vs.db_path)

    def test_preserves_existing_rows(self, tmp_path):
        _make_legacy_db(tmp_path / "knowledge_base.db", rows=3)
        vs = VectorStoreManager(persist_dir=tmp_path)

        conn = sqlite3.connect(f"file:{vs.db_path}?mode=ro", uri=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            texts = {r[0] for r in conn.execute("SELECT text_content FROM chunks")}
            vec_len = conn.execute("SELECT length(vector) FROM chunks LIMIT 1").fetchone()[0]
        finally:
            conn.close()

        assert count == 3
        assert texts == {"legacy text 0", "legacy text 1", "legacy text 2"}
        assert vec_len == 2048  # 向量未被破坏

    def test_migrated_rows_get_defaults(self, tmp_path):
        _make_legacy_db(tmp_path / "knowledge_base.db")
        vs = VectorStoreManager(persist_dir=tmp_path)

        conn = sqlite3.connect(f"file:{vs.db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT importance, access_count, memory_type, consolidated FROM chunks LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        assert row[0] == pytest.approx(0.5)
        assert row[1] == 0
        assert row[2] == "semantic"
        assert row[3] == 0

    def test_is_idempotent(self, tmp_path):
        _make_legacy_db(tmp_path / "knowledge_base.db")
        VectorStoreManager(persist_dir=tmp_path)
        VectorStoreManager(persist_dir=tmp_path)   # 第二次不应抛异常
        assert MEMORY_COLUMNS <= _columns(tmp_path / "knowledge_base.db")

    def test_existing_indexes_survive(self, tmp_path):
        _make_legacy_db(tmp_path / "knowledge_base.db")
        vs = VectorStoreManager(persist_dir=tmp_path)
        conn = sqlite3.connect(f"file:{vs.db_path}?mode=ro", uri=True)
        try:
            idx = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='chunks'"
            )}
        finally:
            conn.close()
        assert {"idx_chunks_source", "idx_chunks_created"} <= idx


class TestMigrationRaceSafety:
    """两个进程同时启动时，重复 ALTER 不应让 __init__ 崩溃（审查发现 I3）。

    注：SQLite **不支持** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（已实测 3.51.2 报语法错误），
    因此必须靠捕获 OperationalError 实现幂等。
    """

    def test_add_column_helper_tolerates_duplicate(self, tmp_path):
        db = tmp_path / "race.db"
        conn = sqlite3.connect(str(db))
        conn.execute(LEGACY_SCHEMA)
        # 模拟“另一进程”已经加过该列
        conn.execute("ALTER TABLE chunks ADD COLUMN importance REAL DEFAULT 0.5")
        conn.commit()

        # 本进程的重复 ALTER 不应抛异常
        VectorStoreManager._add_column_if_missing(
            conn.cursor(), "importance", "REAL DEFAULT 0.5"
        )
        conn.close()

    def test_migration_still_works_after_partial_race(self, tmp_path):
        db = tmp_path / "knowledge_base.db"
        _make_legacy_db(db)
        conn = sqlite3.connect(str(db))
        conn.execute("ALTER TABLE chunks ADD COLUMN importance REAL DEFAULT 0.5")
        conn.execute("ALTER TABLE chunks ADD COLUMN access_count INTEGER DEFAULT 0")
        conn.commit()
        conn.close()

        vs = VectorStoreManager(persist_dir=tmp_path)   # 补齐剩余 3 列

        assert MEMORY_COLUMNS <= _columns(vs.db_path)
        conn = sqlite3.connect(f"file:{vs.db_path}?mode=ro", uri=True)
        try:
            assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1
        finally:
            conn.close()
