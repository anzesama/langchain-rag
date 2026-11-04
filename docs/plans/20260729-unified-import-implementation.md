# 统一文档导入流水线 Implementation Plan

> **REQUIRED SUB-SKILL:** Use the executing-plans skill to implement this plan task-by-task.

**Goal:** 新建 `scripts/import.py`，一条 CLI 命令完成文档 → chunks(LSH同步) → entities(jieba) → relationships(领域词表+LLM可选) 全链路导入

**Architecture:** CLI 解析路径参数 → `UnifiedImporter` 协调三个模块（VectorStoreManager, LLMExtractor, WikiDB, LSHIndexManager）串行四步

**Tech Stack:** argparse, libsql, jieba, sentence-transformers (BGE), LLM API (Agnes)

---

## 依赖分析

| 接口 | 模块 | 状态 |
|------|------|------|
| `VectorStoreManager.add_documents()` | vector_store_libsql.py | ✅ 可用 |
| `VectorStoreManager.delete_by_source()` | vector_store_libsql.py | ✅ 可用 |
| `VectorStoreManager.get_chunk_count(source)` | vector_store_libsql.py | ✅ 可用 |
| `LLMExtractor.extract_all(text, source)` | llm_extractor.py | ✅ 可用 (jieba+LLM) |
| `WikiDB.add_entity()` | wiki_db_libsql.py | ✅ 可用 |
| `WikiDB.add_relationship()` | wiki_db_libsql.py | ✅ 可用 |
| `LSHIndexManager.add_documents()` | lsh_index.py | ✅ 可用 |
| `LSHIndexManager.save_index()` | lsh_index.py | ✅ 可用 |
| 文本分块 | langchain RecursiveCharacterTextSplitter | ✅ 已有 |

---

### Task 1: 创建 UnifiedImporter 模块 + 测试桩

**TDD scenario:** New feature — full TDD cycle

**Files:**
- Create: `rag_core/unified_importer.py`
- Test: `tests/test_unified_importer.py`

**Step 1: 写校验测试（UnitImporter 构造函数和分块接口）**

```python
# tests/test_unified_importer.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_importer_init():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    assert importer.vs is not None
    assert importer.wiki_db is not None
    assert importer.lsh is not None
    assert importer.extractor is not None

def test_split_text():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    chunks = importer._split_text("这是第一段。\n\n这是第二段。", "test.md")
    assert len(chunks) >= 1
    assert all(hasattr(c, 'page_content') for c in chunks)
    assert chunks[0].metadata['source'] == 'test.md'

def test_get_source_fingerprint():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    fp = importer._source_fingerprint("test.md")
    assert isinstance(fp, str)

def test_is_already_imported():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    # 不存在的文件返回 False
    assert importer._is_already_imported("nonexistent_xyz.md") is False
```

**Step 2: 创建空实现**

```python
# rag_core/unified_importer.py
from pathlib import Path
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag_config import logger
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.wiki_db_libsql import get_wiki_db

class UnifiedImporter:
    def __init__(self):
        self.vs = VectorStoreManager()
        self.wiki_db = get_wiki_db()
        self.lsh = None  # 延迟加载（LSH 只在 chunks 表有数据时需要）
        self.extractor = None  # LLMExtractor 延迟加载

    def _split_text(self, text, source):
        pass

    def _source_fingerprint(self, source):
        pass

    def _is_already_imported(self, source):
        pass
```

**Step 3: 跑测试**  
Run: `pytest tests/test_unified_importer.py -v --no-header`  
Expected: FAIL（AttributeError 抛接口未实现）

**Step 4: 写实现让测试通过**

**Step 5: Commit**  
```bash
git add tests/test_unified_importer.py rag_core/unified_importer.py
git commit -m "test: UnifiedImporter 基础结构 + 分块/指纹接口测试"
```

---

### Task 2: 实现 Step 1 — 分块 + embedding 入库

**TDD scenario:** Extending tested code — 在现有桩上添加功能

**Files:**
- Modify: `rag_core/unified_importer.py`

**Step 1: 补充测试**

