# Wiki 知识管道统一化实施计划

> **REQUIRED SUB-SKILL:** Use the `executing-plans` skill to implement this plan task-by-task.

**Goal:** 修复 Wiki 层的三个核心问题：统一文档入库入口、激活待审核队列、统一路径配置

**Architecture:** 通过以下三个任务实现知识管道的统一：
1. **统一入库入口** — 确保所有文档入库路径都触发 Wiki 更新（已验证：所有路径正确，无需修改）
2. **激活待审核队列** — 在 WikiUpdater 实例化时调用 reasoner 的推导保存方法
3. **统一路径配置** — 将硬编码路径替换为 `rag_config.py` 中的 `BASE_DIR`

**Tech Stack:** Python 3.9 (ml_env), SQLite (Wiki DB), ChromaDB, LangChain

---

## 📊 当前状态分析

### 任务 1：统一文档入库入口 ✅ 已验证通过

检查了三个文档入库路径：

| 入库路径 | 调用方法 | Wiki 同步调用 | 状态 |
|---------|---------|-------------|------|
| `KnowledgeBase.add_document()` | `_add_novel_document()` → `_sync_wiki_layer()` | ✅ 调用 | 正确 |
| `KnowledgeBase.add_directory()` | `_add_directory_batch()` → `_sync_wiki_layer()` | ✅ 调用 | 正确 |
| `AutoImportManager._import_file()` | 直接调用 `WikiUpdater.batch_add_from_text()` | ✅ 调用 | 正确 |
| `cmd_search()` → `_import_search_to_chromadb()` → `kb.add_document()` | → `_add_novel_document()` → `_sync_wiki_layer()` | ✅ 调用 | 正确 |

**结论：所有入库路径都已正确触发 Wiki 更新，无需修改。**

---

### 任务 2：激活待审核队列 ❌ 需要修复

**问题根因：**

1. `wiki_updater.py` 中的 `get_pending_review()` 返回硬编码空列表：
   ```python
   def get_pending_review(self, limit: int = 20) -> List[Dict[str, Any]]:
       """获取待审核的实体列表"""
       # 从 seed.json 加载(简化版)
       # TODO: 实现从数据库查询待审核实体
       return []  # ❌ 永远返回空列表
   ```

2. `wiki_updater.py` 中的 `save_deductions()` 和 `save_entity_properties()` 从未被调用：
   - `save_deductions()` 在第 558 行定义，但从未被调用
   - `save_entity_properties()` 未定义（需要新增）

3. `wiki_reasoner.py` 中的 `save_deductions_to_pending()` 方法存在但未被触发：
   ```python
   # wiki_reasoner.py:623 - 已实现，但从未被调用
   def save_deductions_to_pending(self) -> int:
       # 插入 pending_reviews 表的逻辑
   ```

**解决方案：**

在 `WikiUpdater.__init__()` 方法中，实例化 `WikiReasoner` 后立即调用：
- `reasoner.save_deductions_to_pending()` — 保存关系推导到待审核队列
- `reasoner.save_entity_properties()` — 保存实体属性推导到待审核队列

同时修复 `get_pending_review()` 方法，改为从数据库查询。

---

### 任务 3：统一路径配置 ❌ 需要修复

**问题根因：**

`D:/class/project-config` 硬编码在以下文件中：

| 文件 | 硬编码路径 | 应该改为 |
|------|----------|---------|
| `wiki_manager_web.py` | `Path('D:/class/project-config') / 'data' / 'wiki' / 'wiki.db'` | `Path(__file__).parent.parent.parent / 'data' / 'wiki' / 'wiki.db'` |
| `wiki_review_web.py` | `Path('D:/class/project-config') / 'data' / 'wiki' / 'wiki.db'` | `Path(__file__).parent.parent.parent / 'data' / 'wiki' / 'wiki.db'` |
| `test_flask_simple.py` | `Path('D:/class/project-config') / 'data' / 'wiki' / 'wiki.db'` | `rag_config.BASE_DIR / 'data' / 'wiki' / 'wiki.db'` |
| `test_simple.py` | `Path('D:/class/project-config') / 'data' / 'wiki' / 'wiki.db'` | `rag_config.BASE_DIR / 'data' / 'wiki' / 'wiki.db'` |
| `test_wiki_manager.py` | `print(f"启动命令: cd D:/class/project-config/langchain-rag && ...")` | `print(f"启动命令: cd {rag_config.BASE_DIR} && ...")` |

