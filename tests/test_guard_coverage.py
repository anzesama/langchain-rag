"""生产库守卫的覆盖面（防回归）

2026-11-03 事故后加固：守卫不能只盯 3 个文件 —— `storage/` 下还有
`vector_store.db`、`wiki.db`、`global_counter.json`、`progress_*.json` 等运行时产物。
日志文件（`*.log`）由运行期持续写入，必须排除。
"""
import pytest

from tests.conftest import _guarded_files


def _touch(dirpath, name):
    path = dirpath / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_excludes_log_files(tmp_path):
    _touch(tmp_path, "rag.log")
    _touch(tmp_path, "knowledge_base.db")
    names = {p.name for p in _guarded_files(tmp_path)}
    assert "knowledge_base.db" in names
    assert "rag.log" not in names


def test_excludes_rotated_logs(tmp_path):
    _touch(tmp_path, "rag.log.1")
    assert _guarded_files(tmp_path) == []


@pytest.mark.parametrize("name", [
    "knowledge_base.db",
    "novel_lsh.index",
    "id_map.pkl",
    "vector_store.db",
    "wiki.db",
    "global_counter.json",
    ".import_fingerprints.json",
    "progress_chapter_1158.json",
])
def test_covers_storage_artifacts(tmp_path, name):
    _touch(tmp_path, name)
    assert name in {p.name for p in _guarded_files(tmp_path)}


def test_covers_nested_files(tmp_path):
    _touch(tmp_path, "lsh_index/index.faiss")
    assert any(p.name == "index.faiss" for p in _guarded_files(tmp_path))


def test_missing_directory_is_empty(tmp_path):
    assert _guarded_files(tmp_path / "does_not_exist") == []


def test_ignores_directories(tmp_path):
    (tmp_path / "knowledge_base").mkdir()
    assert _guarded_files(tmp_path) == []
