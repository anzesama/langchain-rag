"""pytest 全局配置。

背景（2026-11-03 事故）：`tests/` 原先没有 conftest.py，且
`VectorStoreManager.__init__` 忽略 `persist_dir`、永远用全局
`LIBSQL_DICTIONARY_PATH`（生产库）——导致 `pytest tests/` 全量跑一次
就把生产 KB 从 13198 chunks 打成 690 chunks。

本文件提供两道防线：
1. `isolate_rag_database`（隔离）：把默认存储路径重定向到临时目录
2. `guard_production_kb`（安全网）：任何测试导致 `storage/` 下运行期产物
   指纹变化 → 直接失败

⚠️ 踩坑记录（2026-11-04，本文件自查发现）：
   隔离 fixture 曾用 `sys.modules` 扫描来 patch 同名路径常量，结果**把本模块自己的
   `STORAGE_DIR` 也 patch 成了临时目录** —— 之后所有 `_is_under(v, STORAGE_DIR)`
   的比较基准都变成临时目录，导致真正的 `rag_config.*` 一个都没被 patch
   （守卫因此抓到测试直接写生产库）。
   修法：① 用**不可变常量**做基准 ② 跳过 conftest 自身。
"""
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 生产存储目录 —— **只读基准，任何情况下都不得被 patch**
PRODUCTION_STORAGE = PROJECT_ROOT / "storage"

#: 需要重定向的「路径型」配置常量（值必须指向生产 storage/ 才会被替换）
PATH_CONSTANTS = (
    "LIBSQL_DICTIONARY_PATH",
    "VECTOR_STORE_PERSIST_DIR",
    "LSH_INDEX_PATH",
    "ID_MAP_PATH",
    "STORAGE_DIR",
    "LOAD_STATE_PATH",
)


# --------------------------------------------------------------- 守卫实现

def _is_log_file(name: str) -> bool:
    """日志由运行期持续写入，不纳入指纹守卫"""
    return name.endswith(".log") or ".log." in name


def _guarded_files(storage_dir=None):
    """`storage/` 下所有运行期产物（递归，排除日志）。

    只盯 3 个文件是不够的：`vector_store.db` / `wiki.db` / `global_counter.json` /
    `progress_*.json` 同样是生产状态，被测试写坏一样是数据事故。
    """
    root = Path(storage_dir) if storage_dir is not None else PRODUCTION_STORAGE
    if not root.exists():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not _is_log_file(path.name)
    ]


def _fingerprint(path: Path):
    """文件指纹 (size, mtime_ns)。

    仅用计数不够：`INSERT OR REPLACE` + 确定性 chunk_id 会“替换而非新增”，
    计数不变但已污染生产库（真实发生）。
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _fingerprints():
    return {
        str(path.relative_to(PRODUCTION_STORAGE)): _fingerprint(path)
        for path in _guarded_files(PRODUCTION_STORAGE)
    }


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _is_conftest_module(module) -> bool:
    """不要 patch 本文件自己，否则会破坏 PRODUCTION_STORAGE 的基准语义"""
    name = getattr(module, "__name__", "") or ""
    return name == "conftest" or name.endswith(".conftest")


# --------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def isolate_rag_database(tmp_path, monkeypatch):
    """把默认存储路径重定向到临时目录。

    ⚠️ 必须 patch **各模块自己的** 模块级名字：这些模块用
       `from rag_config import ...` 绑定了副本，patch `rag_config` 无效。
       因此这里扫描 `sys.modules`，凡是值为「生产 storage/ 下的 Path」
       的同名常量一律替换 —— 新模块自动覆盖，不需要手工维护清单。
    """
    tmp_dir = tmp_path / "kb_store"
    replacements = {
        "LIBSQL_DICTIONARY_PATH": tmp_dir / "knowledge_base.db",
        "VECTOR_STORE_PERSIST_DIR": tmp_dir,
        "LSH_INDEX_PATH": tmp_dir / "novel_lsh.index",
        "ID_MAP_PATH": tmp_dir / "id_map.pkl",
        "STORAGE_DIR": tmp_dir,
        "LOAD_STATE_PATH": tmp_dir / "load_state.json",
    }

    # 先尽量加载相关模块，保证它们在 sys.modules 里被扫描到
    for module_name in (
        "rag_config",
        "rag_core.vector_store_libsql",
        "rag_core.lsh_index",
        "rag_core.wiki_db_libsql",
        "rag_core.knowledge_base",
        "rag_core.auto_importer",
        "rag_core.unified_importer",
        "rag_core.parent_document_retriever",
    ):
        try:
            __import__(module_name)
        except Exception:
            pass

    # WikiDB 是全局单例：必须重置，否则后续测试会复用上一个测试的临时库
    wiki_module = sys.modules.get("rag_core.wiki_db_libsql")
    if wiki_module is not None:
        monkeypatch.setattr(wiki_module, "_wiki_db_instance", None, raising=False)

    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__dict__", None):
            continue
        if _is_conftest_module(module):
            continue
        for name in PATH_CONSTANTS:
            current = getattr(module, name, None)
            if isinstance(current, Path) and _is_under(current, PRODUCTION_STORAGE):
                monkeypatch.setattr(module, name, replacements[name], raising=False)

    yield tmp_dir


@pytest.fixture(autouse=True)
def guard_production_kb():
    """安全网：测试前后 `storage/` 运行期产物的指纹必须一致。

    这是 2026-11-03 数据事故（13198 → 690 chunks）的回归防护。
    """
    before = _fingerprints()
    yield
    after = _fingerprints()

    changed = {
        name: (before.get(name), after.get(name))
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    }
    assert not changed, (
        f"❌ 测试写入了生产存储产物！(size, mtime_ns) 变化:\n"
        + "\n".join(f"   {k}: {v[0]} -> {v[1]}" for k, v in sorted(changed.items()))
        + f"\n   目录: {PRODUCTION_STORAGE}\n"
        f"   请用 tmp_path 隔离（见 isolate_rag_database），不要直连生产库。"
    )