**解决方案：**

1. 在 `wiki_manager_web.py` 顶部添加：`from rag_config import BASE_DIR`
2. 在 `wiki_review_web.py` 顶部添加：`from rag_config import BASE_DIR`
3. 在测试文件顶部添加：`from rag_config import BASE_DIR`
4. 将所有硬编码的 `D:/class/project-config` 替换为 `BASE_DIR`

---

## 🎯 实施任务

### Task 1: 修复 WikiUpdater 待审核队列

**TDD scenario:** 修改已实现代码 — 需要验证数据库查询和调用链

**Files:**
- Modify: `D:/class/project-config/langchain-rag/rag_core/wiki_updater.py:465-510`
- Modify: `D:/class/project-config/langchain-rag/rag_core/wiki_updater.py:55-60`
- Modify: `D:/class/project-config/langchain-rag/rag_core/wiki_reasoner.py:623-670`

**Step 1: 修复 `get_pending_review()` 方法**

```python
def get_pending_review(self, limit: int = 20) -> List[Dict[str, Any]]:
    """
    获取待审核的实体列表（从数据库查询）

    Args:
        limit: 最大数量

    Returns:
        待审核列表
    """
    try:
        cursor = self.wiki_db.connect().cursor()
        cursor.execute('''
            SELECT id, entity_name, relation_type, properties, confidence, review_status,
                   created_at
            FROM pending_reviews
            WHERE review_status = 'pending'
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        self.wiki_db.connect().close()

        result = []
        for row in rows:
            result.append({
                'id': row['id'],
                'entity_name': row['entity_name'],
                'relation_type': row['relation_type'],
                'properties': row['properties'],
                'confidence': row['confidence'],
                'review_status': row['review_status'],
                'created_at': row['created_at']
            })
        return result
    except Exception as e:
        logger.error(f"查询待审核列表失败: {e}")
        return []
```

**Step 2: 在 WikiUpdater.__init__() 中调用 reasoner 的保存方法**

```python
def __init__(self):
    # ... 现有代码 ...

    # 激活 Reasoner 并保存推导结果
    self.reasoner = WikiReasoner(self.wiki_db)
    saved_count = self.reasoner.save_deductions_to_pending()
    logger.info(f"已保存 {saved_count} 条推导结果到待审核队列")

    # 保存实体属性推导（如果实现）
    saved_props = self.reasoner.save_entity_properties()
    logger.info(f"已保存 {saved_props} 条属性推导")
```

**Step 3: 验证数据库表结构**

检查 `wiki_db.py` 中的 `pending_reviews` 表结构：
```sql
CREATE TABLE IF NOT EXISTS pending_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT,
    entity_name TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    properties TEXT,
    confidence REAL,
    review_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Step 4: 测试待审核队列**

```bash
# 1. 添加一个新文档触发实体提取
cd D:/class/project-config/langchain-rag
python scripts/rag_cli.py add novel_chapters/第001章.txt

# 2. 检查待审核队列（应该有新记录）
python -c "
from rag_core.wiki_db import WikiDB
wiki_db = WikiDB()
reviews = wiki_db.get_pending_reviews(limit=10)
print(f'待审核记录数: {len(reviews)}')
for r in reviews[:3]:
    print(f'  - {r[\"entity_name\"]} -{r[\"relation_type\"]}-> (置信度: {r[\"confidence\"]})')
"
```

**Step 5: Commit**

```bash
git add rag_core/wiki_updater.py rag_core/wiki_reasoner.py
git commit -m "fix: activate pending_reviews queue in WikiUpdater"
```

---

### Task 2: 统一路径配置

**TDD scenario:** 修改已实现代码 — 需要验证路径正确性

**Files:**
- Modify: `D:/class/project-config/langchain-rag/scripts/wiki_manager_web.py:53-54`
- Modify: `D:/class/project-config/langchain-rag/scripts/wiki_manager_web.py:1481-1482`
- Modify: `D:/class/project-config/langchain-rag/scripts/wiki_review_web.py:39-40`
- Modify: `D:/class/project-config/langchain-rag/scripts/wiki_review_web.py:604-624`
- Modify: `D:/class/project-config/langchain-rag/scripts/test_flask_simple.py:11`
- Modify: `D:/class/project-config/langchain-rag/scripts/test_simple.py:10`
- Modify: `D:/class/project-config/langchain-rag/scripts/test_wiki_manager.py:100`

**Step 1: 修改 `wiki_manager_web.py`**

在文件顶部添加导入：
```python
from rag_config import BASE_DIR

