# Wiki 层实现总结

## 实施日期
2026-07-08

## 实施内容

### 1. Wiki 数据库模块 (`rag_core/wiki_db.py`)

**功能**：
- SQLite 数据库存储实体和关系
- 实体操作：添加、查询、更新、删除
- 关系操作：添加、查询
- 事实查询接口：解析查询并返回答案

**核心类**：
```python
WikiDB:
  - init_db()                 # 初始化数据库
  - add_entity()              # 添加实体
  - get_entity()              # 查询实体
  - add_relationship()        # 添加关系
  - get_relations()           # 查询关系
  - get_fact_query_answer()   # 处理事实类查询
```

### 2. Wiki 路由模块 (`rag_core/wiki_router.py`)

**功能**：
- 判断查询类型（事实类 vs 语义类）
- 路由到 Wiki 或 RAG

**路由规则**：
- 事实类：包含实体名 + 事实关键词（主修/属于/持有）+ 无语义关键词 → Wiki
- 语义类：包含语义关键词（为什么/怎么/如何）+ 语义关键词 → RAG
- 默认：RAG

**核心类**：
```python
WikiRouter:
  - route(query)              # 路由判断
  - load_known_entities()     # 加载已知实体
```

### 3. 集成到 RagPipeline (`rag_core/rag_pipeline.py`)

**修改内容**：
- 导入 Wiki 模块
- 在 `ask()` 方法中添加路由逻辑
- 事实类查询 → Wiki 数据库
- Wiki 无结果 → 回退到 RAG

**流程**：
```
用户提问
  → Wiki 路由判断
    → 事实类查询 → Wiki 数据库
      → 返回答案
    → Wiki 无结果 → RAG 流程
      → 检索 + 生成
```

### 4. 初始数据 (`data/wiki/seed.json`)

**内容**：
- 12 个实体（方源、春秋蝉、力道、狐仙福地等）
- 10 个关系（持有、主修、师承等）

### 5. 测试脚本 (`tests/test_wiki_simple.py`)

**测试内容**：
- Wiki 数据库基本功能
- Wiki 路由判断
- Seed 数据加载

## 测试结果

### 测试 1：Wiki 数据库
```
✓ Wiki 数据库初始化成功
✓ 添加实体成功
✓ 添加关系成功
```

### 测试 2：事实查询
```
查询: 方源主修什么流派？
路由结果: wiki
查询结果: 方源 主修 的对象: 力道
```

### 测试 3：路由判断
```
事实类查询（方源主修什么流派？） → wiki
语义类查询（方源为什么这么残忍？） → rag
默认查询（今天天气怎么样？） → rag
```

## 使用示例

### 1. 直接使用 Wiki 数据库
```python
from rag_core.wiki_db import get_wiki_db

wiki_db = get_wiki_db()
wiki_db.init_db()

wiki_db.add_entity("方源", "人物", {"主修": "力道"})
wiki_db.add_relationship("方源", "力道", "主修")

answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
print(answer)  # 方源 主修 的对象: 力道
```

### 2. 使用 KnowledgeBase（自动路由）
```python
from rag_core.knowledge_base import KnowledgeBase

kb = KnowledgeBase()
result = kb.search("方源主修什么流派？")

# 事实类查询会自动路由到 Wiki
# 语义类查询会路由到 RAG
print(result["answer"])
```

## 文件清单

### 新增文件
- `rag_core/wiki_db.py` - Wiki 数据库模块
- `rag_core/wiki_router.py` - Wiki 路由模块
- `data/wiki/seed.json` - 初始数据
- `tests/test_wiki_simple.py` - 简化测试脚本
- `docs/wiki/WIKI_IMPLEMENTATION.md` - 本文档

### 修改文件
- `rag_core/rag_pipeline.py` - 集成 Wiki 路由

## 下一步计划

### Week 2: 增量更新与 CLI 工具
1. 实现增量更新模块 (`wiki_updater.py`)
2. 创建 CLI 工具 (`scripts/wiki_cli.py`)
3. 实现同步检查脚本 (`scripts/sync_wiki_chroma.py`)

### Week 3: 数据加载与测试
1. 实现 `seed.json` 加载功能
2. 编写完整测试用例
3. 优化路由准确率

### Week 4: 可视化与文档
1. 实现知识图谱可视化
2. 编写用户文档
3. 性能优化

## 性能指标

| 指标 | 目标 | 当前状态 |
|------|------|----------|
| Wiki 查询延迟 | < 5ms | 待测试 |
| 路由准确率 | > 95% | 待测试 |
| 数据库查询延迟 | < 2ms | 待测试 |

## 已知问题

1. **日志乱码**：Windows GBK 编码导致日志中文显示异常
   - 解决方案：在 Windows 上使用 UTF-8 日志编码

2. **Seed 数据加载**：未实现从 `seed.json` 加载数据
   - 解决方案：Week 3 实现

3. **路由准确率**：需要更多测试用例验证
   - 解决方案：Week 3 编写测试用例

## 总结

Wiki 层已成功实现基础功能：
- ✅ SQLite 数据库存储实体和关系
- ✅ 事实查询接口
- ✅ Wiki 路由判断
- ✅ 集成到 RagPipeline
- ✅ 基础测试通过

**下一步**：实现增量更新和 CLI 工具。
