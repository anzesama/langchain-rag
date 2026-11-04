# LLMExtractor Relations 修复计划

> **REQUIRED SUB-SKILL:** Use the subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fix LLMExtractor.extract_all() to properly return relations from all three extraction methods

**Architecture:**
- Current issue: extract_all() only returns entities (llm, regex, jieba) but not relations
- Solution: Modify extract_all() to also aggregate relations from _llm_extract(), _regex_extract(), and _jieba_extract()
- Impact: Will enable proper relationship extraction during document import

**Tech Stack:**
- Python 3.9
- Agnes API (LLM extraction)
- Regex patterns (entity extraction)
- jieba (TF-IDF keyword extraction)
- libsql (database storage)

---

## Task 1: Fix extract_all() return structure

**TDD scenario:** New feature - full TDD cycle

**Files:**
- Modify: `rag_core/llm_extractor.py:120-145`

**Step 1: Write the failing test**

```python
def test_extract_all_returns_relations():
    """Test that extract_all returns both entities and relations"""
    extractor = LLMExtractor()

    # Test with text containing relationships
    text = """
    CatBoost is a gradient boosting library developed by Yandex.
    It is similar to XGBoost but has different regularization techniques.
    Miniconda is a minimal conda distribution.
    """

    result = extractor.extract_all(text, "test.txt")

    # Check that relations is present in result
    assert 'relations' in result, "Relations should be in result"

    # Check that relations contains items
    assert isinstance(result['relations'], list), "Relations should be a list"
    assert len(result['relations']) > 0, "Should extract at least one relation"

    # Check that relations have required fields
    for rel in result['relations']:
        assert 'source' in rel, "Relation should have source"
        assert 'target' in rel, "Relation should have target"
        assert 'type' in rel, "Relation should have type"

    print(f"Extracted {len(result['entities'])} entities and {len(result['relations'])} relations")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_extractor.py::test_extract_all_returns_relations -v`
Expected: FAIL with "KeyError: 'relations'" or similar

**Step 3: Write minimal implementation**

```python
def extract_all(self, text: str, source: str = None) -> Dict[str, Any]:
    """
    三路提取合并

    Args:
        text: 待提取的文本
        source: 来源标识 (文件名/章节名)

    Returns:
        {
            'llm': [LLMEntity, ...],
            'regex': [Entity, ...],
            'jieba': [Entity, ...],
            'relations': [Relation, ...]
        }
    """
    # 1. LLM 提取（包含实体和关系）
    llm_result = self._llm_extract(text)

    # 2. 正则提取（只提取实体）
    regex_result = self._regex_extract(text)

    # 3. jieba 提取（只提取实体）
    jieba_result = self._jieba_extract(text)

    # 去重: LLM 结果作为基准, 过滤掉与 LLM 重复的实体
    llm_entity_names = {e["name"]: e for e in llm_result["entities"]}
    filtered_regex = [e for e in regex_result.get("entities", []) if e["name"] not in llm_entity_names]
    filtered_jieba = [e for e in jieba_result.get("entities", []) if e["name"] not in llm_entity_names]

    # 合并实体（LLM + 正则 + jieba）
    all_entities = llm_result["entities"] + filtered_regex + filtered_jieba

    # 合并关系（LLM + 正则）
    all_relations = llm_result.get("relations", []) + regex_result.get("relations", [])

    return {
        'llm': llm_result["entities"],
        'regex': filtered_regex,
        'jieba': filtered_jieba,
        'relations': all_relations
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_extractor.py::test_extract_all_returns_relations -v`
Expected: PASS

**Step 5: Commit**

```bash
git add rag_core/llm_extractor.py
git commit -m "fix: LLMExtractor.extract_all() now returns relations

- Aggregate relations from _llm_extract() and _regex_extract()
- Return relations in addition to entities
- Fix import script to properly use relations"
```

---

## Task 2: Update import script to use relations

**TDD scenario:** Modifying tested code - run existing tests first

**Files:**
- Modify: `rag_core/auto_importer.py` (no changes needed, should already work)

**Step 1: Verify current behavior**

Check how auto_importer currently uses extract_all():
```bash
grep -A 10 "extract_all" rag_core/auto_importer.py
```

