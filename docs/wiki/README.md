# Wiki 层文档

## 概述

Wiki 层为 RAG 系统提供结构化事实存储，解决现有系统**召回混淆**和**知识复利困难**的问题。

## 架构

```
用户提问
  ↓
WikiRouter（路由判断）
  ↓
┌─────────────┬─────────────┐
│  事实类查询  │   语义类查询  │
│     → Wiki  │      → RAG   │
└─────────────┴─────────────┘
```

## 核心模块

### 1. WikiDB (`rag_core/wiki_db.py`)

SQLite 数据库管理器，提供：
- 实体操作（增删查改）
- 关系操作
- 事实查询接口

**快速开始**：
```python
from rag_core.wiki_db import get_wiki_db

wiki_db = get_wiki_db()
wiki_db.init_db()

wiki_db.add_entity("方源", "人物", {"主修": "力道"})
wiki_db.add_relationship("方源", "力道", "主修")

answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
print(answer)  # 方源 主修 的对象: 力道
```

### 2. WikiRouter (`rag_core/wiki_router.py`)

路由器，判断查询类型：
- 事实类查询 → Wiki
- 语义类查询 → RAG

**快速开始**：
```python
from rag_core.wiki_router import WikiRouter

router = WikiRouter(known_entities={"方源", "力道"})
route = router.route("方源主修什么流派？")
print(route)  # "wiki"
```

### 3. 集成到 RagPipeline

RagPipeline 自动路由查询：
```python
from rag_core.knowledge_base import KnowledgeBase

kb = KnowledgeBase()
result = kb.search("方源主修什么流派？")
# 事实类查询自动路由到 Wiki
# 语义类查询路由到 RAG
```

## 数据结构

### 实体表
```sql
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    properties TEXT,           -- JSON
    aliases TEXT,              -- JSON
    source_chapter TEXT
);
```

### 关系表
```sql
CREATE TABLE relationships (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,    -- 持有/属于/主修/背叛/盟友
    properties TEXT,           -- JSON
    source_chapter TEXT
);
```

## 路由规则

| 查询类型 | 关键词 | 示例 |
|---------|--------|------|
| 事实类 | 实体名 + 事实关键词 | "方源主修什么流派？" |
| 语义类 | 语义关键词 | "方源为什么这么残忍？" |
| 默认 | - | "今天天气怎么样？" |

## 使用示例

### 添加数据
```python
from rag_core.wiki_db import get_wiki_db

wiki_db = get_wiki_db()
wiki_db.init_db()

# 添加实体
wiki_db.add_entity(
    name="方源",
    entity_type="人物",
    properties={"主修": "力道", "资质": "甲等9成"},
    aliases=["方正", "黑土"]
)

# 添加关系
wiki_db.add_relationship(
    source_name="方源",
    target_name="力道",
    rel_type="主修",
    source_chapter="第1章"
)
```

### 查询数据
```python
# 查询实体
entity = wiki_db.get_entity("方源")
print(entity['properties'])  # {'主修': '力道', '资质': '甲等9成'}

# 查询关系
relations = wiki_db.get_relations("fang_yuan")
for rel in relations:
    print(f"{rel['source']} -{rel['rel_type']}-> {rel['target']}")

# 事实查询
answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
print(answer)  # 方源 主修 的对象: 力道
```

### CLI 工具（待实现）
```bash
# 查看待审核实体
python rag_cli.py wiki review

# 审核通过
python rag_cli.py wiki approve --id=xxx

# 添加实体
python rag_cli.py wiki add --name="XXX" --type="人物"
```

## 测试

运行简化测试：
```bash
cd langchain-rag
python tests/test_wiki_simple.py
```

## 数据文件

- `data/wiki/seed.json` - 初始实体和关系数据
- `data/wiki/wiki.db` - SQLite 数据库文件

## 下一步

- [ ] 实现增量更新模块
- [ ] 创建 CLI 工具
- [ ] 实现可视化
- [ ] 优化路由准确率

## 相关文档

- [实现总结](./WIKI_IMPLEMENTATION.md)
- [知识库问题](../KNOWLEDGE_BASE_ISSUES.md)
- [故障排除](../../troubleshooting.md)
