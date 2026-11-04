"""静态守卫：CLI 不得再含 DB / LLM 逻辑（防止逻辑再次漂移）"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "batch_extract_relations.py"


def _load():
    spec = importlib.util.spec_from_file_location("_batch_cli", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_batch_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_script_has_no_db_or_llm_logic():
    src = SCRIPT.read_text(encoding="utf-8")

    assert "LLMRefiner" not in src, "LLM 构造必须已迁入 rag_core/relation_extractor.py"
    assert "sqlite3" not in src, "CLI 不得直接访问数据库"
    assert "storage/knowledge_base.db" not in src, "不得硬编码 DB 路径"


def test_cli_delegates_to_single_entry():
    mod = _load()
    from rag_core.relation_extractor import extract_relations_for_source

    assert mod.extract_relations_for_source is extract_relations_for_source
