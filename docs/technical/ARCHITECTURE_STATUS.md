# 知识库架构状态报告

**时间**: 2026-07-31  
**状态**: ✅ libsql 统一存储 + LSH 优先检索 + Wiki Manager Web + 知识库检索

---

## 📊 当前架构

### 存储层（libsql 统一存储）

```
┌──────────────────────────────────────────────┐
│              存储架构                         │
├──────────────────────────────────────────────┤
│  libsql (storage/knowledge_base.db)          │
│  ├── chunks 表 — 向量数据（chunk_id, vector, metadata）
│  ├── entities 表 — Wiki 实体                 │
│  ├── relationships 表 — Wiki 关系            │
│  ├── entity_history 表 — 历史版本            │
│  ├── facts 表 — 事实锚点                    │
│  ├── pending_reviews 表 — 待审核            │
│  └── correction_log 表 — 修正日志           │
├──────────────────────────────────────────────┤
│  FAISS LSH 索引 (storage/lsh_index/)         │
│  └── index.faiss + id_map.pkl               │
├──────────────────────────────────────────────┤
│  ChromaDB (storage/knowledge_base/)          │
│  └── 回退存储（LSH 召回不足时使用）           │
└──────────────────────────────────────────────┘
```

### 检索流程

```
用户查询
    ↓
RagPipeline.retrieve()
    ↓
┌─────────────────────────────────────┐
│ 1. LSH 检索 (FAISS, ~0.1ms)         │
│    - 返回 top_k * 2 个内部 ID       │
│    - 通过 id_map 获取 Document 对象  │
├─────────────────────────────────────┤
│ 2. 判断召回是否充足                  │
│    - count >= LSH_RECALL_MIN_COUNT (5)  │
│    - score >= LSH_RECALL_MIN_SCORE (0.6)│
├─────────────────────────────────────┤
│ 3. 如果召回不足 → ChromaDB HNSW 回退│
│    - 合并 LSH + HNSW 结果，去重     │
├─────────────────────────────────────┤
│ 4. 条件因果排序                      │
│    - 如果 doc_type=="novel" > 80%   │
│    - 按 global_order 排序           │
└─────────────────────────────────────┘
    ↓
RagPipeline.generate_answer()
    ↓
LLM 生成回答
```

---

## ✅ 已实现模块

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| **libsql 向量存储** | `vector_store_libsql.py` | ✅ 完成 | libsql 向量存储（主存储） |
| **ChromaDB 向量存储** | `vector_store.py` | ✅ 完成 | ChromaDB 向量存储（回退） |
| **Wiki 数据库 (libsql)** | `wiki_db_libsql.py` | ✅ 完成 | libsql Wiki 数据库 |
| **Wiki 数据库 (兼容)** | `wiki_db.py` | ✅ 完成 | 重导出 libsql 版本 |
| **LSH 索引管理器** | `lsh_index.py` | ✅ 完成 | FAISS LSH，int8 量化，保存/加载 |
| **因果排序器** | `causal_sorter.py` | ✅ 完成 | 按 global_order 排序，上下文窗口 |
| **断点续传加载器** | `resume_loader.py` | ✅ 完成 | per-file 进度，全局计数器 |
| **知识库主类** | `knowledge_base.py` | ✅ 重写 | 集成 libsql + LSH + 断点续传 + 同步双写 |
| **RAG 管道** | `rag_pipeline.py` | ✅ 重写 | LSH 优先 + HNSW 回退 + 因果排序 |
| **混合检索路由** | `hybrid_router.py` | ✅ 完成 | 自动路由普通/父子模式 |
| **父子索引构建** | `parent_index_builder.py` | ✅ 完成 | 后台异步构建父子索引 |
| **CLI 工具** | `rag_cli.py` | ✅ 更新 | novel 子命令 + rebuild 参数 |
| **Wiki CLI** | `wiki_cli.py` | ✅ 完成 | Wiki 管理 CLI |
| **批量关系抽取** | `batch_extract_relations.py` | ✅ 完成 | CLI/Web 批量抽取关系 |
| **Web 知识图谱** | `wiki_manager_web.py` | ✅ 完成 | Canvas 力导向图谱 + 详情面板 |
| **LLM 精炼** | `wiki_manager_web.py` | ✅ 完成 | 实体精筛 + 关系提取 + 精炼状态显示 |
| **配置** | `rag_config.py` | ✅ 更新 | libsql 路径、LSH 路径、召回阈值、架构开关 |
| **迁移脚本** | `migrate_to_libsql.py` | ✅ 完成 | 从 ChromaDB/SQLite 迁移到 libsql |
| **备份脚本** | `backup_before_migration.py` | ✅ 完成 | 迁移前完整备份 |
| **回滚脚本** | `rollback_libsql.py` | ✅ 完成 | 快速回滚到迁移前状态 |
| **验证脚本** | `verify_migration.py` | ✅ 完成 | 迁移后数据完整性验证 |