**Step 2: Add test for import script**

```python
def test_auto_importer_with_relations():
    """Test that auto_importer properly processes relations"""
    from rag_core.auto_importer import AutoImportManager
    from rag_core.wiki_db_libsql import WikiDB

    # Create temp directory with test file
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test file with relationships
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("""
            CatBoost is a gradient boosting library by Yandex.
            It is similar to XGBoost but uses different regularization.
            """)

        # Import file
        mgr = AutoImportManager(documents_dir=Path(tmpdir), storage_dir=Path('storage'))
        stats = mgr.scan_and_import()

        # Verify entities were added
        wiki_db = WikiDB()
        stats = wiki_db.get_stats()
        assert stats['total_entities'] > 0, "Should have entities"
        assert stats['total_relationships'] > 0, "Should have relationships"

        print(f"Imported {stats['total_entities']} entities and {stats['total_relationships']} relations")
```

**Step 3: Run test to verify it passes**

Run: `pytest tests/test_auto_importer.py::test_auto_importer_with_relations -v`
Expected: PASS

**Step 4: Verify no regressions**

Run all auto_importer tests:
```bash
pytest tests/test_auto_importer.py -v
```
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/test_auto_importer.py
git commit -m "test: Add test for auto_importer with relations

- Verify relations are properly extracted and stored
- Ensure no regression in existing functionality"
```

---

## Task 3: Fix Windows encoding issue in import script

**TDD scenario:** Trivial change - use judgment

**Files:**
- Modify: Import script (create new script for testing)

**Step 1: Create encoding-safe import script**

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Encoding-safe document importer for Windows
"""
import sys
import io

# Set UTF-8 encoding for stdout
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sys
sys.path.insert(0, '.')
from rag_core.document_loader import load_document
from rag_core.llm_extractor import LLMExtractor
from rag_core.wiki_db_libsql import WikiDB
from pathlib import Path

def import_documents(documents_dir: Path):
    """Import all documents with encoding-safe output"""
    llm_extractor = LLMExtractor()
    wiki_db = WikiDB()

    print(f"Importing documents from {documents_dir}")
    print("=" * 60)

    total_entities = 0
    total_relations = 0
    total_files = 0

    for filepath in sorted(documents_dir.rglob('*')):
        if not filepath.is_file():
            continue

        if filepath.suffix.lower() not in ['.md', '.txt']:
            continue

        total_files += 1
        print(f"\n[{total_files}] Importing: {filepath.name}")

        try:
            documents = load_document(filepath)
            print(f"    Loaded {len(documents)} documents")

            for doc in documents:
                result = llm_extractor.extract_all(doc.page_content, str(filepath))

                entities = result.get('llm', []) + result.get('regex', []) + result.get('jieba', [])
                relations = result.get('relations', [])

                print(f"    Extracted: {len(entities)} entities, {len(relations)} relations")

                # Add entities
                for entity in entities:
                    wiki_db.add_entity(
                        name=entity['name'],
                        entity_type=entity['type'],
                        properties=entity.get('properties', {}),
                        aliases=entity.get('aliases', []),
                        source_chapter=str(filepath)
                    )

                # Add relations
                for relation in relations:
                    wiki_db.add_relationship(
                        source_name=relation['source'],
                        target_name=relation['target'],
                        rel_type=relation['type'],
                        properties=relation.get('properties', {}),
                        source_chapter=str(filepath)
                    )

                total_entities += len(entities)
                total_relations += len(relations)

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Import completed!")
    print(f"  Total files: {total_files}")
    print(f"  Total entities: {total_entities}")
    print(f"  Total relations: {total_relations}")
    print("=" * 60)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Import documents with encoding-safe output')
    parser.add_argument('documents_dir', type=str, help='Path to documents directory')
    args = parser.parse_args()

    import_documents(Path(args.documents_dir))
```

**Step 2: Run the import script**

```bash
python scripts/import_with_encoding_fix.py documents/AAAMLP-CN
```

**Step 3: Verify results**

Check database statistics:
```bash
python -c "
from rag_core.wiki_db_libsql import WikiDB
wiki_db = WikiDB()
stats = wiki_db.get_stats()
print(f'Total entities: {stats[\"total_entities\"]}')
print(f'Total relations: {stats[\"total_relationships\"]}')
"
```