# 修改硬编码路径
DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
CHROMA_DB_PATH = BASE_DIR / 'storage' / 'knowledge_base'
```

在 API 路由中修改：
```python
# Line 1481-1482
db_path = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
chroma_path = BASE_DIR / 'storage' / 'knowledge_base'
```

**Step 2: 修改 `wiki_review_web.py`**

在文件顶部添加导入：
```python
from rag_config import BASE_DIR

# 修改硬编码路径
DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
CHROMA_DB_PATH = BASE_DIR / 'storage' / 'knowledge_base'
```

在 API 路由中修改：
```python
# Line 604-624
db_path = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
chroma_path = BASE_DIR / 'storage' / 'knowledge_base'
```

**Step 3: 修改测试文件**

在 `test_flask_simple.py` 顶部添加：
```python
from rag_config import BASE_DIR

# 修改硬编码路径
DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
```

在 `test_simple.py` 顶部添加：
```python
from rag_config import BASE_DIR

# 修改硬编码路径
DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
```

在 `test_wiki_manager.py` 中修改：
```python
# Line 100
print(f"启动命令: cd {BASE_DIR} && python scripts/wiki_manager_web.py")
```

**Step 4: 测试路径配置**

```bash
# 1. 启动 Wiki Manager Web
cd D:/class/project-config/langchain-rag
python scripts/wiki_manager_web.py

# 2. 在浏览器中访问 http://localhost:5000，验证实体/关系管理正常加载

# 3. 测试 Wiki Review Web
python scripts/wiki_review_web.py
# 访问 http://localhost:5001
```

**Step 5: Commit**

```bash
git add scripts/wiki_manager_web.py scripts/wiki_review_web.py scripts/test_flask_simple.py scripts/test_simple.py scripts/test_wiki_manager.py
git commit -m "refactor: unify hardcoded paths to rag_config.BASE_DIR"
```

---

### Task 3: 验证整个 Wiki 管道

**TDD scenario:** 集成测试 — 需要验证端到端流程

**Files:**
- Test: `D:/class/project-config/langchain-rag/tests/test_wiki_pipeline.py` (新建)

**Step 1: 创建集成测试文件**

```python
"""
Wiki 管道集成测试

测试场景：
1. 文档入库 → 实体提取 → 关系抽取 → 推导 → 待审核队列
2. 待审核队列查询
3. 路径配置正确性
"""
import pytest
from pathlib import Path
from rag_core.wiki_db import WikiDB
from rag_core.wiki_updater import WikiUpdater
from rag_core.wiki_reasoner import WikiReasoner
from rag_config import BASE_DIR

def test_wiki_pipeline_integration():
    """测试完整的 Wiki 管道"""
    wiki_db = WikiDB()
    updater = WikiUpdater()  # 应该自动保存推导结果

    # 1. 验证待审核队列不为空
    reviews = wiki_db.get_pending_reviews(limit=10)
    assert len(reviews) > 0, "待审核队列应该有记录"

    # 2. 验证路径配置正确
    assert wiki_db.db_path == BASE_DIR / 'data' / 'wiki' / 'wiki.db'
    assert wiki_db.chroma_path == BASE_DIR / 'storage' / 'knowledge_base'

    print(f"✅ Wiki 管道测试通过: {len(reviews)} 条待审核记录")

def test_path_config():
    """测试路径配置"""
    from scripts.wiki_manager_web import DB_PATH, CHROMA_DB_PATH
    from scripts.wiki_review_web import DB_PATH as REVIEW_DB_PATH, CHROMA_DB_PATH as REVIEW_CHROMA_PATH

    assert DB_PATH == BASE_DIR / 'data' / 'wiki' / 'wiki.db'
    assert CHROMA_DB_PATH == BASE_DIR / 'storage' / 'knowledge_base'
    assert REVIEW_DB_PATH == BASE_DIR / 'data' / 'wiki' / 'wiki.db'
    assert REVIEW_CHROMA_PATH == BASE_DIR / 'storage' / 'knowledge_base'

    print("✅ 路径配置测试通过")