```python
# tests/test_unified_importer.py 追加
def test_import_chunks_to_libsql():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    fragments = [Document(page_content="test content for embedding", metadata={"source": "test_import.md"})]
    chunks = importer._import_chunks(fragments, "test_import.md", overwrite=False)
    assert len(chunks) = len(fragments)

    # 验证已写库
    count = importer.vs.get_chunk_count("test_import.md")
    assert count >= 1

    # 清理
    importer.vs.delete_by_source("test_import.md")

def test_overwrite_chunks():
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter()
    fragments = [Document(page_content="test overwrite", metadata={"source": "test_ow.md"})]
    importer._import_chunks(fragments, "test_ow.md", overwrite=True)
    fragments2 = [Document(page_content="replaced", metadata={"source": "test_ow.md"})]
    importer._import_chunks(fragments2, "test_ow.md", overwrite=True)
    # 验证已被替换
    count = importer.vs.get_chunk_count("test_ow.md")
    assert count >= 1  # TODO 替换逻辑
    importer.vs.delete_by_source("test_ow.md")
```

**Step 2: 实现 `_import_chunks()`**——调用 `VectorStoreManager.add_documents()`、处理 overwrite 时 `delete_by_source()`

**Step 3: 跑测试确保通过**

**Step 4: Commit**

---

### Task 3: 实现 Step 2 + Step 3 — jieba 实体提取 + 领域词表关系

**TDD scenario:** Extend test suite with integration test

**Files:**
- Modify: `rag_core/unified_importer.py`

**Step 1: 写 LLM Extractor 调用的集成测试**

```python
def test_import_entities_and_relations_from_jieba():
    import rag_core.wiki_db_libsql as wiki_db_module
    importer = UnifiedImporter()
    wiki_db = importer.wiki_db

    # 检查清理（避免已有数据干扰）
    importer._import_entities_and_relations("欠拟合是机器学习中常见的一种现象", "test_jieba.md")
    # 验证实体入库
    assert wiki_db.entity_exists("欠拟合")
    assert wiki_db.entity_exists("机器学习")
```

**Step 2: 实现 `_import_entities_and_relations()`**——调 `LLMExtractor.extract_all()` → 写 entities → 写 relationships（默认 SKIP_LLM）

**Step 3: 跑测试确保通过**

**Step 4: Commit**

---

### Task 4: 实现 Step 4 — LLM 精炼低置信度关系（可选）

**TDD scenario:** Trivial — 标记控制

**Step 1: 实现 `_refine_relations_with_llm()`**——调 `LLMExtractor._llm_extract()` 对 `all_entities` 结果重新做关系提取，用 jieba 基准过滤

**Step 2: Commit**

---

### Task 5: 实现 LSH 同步

**TDD scenario:** Modify existing code

**Step 1: 在 `_import_chunks()` 末尾加 LSH 同步**

```python
if self.lsh and len(chunks) > 0:
    embeddings = get_embeddings([c.page_content for c in chunks])
    self.lsh.add_documents(chunks, embeddings)
    self.lsh.save_index()
```

**Step 2: Commit**

---

### Task 6: 创建 CLI 入口 — `scripts/import.py`

**Step 1: 实现 argparse + 主流程**

```python
python scripts/import.py <path> [--llm] [--overwrite] [--steps 1,2,3,4]
```

**Step 2: 扫描文件 → import 循环**

**Step 3: 输出统计**（完成摘要）

**Step 4: Commit**

---

### Task 7: 端到端验证 — 导入 AAAMLP-CN

**Step 1: 跑 `python scripts/import.py documents/AAAMLP-CN/`**

```bash
python scripts/import.py documents/AAAMLP-CN/
```

预期输出格式：
```
Processing 15 files...
  [1/15] README.md → 3 chunks, 2 entities, 1 relation
  ...
Done. 15 files, 630 chunks, 125 entities, 55 relations
```

**Step 2: 验证结果 (chunks/entities/relationships)**

**Step 3: 验证增量模式（重复执行不报错）**

**Step 4: Commit**

---

### Task 8: 更新文档 + troubleshooting

- README.md: 添加 import.py 用法
- troubleshooting.md: ChromeDB 已删、vector_store.py → vector_store_libsql.py、LLM 在 import 中默认关闭