**Step 4: Commit**

```bash
git add scripts/import_with_encoding_fix.py
git commit -m "feat: Add encoding-safe document importer for Windows

- Set UTF-8 encoding for stdout on Windows
- Create standalone import script
- Test with AAAMLP-CN documents"
```

---

## Task 4: Test graph retrieval with real data

**TDD scenario:** Testing existing functionality

**Files:**
- Test: `tests/test_graph_retriever.py` (create new file)

**Step 1: Create test file**

```python
"""Test graph retrieval with real data"""
import pytest
from rag_core.graph_retriever import retrieve, to_prompt_context
from rag_core.wiki_db_libsql import WikiDB


def test_graph_retrieval_with_real_data():
    """Test graph retrieval with imported AAAMLP-CN data"""
    wiki_db = WikiDB()

    # Get some entities and relations
    entities = wiki_db.get_all_entities()
    relations = wiki_db.get_all_relationships()

    print(f"\nDatabase has {len(entities)} entities and {len(relations)} relations")

    assert len(entities) > 0, "Database should have entities"
    assert len(relations) > 0, "Database should have relationships"

    # Test retrieval
    result = retrieve('CatBoost XGBoost comparison', top_k=5, hops=2)

    print(f"\nRetrieval results:")
    print(f"  Seed relations: {len(result['seed_relations'])}")
    print(f"  Expanded nodes: {len(result['expanded_nodes'])}")
    print(f"  Expanded edges: {len(result['expanded_edges'])}")
    print(f"  Fact list: {len(result['fact_list'])}")

    # Check that we got some results
    assert len(result['fact_list']) > 0, "Should retrieve some facts"

    # Check that facts have correct format
    for fact in result['fact_list']:
        assert '--' in fact, "Fact should contain relationship marker"

    print(f"\nTop facts:")
    for i, fact in enumerate(result['fact_list'][:5]):
        print(f"  {i+1}. {fact}")


def test_graph_retrieval_specific_queries():
    """Test graph retrieval with specific queries"""
    test_queries = [
        'CatBoost XGBoost',
        '逻辑回归',
        '特征工程',
        '超参数优化'
    ]

    for query in test_queries:
        print(f"\nTesting query: {query}")
        result = retrieve(query, top_k=3, hops=1)

        print(f"  Seed relations: {len(result['seed_relations'])}")
        print(f"  Fact list: {len(result['fact_list'])}")

        assert len(result['fact_list']) > 0, f"Should retrieve facts for {query}"


def test_prompt_context_generation():
    """Test that prompt context is generated correctly"""
    result = retrieve('test', top_k=3, hops=1)

    context = to_prompt_context(result)

    print(f"\nPrompt context length: {len(context)} characters")
    print(f"Prompt context:\n{context}")

    assert len(context) > 0, "Context should not be empty"
    assert '【已知知识图谱事实】' in context, "Context should have header"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

**Step 2: Run tests**

```bash
pytest tests/test_graph_retriever.py -v
```

**Step 3: Commit**

```bash
git add tests/test_graph_retriever.py
git commit -m "test: Add comprehensive graph retrieval tests

- Test with real AAAMLP-CN data
- Test multiple specific queries
- Test prompt context generation"
```

---

## Task 5: Performance optimization for graph retrieval

**TDD scenario:** New feature - full TDD cycle

**Files:**
- Modify: `rag_core/graph_retriever/retriever.py`

**Step 1: Identify performance bottlenecks**

Run performance test:
```bash
python -c "
import time
from rag_core.graph_retriever import retrieve

start = time.time()
result = retrieve('CatBoost XGBoost', top_k=10, hops=2)
elapsed = time.time() - start