---

## 📊 当前知识库状态

**已加载文档**:
- 《蛊真人》精校版 — 章节文件已分割，部分章节已加载
- 其他文档 — 通过 auto-import 自动索引

**存储文件**:
- `storage/knowledge_base.db` — libsql 统一数据库（向量 + Wiki）
- `storage/lsh_index/index.faiss` — FAISS LSH 索引
- `storage/lsh_index/id_map.pkl` — ID 映射文件
- `storage/progress_*.json` — per-file 进度文件
- `storage/global_counter.json` — 全局计数器
- `storage/knowledge_base/` — ChromaDB 存储（兼容/回退）

---

## 📋 验收状态

| 验收项 | 状态 |
|--------|------|
| libsql 向量存储实现 | ✅ 通过 |
| libsql Wiki 数据库实现 | ✅ 通过 |
| LSH 索引管理器实现 | ✅ 通过 |
| 因果排序器实现 | ✅ 通过 |
| 断点续传加载器实现 | ✅ 通过 |
| KnowledgeBase 重写 | ✅ 通过 |
| RagPipeline 重写 | ✅ 通过 |
| 混合检索路由 | ✅ 通过 |
| 父子索引构建 | ✅ 通过 |
| CLI 命令更新 | ✅ 通过 |
| Wiki CLI 命令 | ✅ 通过 |
| 配置更新 | ✅ 通过 |
| 迁移脚本 | ✅ 通过 |
| 备份/回滚脚本 | ✅ 通过 |
| 文档更新 | ✅ 通过 |
| 测试验证 | ✅ 通过 |

---

## 🐛 已知问题

### 1. ChromaDB Telemetry 错误
- **错误信息**: `capture() takes 1 positional argument but 3 were given`
- **影响**: 仅产生日志警告，不影响核心功能
- **解决**: 暂时忽略，后续升级 ChromaDB 版本

### 2. Embedding 生成较慢
- **现象**: 首次调用 embedding 服务需要 4000+ ms
- **原因**: sentence-transformers 模型首次加载需要时间
- **解决**: 使用 `rag_cli.py preload` 预下载模型

### 3. 知识图谱节点渲染问题（已修复）
- **错误**: `Cannot read properties of undefined (reading 'x')`
- **原因**: `graphPositions` 数组未正确创建节点
- **解决**: 添加节点位置创建逻辑（基于连接数计算大小和初始位置）

### 4. Web 批量导入关系失败（已修复）
- **错误**: LLM 返回的实体不存在时导入失败
- **原因**: 没有自动创建缺失实体
- **解决**: 在 `batch_import_relations` 中添加实体自动创建逻辑

### 5. 知识图谱详情面板不自动关闭（已修复）
- **现象**: 点击空白区域/切换面板/删除实体后详情面板不关闭
- **原因**: 缺少 `closeDetailPanel` 函数和事件处理
- **解决**: 添加 `closeDetailPanel` 函数，在点击空白区域/切换面板/删除实体后调用

---

**报告生成时间**: 2026-08-02  
**下次更新**: 完成全量关系抽取和精炼优化后
