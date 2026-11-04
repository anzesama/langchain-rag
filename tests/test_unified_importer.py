import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_importer_init():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    assert importer.vs is not None
    assert importer.wiki_db is not None


def test_split_text():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    text = "这是第一段。\n\n这是第二段。\n\n这是第三段较长内容。" + "x" * 400 + "\n\n这是第四段。"
    chunks = importer._split_text(text, "test.md")
    assert len(chunks) >= 1
    for c in chunks:
        assert hasattr(c, 'page_content')
        assert c.metadata['source'] == 'test.md'


def test_source_fingerprint():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    fp = importer._source_fingerprint("test.md")
    assert isinstance(fp, str)
    assert importer._source_fingerprint("test.md") == fp
    assert importer._source_fingerprint("other.md") != fp


def test_is_imported_false():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    assert importer._is_already_imported("nonexistent_file_xyz123.md") is False


def test_import_chunks():
    """Test that _import_chunks writes to libsql and returns Document list"""
    from rag_core.unified_importer import UnifiedImporter
    from langchain_core.documents import Document
    importer = UnifiedImporter()
    source = "_pytest_import_chunks_test.md"
    # cleanup
    importer.vs.delete_by_source(source)
    fragments = [Document(page_content="test content for embedding chunk test", metadata={"source": source})]
    result = importer._import_chunks(fragments, source, overwrite=False)
    assert len(result) == 1
    assert importer.vs.get_chunk_count(source) >= 1


def test_import_chunks_overwrite():
    """Test overwrite mode deletes old chunks first"""
    from rag_core.unified_importer import UnifiedImporter
    from langchain_core.documents import Document
    importer = UnifiedImporter()
    source = "_pytest_import_overwrite_test.md"
    # cleanup
    importer.vs.delete_by_source(source)
    fragments1 = [Document(page_content="first import", metadata={"source": source})]
    importer._import_chunks(fragments1, source, overwrite=False)
    assert importer.vs.get_chunk_count(source) >= 1
    # overwrite
    fragments2 = [Document(page_content="overwritten", metadata={"source": source})]
    importer._import_chunks(fragments2, source, overwrite=True)
    assert importer.vs.get_chunk_count(source) >= 1


def test_import_entities_and_relations():
    """Test ML text gets entities extracted (jieba only, no LLM API)"""
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    source = "_pytest_entity_import_test.md"
    text = "欠拟合是机器学习中常见的一种现象。训练时如果模型太简单，会出现欠拟合。"
    import os
    os.environ['SKIP_LLM'] = '1'
    try:
        stats = importer._import_entities_and_relations(text, source)
        assert isinstance(stats, dict)
        assert 'entities_added' in stats
        assert 'relations_added' in stats
        assert 'relations_error' in stats, "stats 必须暴露关系抽取错误"
    finally:
        os.environ.pop('SKIP_LLM', None)


def test_step4_uses_single_entry_and_reports_error(monkeypatch):
    """Step 4 必须走 rag_core.relation_extractor，且不抛 AttributeError"""
    import rag_core.relation_extractor as rx
    from rag_core.unified_importer import UnifiedImporter

    called = []

    def _fake(source, domain=None, chunks=None):
        called.append(source)
        return {
            "source": source,
            "entities_count": 0,
            "relations_extracted": 0,
            "relations_imported": 0,
            "error": None,
            "skipped": True,
        }

    monkeypatch.setenv("SKIP_LLM", "1")
    monkeypatch.setattr(rx, "extract_relations_for_source", _fake)

    stats = UnifiedImporter()._import_entities_and_relations("underfitting is common.", "_pytest_step4.md")

    assert called == ["_pytest_step4.md"], "必须调用唯一入口且传入正确 source"
    assert "relations_error" in stats, "stats 必须暴露关系抽取错误"
    assert stats["relations_added"] == 0


def test_step4_skipped_under_skip_llm(monkeypatch):
    """SKIP_LLM=1 时不得构造 LLMRefiner（导入阶段零 LLM 调用）"""
    import rag_core.relation_extractor as rx
    from rag_core.unified_importer import UnifiedImporter

    built = []
    monkeypatch.setenv("SKIP_LLM", "1")
    monkeypatch.setattr(rx, "LLMRefiner", lambda *a, **k: built.append(1))

    UnifiedImporter()._import_entities_and_relations("underfitting is common.", "_pytest_step4_skip.md")

    assert built == []