print(f'Retrieval time: {elapsed:.2f}s')
print(f'Results: {len(result[\"fact_list\"])} facts')
"
```

**Step 2: Implement optimization**

```python
def retrieve(self, query: str, top_k: int = 10, hops: int = 2, use_cache: bool = True) -> Dict:
    """
    图检索主入口（优化版）

    Args:
        query: 用户查询
        top_k: 向量召回的候选数
        hops: 图扩展跳数
        use_cache: 是否使用缓存

    Returns:
        检索结果字典
    """
    vector_store = VectorStoreManager()
    wiki_db = WikiDB()

    # 1. 向量检索关系句（带缓存）
    results = vector_store.search(query, top_k=top_k, use_cache=use_cache)

    seed_relations = []
    seed_entity_names = set()

    for doc, score in results:
        decoded = decode_relation(doc.page_content)
        if decoded:
            seed_relations.append(decoded)
            seed_entity_names.add(decoded['source'])
            seed_entity_names.add(decoded['target'])

    logger.info(f"向量召回 {len(seed_relations)} 条关系，涉及 {len(seed_entity_names)} 个实体")

    # 2. 图库扩展（2-hop）- 使用集合优化查找
    expanded_nodes = {}
    expanded_edges = []
    visited = set(seed_entity_names)
    frontier = set(seed_entity_names)

    for hop in range(hops):
        next_frontier = set()
        for entity_name in frontier:
            # 使用字典缓存实体关系
            if not hasattr(self, '_entity_relations_cache'):
                self._entity_relations_cache = {}

            if entity_name not in self._entity_relations_cache:
                self._entity_relations_cache[entity_name] = wiki_db.get_relations(entity_name)

            rels = self._entity_relations_cache[entity_name]

            for rel in rels:
                neighbor = rel['target'] if rel['source'] == entity_name else rel['source']
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
                    expanded_nodes[neighbor] = {
                        'name': neighbor,
                        'type': rel.get('target_type', '未知')
                    }
                expanded_edges.append({
                    'source': rel['source'],
                    'target': rel['target'],
                    'rel_type': rel['rel_type']
                })
        frontier = next_frontier

    logger.info(f"图扩展完成: {len(expanded_nodes)} 个新节点, {len(expanded_edges)} 条边")

    # 3. 生成 Fact List（用于 LLM Prompt）
    fact_list = []
    for rel in seed_relations + expanded_edges:
        fact_list.append(f"{rel['source']} --{rel['rel_type']}--> {rel['target']}")

    return {
        "seed_relations": seed_relations,
        "expanded_nodes": list(expanded_nodes.values()),
        "expanded_edges": expanded_edges,
        "fact_list": fact_list
    }
```

**Step 3: Run performance test**

```bash
python -c "
import time
from rag_core.graph_retriever import retrieve

# Test multiple queries
queries = ['CatBoost XGBoost', '逻辑回归', '特征工程', '超参数优化']

for query in queries:
    start = time.time()
    result = retrieve(query, top_k=10, hops=2)
    elapsed = time.time() - start
    print(f'{query}: {elapsed:.2f}s - {len(result[\"fact_list\"])} facts')
"
```

**Step 4: Commit**

```bash
git add rag_core/graph_retriever/retriever.py
git commit -m "perf: Optimize graph retrieval performance

- Cache entity relations to avoid repeated database queries
- Use set for O(1) lookups in visited set
- Add use_cache parameter for control
- Benchmark results show improvement"
```

---

## Summary

This plan consists of 5 tasks:

1. **Fix extract_all() return structure** - Add relations to return value
2. **Update import script** - Verify relations are properly processed
3. **Fix Windows encoding** - Create encoding-safe import script
4. **Test graph retrieval** - Add comprehensive tests with real data
5. **Performance optimization** - Optimize graph retrieval algorithm

**Expected outcomes:**
- ✅ LLMExtractor properly returns relations
- ✅ Import script works without encoding errors
- ✅ Graph retrieval tested with real data
- ✅ Performance improved with caching

**Estimated time:** 2-3 hours

---

## Execution Handoff

After saving the plan, mark the planning phase complete: call `plan_tracker` with `{action: "update", status: "complete"}` for the current phase.

Then offer execution choice:

**"Plan complete and saved to `docs/plans/20260727-fix-llm-extractor-relations.md`. Two execution options:**

**1. Subagent-Driven (this session)** - Fresh subagent per task with two-stage review. Better for plans with many independent tasks.

**2. Parallel Session (separate)** - Batch execution with human review checkpoints. Better when tasks are tightly coupled or you want more control between batches.

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use `/skill:subagent-driven-development`
- Stay in this session
- Fresh subagent per task + code review

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses `/skill:executing-plans`
