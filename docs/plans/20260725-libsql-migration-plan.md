# libsql 迁移实现计划

- 日期：2026-07-25
- 状态：📋 计划中
- 目标：使用 libsql 替代 ChromaDB 和 SQLite，统一存储层

---

## 📋 目录

1. [概述](#概述)
2. [目标](#目标)
3. [技术方案](#技术方案)
4. [实施阶段](#实施阶段)
5. [回退预案](#回退预案)
6. [验证方法](#验证方法)
7. [风险与缓解](#风险与缓解)

---

## 概述

### 背景

当前 RAG 系统使用混合存储方案：
- **ChromaDB**：向量存储（存储文档块 + 向量 + 元数据）
- **SQLite**：Wiki 数据库（存储实体、关系、历史版本、事实）
- **FAISS LSH 索引**：加速检索（独立存储）

### 问题

- 存储层不统一，数据冗余
- ChromaDB 和 SQLite 功能重叠
- 维护成本高

### 解决方案

使用 libsql（本地文件存储）统一存储：
- 向量数据：chunks 表（chunk_id, vector, metadata）
- 结构化数据：entities/relationships/facts 表
- FAISS LSH 索引：继续独立存储（用于加速检索）

---

## 目标

### 功能目标

- [ ] 向量检索功能正常
- [ ] 结构化查询功能正常
- [ ] LSH 检索功能正常
- [ ] 断点续传功能正常
- [ ] 所有 CLI 命令正常

### 性能目标

- [ ] 首次检索时间 < 5s
- [ ] 后续检索时间 < 0.1s
- [ ] 数据库文件大小合理（< 10GB）

### 质量目标

- [ ] 代码覆盖率 > 80%
- [ ] 所有测试通过
- [ ] 完整的文档

---

## 技术方案

### 架构设计

```
┌─────────────────────────────────────────────────────┐
│                  RAG 系统                          │
├─────────────────────────────────────────────────────┤
│  文档加载 → 向量化 → libsql（向量表）               │
│            ↓                                        │
│        FAISS LSH 索引（加速检索）                   │
│            ↓                                        │
│  检索请求 → LSH 快速召回 → libsql 向量检索 → LLM   │
└─────────────────────────────────────────────────────┘
```

### 存储结构

#### libsql 数据库结构

**chunks 表**（向量存储）
```sql
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    vector BLOB NOT NULL,        -- 向量数据（存为 BLOB）
    metadata TEXT NOT NULL,      -- 元数据（JSON）
    embedding TEXT NOT NULL,     -- Embedding 模型名称
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**entities 表**（实体）
```sql
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    properties TEXT,             -- JSON
    aliases TEXT,                -- JSON
    source_chapter TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**relationships 表**（关系）
```sql
CREATE TABLE relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    properties TEXT,             -- JSON
    source_chapter TEXT,
    FOREIGN KEY(source_id) REFERENCES entities(id),
    FOREIGN KEY(target_id) REFERENCES entities(id)
);
```

**entity_history 表**（历史版本）
```sql
CREATE TABLE entity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    old_properties TEXT,
    new_properties TEXT,
    change_reason TEXT,
    changed_by TEXT,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP,
    is_correction BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**facts 表**（事实锚点）
```sql
CREATE TABLE facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    verified_by TEXT,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
);
```

**pending_reviews 表**（待审核）
```sql
CREATE TABLE pending_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT,
    entity_name TEXT NOT NULL,
    entity_type TEXT,
    properties TEXT,
    relation_type TEXT,
    source_id TEXT,
    target_id TEXT,
    confidence REAL DEFAULT 0.5,
    source_text TEXT,
    source_chapter TEXT,
    review_status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**correction_log 表**（修正日志）
```sql
CREATE TABLE correction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
);
```

### FAISS LSH 索引

保持独立存储：
- `storage/lsh_index/index.faiss` - LSH 索引文件
- `storage/lsh_index/id_map.pkl` - ID 映射文件
- `storage/lsh_index/load_state.json` - 加载进度文件

---

## 实施阶段

### 阶段 1：备份与回退预案

**任务**：
- [ ] 创建备份脚本 `scripts/backup_before_migration.py`
- [ ] 创建回滚脚本 `scripts/rollback_libsql.py`
- [ ] 创建验证脚本 `scripts/verify_migration.py`
- [ ] 创建迁移文档 `docs/technical/LIBSQL_MIGRATION_GUIDE.md`
- [ ] 创建回退预案文档 `docs/technical/LIBSQL_ROLLBACK_PLAN.md`

**文件**：
- `scripts/backup_before_migration.py`
- `scripts/rollback_libsql.py`
- `scripts/verify_migration.py`
- `docs/technical/LIBSQL_MIGRATION_GUIDE.md`
- `docs/technical/LIBSQL_ROLLBACK_PLAN.md`

**提交**：
```
chore: 添加 libsql 迁移回退预案

- 创建备份脚本
- 创建回滚脚本
- 创建验证脚本
- 添加迁移文档
- 添加回退预案文档
```

---

### 阶段 2：重构 VectorStoreManager

**任务**：
- [ ] 创建 `VectorStoreManagerLibsql` 类
- [ ] 实现向量表创建和初始化
- [ ] 实现批量插入向量（使用参数化查询）
- [ ] 实现向量相似度检索（使用元数据过滤）
- [ ] 添加向量查询缓存
- [ ] 编写单元测试
- [ ] 集成到 `KnowledgeBase` 类

**文件**：
- `rag_core/vector_store_libsql.py`（新文件）
- `rag_core/vector_store.py`（修改）

**提交**：
```
feat: 重构 VectorStoreManager 使用 libsql

- 创建 VectorStoreManagerLibsql 类
- 实现向量表创建和初始化
- 实现批量插入向量
- 实现向量相似度检索
- 添加向量查询缓存
- 添加单元测试
- 集成到 KnowledgeBase 类
```

---

### 阶段 3：重构 WikiDB

**任务**：
- [ ] 创建 `WikiDBLibsql` 类
- [ ] 实现实体表创建和初始化
- [ ] 实现关系表创建和初始化
- [ ] 实现历史版本表创建和初始化
- [ ] 实现事实表创建和初始化
- [ ] 实现待审核表创建和初始化
- [ ] 实现修正日志表创建和初始化
- [ ] 迁移所有 WikiDB 方法到 libsql 版本
- [ ] 编写单元测试
- [ ] 集成到 `KnowledgeBase` 类

**文件**：
- `rag_core/wiki_db_libsql.py`（新文件）
- `rag_core/wiki_db.py`（修改）

**提交**：
```
feat: 重构 WikiDB 使用 libsql

- 创建 WikiDBLibsql 类
- 实现所有表创建和初始化
- 迁移所有 WikiDB 方法
- 添加单元测试
- 集成到 KnowledgeBase 类
```

---

### 阶段 4：迁移脚本

**任务**：
- [ ] 创建迁移脚本 `scripts/migrate_to_libsql.py`
- [ ] 实现从 ChromaDB 迁移向量数据
- [ ] 实现从 SQLite 迁移 Wiki 数据
- [ ] 实现从 LSH 索引迁移（保持不变）
- [ ] 添加数据验证和对比
- [ ] 执行迁移
- [ ] 运行验证脚本

**文件**：
- `scripts/migrate_to_libsql.py`（新文件）
- `scripts/verify_migration.py`（修改）

**提交**：
```
feat: 创建 libsql 迁移脚本

- 实现从 ChromaDB 迁移向量数据
- 实现从 SQLite 迁移 Wiki 数据
- 添加数据验证和对比
- 执行迁移
- 运行验证脚本
```

---

### 阶段 5：测试与验证

**任务**：
- [ ] 运行所有单元测试
- [ ] 运行集成测试
- [ ] 运行 CLI 工具测试
- [ ] 运行验证脚本
- [ ] 性能测试
- [ ] 数据完整性验证

**提交**：
```
test: 验证 libsql 迁移结果

- 运行所有单元测试
- 运行集成测试
- 运行 CLI 工具测试
- 运行验证脚本
- 性能测试
- 数据完整性验证
```

---

### 阶段 6：文档更新

**任务**：
- [ ] 更新 `README.md`
- [ ] 更新 `docs/project/README.md`
- [ ] 更新 `docs/technical/ARCHITECTURE_STATUS.md`
- [ ] 更新 `docs/technical/LIBSQL_MIGRATION_GUIDE.md`
- [ ] 更新 `docs/technical/LIBSQL_ROLLBACK_PLAN.md`
- [ ] 更新 `docs/technical/RAG_UPGRADE_PLAN.md`

**提交**：
```
docs: 更新 libsql 迁移文档

- 更新 README.md
- 更新项目文档
- 更新架构文档
- 更新迁移指南
- 更新回退预案
```

---

## 回退预案

### 备份策略

**迁移前备份**：
```bash
# 备份 ChromaDB 数据
cp -r storage/knowledge_base storage/knowledge_base.backup.$(date +%Y%m%d_%H%M%S)

# 备份 SQLite 数据
cp storage/data/wiki/wiki.db storage/data/wiki/wiki.db.backup.$(date +%Y%m%d_%H%M%S)

# 备份 LSH 索引
cp storage/lsh_index/index.faiss storage/lsh_index/index.faiss.backup.$(date +%Y%m%d_%H%M%S)
cp storage/lsh_index/id_map.pkl storage/lsh_index/id_map.pkl.backup.$(date +%Y%m%d_%H%M%S)
cp storage/global_counter.json storage/global_counter.json.backup.$(date +%Y%m%d_%H%M%S)
```

### 回滚步骤

**快速回滚命令**：
```bash
# 停止 RAG 服务
python scripts/rag_cli.py service stop

# 运行回滚脚本
python scripts/rollback_libsql.py

# 重启服务
python scripts/rag_cli.py service start

# 验证服务
python scripts/rag_cli.py status
```

### 验证方法

**迁移后验证脚本**：
```python
def verify_migration():
    """验证迁移后的数据完整性"""
    # 1. 检查 libsql 文件是否存在
    libsql_file = Path("storage/knowledge_base.db")
    if not libsql_file.exists():
        print("❌ libsql 文件不存在")
        return False

    # 2. 检查数据库连接
    conn = sqlite3.connect(str(libsql_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chunks")
    chunk_count = cursor.fetchone()[0]
    print(f"✅ 向量数据: {chunk_count} 个块")

    cursor.execute("SELECT COUNT(*) FROM entities")
    entity_count = cursor.fetchone()[0]
    print(f"✅ 实体数据: {entity_count} 个实体")

    cursor.execute("SELECT COUNT(*) FROM relationships")
    relation_count = cursor.fetchone()[0]
    print(f"✅ 关系数据: {relation_count} 条")

    conn.close()

    # 3. 对比备份数据
    # ...（对比 ChromaDB、SQLite、LSH 索引的数据量）

    print("\n✅ 所有验证通过！")
    return True
```

---

## 风险与缓解

### 风险 1：数据迁移失败

**概率**：中等
**影响**：高
**缓解措施**：
- 迁移前完整备份
- 迁移后验证数据完整性
- 提供快速回滚脚本

### 风险 2：性能下降

**概率**：低
**影响**：中
**缓解措施**：
- 性能基准测试
- 优化查询语句
- 添加索引

### 风险 3：代码兼容性问题

**概率**：低
**影响**：高
**缓解措施**：
- 充分的单元测试
- 集成测试
- 代码审查

### 风险 4：回滚时间过长

**概率**：低
**影响**：中
**缓解措施**：
- 简化回滚脚本
- 缩短回滚时间窗口（24 小时内）

---

## 成功标准

### 功能验证

- [ ] 所有现有功能正常工作
- [ ] 数据完整性验证通过
- [ ] 所有测试通过

### 性能验证

- [ ] 首次检索时间 < 5s
- [ ] 后续检索时间 < 0.1s
- [ ] 数据库文件大小合理

### 文档验证

- [ ] 所有文档更新完成
- [ ] 迁移指南清晰
- [ ] 回退预案详细

---

## 时间估算

| 阶段 | 预计时间 | 依赖 |
|------|---------|------|
| 阶段 1：备份与回退预案 | 2 小时 | 无 |
| 阶段 2：重构 VectorStoreManager | 4 小时 | 阶段 1 |
| 阶段 3：重构 WikiDB | 6 小时 | 阶段 2 |
| 阶段 4：迁移脚本 | 3 小时 | 阶段 2、3 |
| 阶段 5：测试与验证 | 4 小时 | 阶段 4 |
| 阶段 6：文档更新 | 2 小时 | 阶段 5 |

**总计**：约 21 小时（3 个工作日）

---

## 下一步行动

1. ✅ 创建实现计划文档（当前）
2. ⏭️ 创建 Git 分支
3. ⏭️ 开始阶段 1：备份与回退预案
4. ⏭️ 执行迁移
5. ⏭️ 验证结果
6. ⏭️ 合并到主分支

---

**计划创建时间**：2026-07-25
**计划状态**：📋 待执行
