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