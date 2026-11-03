"""pytest 全局配置。

背景（2026-11-03 事故）：`tests/` 原先没有 conftest.py，且
`VectorStoreManager.__init__` 忽略 `persist_dir`、永远用全局
`LIBSQL_DICTIONARY_PATH`（生产库）——导致 `pytest tests/` 全量跑一次
就把生产 KB 从 13198 chunks 打成 690 chunks
（`test_delete_collection` 会 drop `chunks` 表）。

本文件提供两道防线：
1. `guard_production_kb`（安全网）：任何测试导致生产存储产物
   （DB / LSH 索引 / ID 映射）指纹变化 → 直接失败
2. `isolate_rag_database`（隔离）：把默认存储路径重定向到临时目录
"""
import sqlite3
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = PROJECT_ROOT / "storage"

# 生产存储产物（任何写入都会改 mtime_ns / size）
GUARDED_FILES = [
    STORAGE_DIR / "knowledge_base.db",
    STORAGE_DIR / "novel_lsh.index",
    STORAGE_DIR / "id_map.pkl",
]


def _chunk_count(db_path: Path):
    """只读方式读取 chunks 数量；库不存在返回 None"""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return None


def _fingerprint(path: Path):
    """文件指纹 (size, mtime_ns)。

    仅用计数不够：`INSERT OR REPLACE` + 确定性 chunk_id 会“替换而非新增”，
    计数不变但已污染生产库（真实发生）。指纹能捕获任何写入。
    """
    if not path.exists():
        return None
    st = path.stat()
    return (st.st_size, st.st_mtime_ns)


def _fingerprints():
    return {p.name: _fingerprint(p) for p in GUARDED_FILES}


@pytest.fixture(autouse=True)
def isolate_rag_database(tmp_path, monkeypatch):
    """把默认存储路径重定向到临时目录。

    覆盖未显式传路径的代码：`VectorStoreManager()`、`UnifiedImporter()`、
    `KnowledgeBase()`、`AutoImportManager()`、`LSHIndexManager()` 等。

    ⚠️ 必须 patch **各模块自己的** 模块级名字：这些模块用
       `from rag_config import ...` 绑定了副本，patch `rag_config` 无效。
    """
    import rag_core.vector_store_libsql as vsmod
    import rag_core.lsh_index as lshmod
    import rag_config

    tmp_dir = tmp_path / "kb_store"
    tmp_db = tmp_path / "knowledge_base.db"
    tmp_lsh = tmp_path / "novel_lsh.index"
    tmp_idmap = tmp_path / "id_map.pkl"

    for mod in (vsmod, rag_config):
        monkeypatch.setattr(mod, "LIBSQL_DICTIONARY_PATH", tmp_db, raising=False)
        monkeypatch.setattr(mod, "VECTOR_STORE_PERSIST_DIR", tmp_dir, raising=False)
        monkeypatch.setattr(mod, "LSH_INDEX_PATH", tmp_lsh, raising=False)
        monkeypatch.setattr(mod, "ID_MAP_PATH", tmp_idmap, raising=False)

    monkeypatch.setattr(lshmod, "LSH_INDEX_PATH", tmp_lsh, raising=False)
    monkeypatch.setattr(lshmod, "ID_MAP_PATH", tmp_idmap, raising=False)

    try:
        import rag_core.parent_document_retriever as pmod
        monkeypatch.setattr(pmod, "VECTOR_STORE_PERSIST_DIR", tmp_dir, raising=False)
    except Exception:
        pass

    yield tmp_db


@pytest.fixture(autouse=True)
def guard_production_kb():
    """安全网：测试前后生产存储产物的指纹必须一致。

    这是 2026-11-03 数据事故（13198 → 690 chunks）的回归防护。
    """
    before = _fingerprints()
    yield
    after = _fingerprints()
    changed = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    assert not changed, (
        f"❌ 测试写入了生产存储产物！(size, mtime_ns) 变化:\n"
        + "\n".join(f"   {k}: {v[0]} -> {v[1]}" for k, v in changed.items())
        + f"\n   目录: {STORAGE_DIR}\n"
        f"   请用 tmp_path 隔离（见 isolate_rag_database），不要直连生产库。"
    )