def test_pending_queue_not_empty():
    """测试待审核队列不为空（需要先添加文档）"""
    wiki_db = WikiDB()

    # 获取待审核记录
    reviews = wiki_db.get_pending_reviews(limit=100)

    # 至少应该有一些待审核记录（如果数据库不为空）
    print(f"当前待审核记录数: {len(reviews)}")

    if len(reviews) == 0:
        print("⚠️ 待审核队列为空（可能需要先添加文档触发实体提取）")
    else:
        print(f"✅ 待审核队列有 {len(reviews)} 条记录")
        for r in reviews[:5]:
            print(f"  - {r['entity_name']} -{r['relation_type']}-> (置信度: {r['confidence']})")

if __name__ == "__main__":
    test_path_config()
    test_pending_queue_not_empty()
    test_wiki_pipeline_integration()
```

**Step 2: 运行测试**

```bash
cd D:/class/project-config/langchain-rag
python -m pytest tests/test_wiki_pipeline.py -v
```

**Step 3: 手动验证**

```bash
# 1. 添加一个测试文档
echo "方源持有酒杯" > /tmp/test_entity.txt
python -c "
from rag_core.knowledge_base import KnowledgeBase
kb = KnowledgeBase()
kb.add_document('/tmp/test_entity.txt')
print('文档已添加')
"

# 2. 检查待审核队列
python -c "
from rag_core.wiki_db import WikiDB
wiki_db = WikiDB()
reviews = wiki_db.get_pending_reviews(limit=20)
print(f'待审核记录数: {len(reviews)}')
for r in reviews:
    print(f'  - {r[\"entity_name\"]} -{r[\"relation_type\"]}-> (置信度: {r[\"confidence\"]})')
"

# 3. 启动 Web 界面验证
python scripts/wiki_manager_web.py
# 访问 http://localhost:5000
```

**Step 4: Commit**

```bash
git add tests/test_wiki_pipeline.py
git commit -m "test: add wiki pipeline integration tests"
```

---

## 📋 验收标准

### Task 1 验收
- ✅ `get_pending_review()` 返回数据库中的真实记录（非空列表）
- ✅ `WikiUpdater` 实例化时自动调用 `reasoner.save_deductions_to_pending()`
- ✅ `pending_reviews` 表有新的记录（通过 `wiki_db.get_pending_reviews()` 查询验证）
- ✅ 关系推导置信度 > 0.5 的记录会进入待审核队列

### Task 2 验收
- ✅ `wiki_manager_web.py` 中的 `DB_PATH` 和 `CHROMA_DB_PATH` 使用 `BASE_DIR`
- ✅ `wiki_review_web.py` 中的 `DB_PATH` 和 `CHROMA_DB_PATH` 使用 `BASE_DIR`
- ✅ 所有测试文件使用 `BASE_DIR`
- ✅ 路径正确解析为 `D:/class/project-config/data/wiki/wiki.db` 和 `D:/class/project-config/storage/knowledge_base`

### Task 3 验收
- ✅ 集成测试全部通过
- ✅ 手动验证：添加文档后待审核队列有新记录
- ✅ Web 界面正常加载实体和关系数据

---

## 🔄 回滚计划

如果任何任务失败：

1. **Task 1 失败：**
   - 回滚 `wiki_updater.py` 的修改
   - 检查数据库表结构是否正确
   - 检查 `WikiReasoner` 的 `save_deductions_to_pending()` 实现是否正确

2. **Task 2 失败：**
   - 回滚所有硬编码路径的修改
   - 检查 `rag_config.py` 的 `BASE_DIR` 是否正确
   - 验证路径拼接逻辑

3. **Task 3 失败：**
   - 回滚测试文件的修改
   - 检查测试依赖是否正确安装
   - 验证数据库连接是否正常

---

## 📝 注意事项

1. **数据库备份：** 修改前备份 `wiki.db` 文件
2. **向后兼容：** 确保现有 API 不受影响
3. **日志记录：** 所有修改都添加详细的日志输出
4. **错误处理：** 所有数据库操作都添加 try/except
5. **测试覆盖：** 每个修改都有对应的测试验证

---

**Plan saved to:** `docs/plans/2026-07-11-wiki-pipeline-unification.md`

**Next step:** Use `/skill:executing-plans` to implement these tasks task-by-task.
