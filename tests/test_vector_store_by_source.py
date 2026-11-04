"""get_chunks_by_source 精确匹配 + list_sources 契约"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.documents import Document


def _vs():
    from rag_core.vector_store_libsql import VectorStoreManager

    return VectorStoreManager()


def _add(vs, source, text):
    vs.delete_by_source(source)
    vs.add_documents([Document(page_content=text, metadata={"source": source})])


def test_get_chunks_by_source_exact_match_not_fuzzy():
    """a.md 不得命中 subdir/a.md（回归 LIKE '%…%' 误伤）"""
    vs = _vs()
    s1, s2 = "_pytest_src_a.md", "subdir/_pytest_src_a.md"
    _add(vs, s1, "alpha body text")
    _add(vs, s2, "beta body text")

    rows = vs.get_chunks_by_source(s1)

    assert len(rows) == 1
    assert rows[0]["text_content"] == "alpha body text"
    assert rows[0]["chunk_text"] == "alpha body text"
    assert rows[0]["chunk_id"]
    assert isinstance(rows[0]["metadata"], dict)


def test_get_chunks_by_source_limit():
    vs = _vs()
    source = "_pytest_src_limit.md"
    vs.delete_by_source(source)
    vs.add_documents(
        [Document(page_content=f"body-{i}", metadata={"source": source}) for i in range(3)]
    )

    assert len(vs.get_chunks_by_source(source)) == 3
    assert len(vs.get_chunks_by_source(source, limit=2)) == 2


def test_get_chunks_by_source_no_match_returns_empty():
    vs = _vs()
    assert vs.get_chunks_by_source("_pytest_never_existed_xyz.md") == []


def test_list_sources_contains_added_source():
    vs = _vs()
    source = "_pytest_src_list.md"
    _add(vs, source, "list me")

    assert source in vs.list_sources()
