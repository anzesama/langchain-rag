# RAG 知识库系统

**项目路径**：D:/class/project-config/langchain-rag
**Python 版本**：3.9 (ml_env)
**最后更新**：2026-07-31
**存储架构**：libsql（统一存储层）+ FAISS LSH + ChromaDB（回退）
**Web 界面**：Wiki Manager (5000) + RAG Server (8765)

---

## 📁 目录结构

```
langchain-rag/
├── scripts/                    # 📜 核心脚本
│   ├── rag_cli.py              # RAG CLI 工具（统一入口）
│   ├── rag_server_v2.py        # RAG HTTP 服务器
│   ├── wiki_manager_web.py     # Wiki 知识图谱管理 Web 界面
│   ├── wiki_review_web.py      # Wiki 审核清理 Web 界面
│   ├── wiki_graph_web.py       # 知识图谱静态 HTML 生成器
│   └── rag_extension/          # pi Agent 扩展
│       └── pi_rag_tool.ts      # 知识库搜索工具（自动启动服务）
│
├── configs/                    # ⚙️ 配置文件
│   ├── package.json            # Node.js 配置
│   └── package-lock.json       # Node.js 锁文件
│
├── docs/                       # 📚 文档
│   ├── archive/                # 归档文档
│   ├── cleanup/                # 清理相关文档
│   ├── execution/              # 执行总结
│   ├── fix/                    # 修复文档
│   ├── project/                # 项目文档
│   ├── review/                 # 审查文档
│   ├── technical/              # 技术文档
│   └── plans/                  # 计划文档
│
├── rag_core/                   # 🔧 核心代码
│   ├── knowledge_base.py       # 知识库主类
│   ├── vector_store.py         # ChromaDB 向量存储（回退）
│   ├── vector_store_libsql.py  # libsql 向量存储（主存储）
│   ├── rag_pipeline.py         # RAG 管道
│   ├── resume_loader.py        # 断点续传加载器
│   ├── lsh_index.py            # LSH 索引
│   ├── wiki_db.py              # Wiki 数据库（重导出 libsql 版本）
│   ├── wiki_db_libsql.py       # Wiki 数据库（libsql 实现）
│   ├── parent_document_retriever.py
│   └── ...                     # 其他核心模块
│
├── documents/                  # 📖 文档目录
│   ├── 蛊真人_精校版.txt       # 小说原文
│   ├── novel_chapters/         # 小说章节
│   ├── AAAMLP-CN/              # 机器学习文档
│   └── ...                     # 其他文档
│
├── storage/                    # 💾 存储目录
│   ├── knowledge_base.db       # libsql 统一数据库（向量+Wiki）
│   ├── knowledge_base/         # ChromaDB 数据库（兼容/回退）
│   ├── lsh_index/              # FAISS LSH 索引
│   ├── global_counter.json     # 全局计数器
│   └── ...                     # 其他数据
│
├── tests/                      # 🧪 测试目录
├── logs/                       # 📝 日志目录
├── backups/                    # 🗄️ 备份目录
├── archive/                    # 📦 归档目录
└── rag_extension/              # 🧩 RAG 扩展
```

---

## 🚀 快速开始

### 1. 激活环境
```bash
conda activate ml_env
```

### 2. 启动 RAG 服务
```bash
# 方式 1: 通过 CLI 启动
python scripts/rag_cli.py service start

# 方式 2: 直接运行服务器
python scripts/rag_server_v2.py
```

### 3. 使用 CLI 工具
```bash
python scripts/rag_cli.py --help
```

### 4. 添加文档
```bash
# 添加单个文档
python scripts/rag_cli.py add documents/your-file.txt

# 添加小说（支持断点续传）
python scripts/rag_cli.py add-novel documents/蛊真人_精校版.txt

# 批量添加目录
python scripts/rag_cli.py add-dir
```

### 5. 搜索知识库
```bash
# 智能搜索（生成回答）
python scripts/rag_cli.py search "方源的目标是什么"

# 原始检索（返回文档片段）
python scripts/rag_cli.py search-raw "修仙" --top-k 10
```

### 6. 查看状态
```bash
# 完整状态检查
python scripts/rag_cli.py status

# 快速查看
python scripts/rag_cli.py view
```

---

## 📚 文档索引

### 项目文档
- **[项目说明](docs/project/README.md)** - 项目概述和用法
- **[项目总结](docs/project/PROJECT_SUMMARY.md)** - 项目总结
- **[项目索引](docs/project/PROJECT_INDEX.md)** - 项目索引
- **[使用指南](docs/project/USAGE_GUIDE.md)** - 使用指南
- **[项目经验](docs/project/PROJECT_EXPERIENCES.md)** - 项目经验

### 技术文档
- **[架构状态](docs/technical/ARCHITECTURE_STATUS.md)** - 架构状态
- **[升级总结](docs/technical/UPGRADE_SUMMARY.md)** - 升级总结
- **[升级计划](docs/technical/RAG_UPGRADE_PLAN.md)** - 升级计划
- **[重构计划](docs/technical/REFACTOR_PLAN_RAG.md)** - 重构计划
- **[系统状态](docs/technical/SYSTEM_STATUS_20260701.md)** - 系统状态

### 修复文档
- **[修复报告](docs/fix/FIX_REPORT.md)** - 修复报告
- **[修复总结](docs/fix/FIX_SUMMARY.md)** - 修复总结
- **[问题分析](docs/fix/KNOWLEDGE_BASE_ISSUES.md)** - 问题分析
- **[修复计划](docs/fix/KNOWLEDGE_BASE_FIX_PLAN.md)** - 修复计划

### 清理文档
- **[清理报告](docs/cleanup/CLEANUP_REPORT.md)** - 清理报告
- **[垃圾清理](docs/cleanup/CLEANUP_GARBAGE_REPORT.md)** - 垃圾清理报告

### Wiki 层文档
- **[用户指南](docs/wiki/USER_GUIDE.md)** - Wiki 层使用指南
- **[实现总结](docs/wiki/WIKI_IMPLEMENTATION.md)** - Wiki 层实现总结
- **[快速总结](docs/wiki/QUICK_SUMMARY.md)** - Week 1 总结
- **[Week 2 总结](docs/wiki/WEEK2_SUMMARY.md)** - Week 2 总结
- **[Week 3 总结](docs/wiki/WEEK3_COMPLETE_SUMMARY.md)** - Week 3 总结
- **[完整总结](docs/wiki/COMPLETE_SUMMARY.md)** - Wiki 层完整总结

### 执行文档
- **[执行总结](docs/execution/EXECUTION_SUMMARY_20260702.md)** - 执行总结
- **[阶段总结](docs/execution/PHASE_SUMMARY.md)** - 阶段总结
- **[加载总结](docs/execution/LOAD_SUMMARY_20260702.md)** - 加载总结
- **[实现总结](docs/execution/IMPLEMENTATION_SUMMARY.md)** - 实现总结
- **[脚本重构报告](docs/execution/SCRIPT_REFACTORING_REPORT.md)** - 脚本重构报告

### 审查文档
- **[审查归档](docs/review/REVIEW_ARCHIVE_20260702.md)** - 审查归档
- **[混合路由总结](docs/review/HYBRID_ROUTER_SUMMARY.md)** - 混合路由总结
- **[审查总结 KB 修复](docs/review/REVIEW_SUMMARY_KB_FIX.md)** - 审查总结 KB 修复
- **[审查总结热点系统](docs/review/REVIEW_SUMMARY_HOTSPOT_SYSTEM.md)** - 审查总结热点系统

---

## 🔧 核心功能

### 知识库管理
- ✅ 文档自动加载和向量化
- ✅ **libsql 统一存储**（向量 + Wiki 结构化数据）
- ✅ **断点续传**（进度文件 + libsql 同步）
- ✅ LSH 索引加速检索
- ✅ ChromaDB 回退机制
- ✅ 混合检索路由
- ✅ 父子文档检索

### 检索功能
- ✅ 向量相似度检索
- ✅ LSH 哈希索引检索
- ✅ **P0: CrossEncoder 语义重排**（默认禁用，可通过 `enable_reranker=True` 启用）
- ✅ **P1: 多路召回**（LSH + ChromaDB HNSW + BM25，当前 LSH+HNSW 双路）
- ✅ 因果排序
- ✅ 查询向量缓存（避免重复 embedding）
- ✅ ChromaDB 预热（避免首次搜索冷启动）

### 🧠 脑启发性记忆层（Phase 1，默认关闭）
- ✅ **静态重要性评分**（规则引擎打底：长度信号 + 4 类关键词 + 来源权重）
- ✅ **软遗忘**（艾宾浩斯**真半衰期**，默认 7 天，`RAG_RECALL_HALF_LIFE` 可覆盖）——只降权不删除
- ✅ **检索即强化**（命中后 `access_count` +1、`importance` ×1.05，达阈值标记 `consolidated`）
- ✅ **可观测端点** `GET /api/memories/stats`（总数 / 语义 / 情景 / 已巩固 / 平均重要性 / 高访问 / 已衰减）
- ⚙️ **开关**：`RAG_MEMORY_ENABLED=1` 启用（**关闭时行为与旧版完全一致**，零风险回滚）
- 🔒 **零侵入迁移**：`chunks` 表新增 5 列（`importance` / `access_count` / `last_access` / `memory_type` / `consolidated`，均有默认值）
- 📄 设计/计划：`docs/plans/2026-11-03-brain-inspired-memory-rag-{design,plan}.md`；调研：`documents/research_brain-inspired-rag.md`

### 服务管理
- ✅ RAG 服务自动启动（pi 扩展中集成）
- ✅ 健康检查端点
- ✅ 命令行服务管理

### 文档管理
- ✅ 多格式文档支持
- ✅ 大文件分批加载
- ✅ 内容去重
- ✅ 全局计数器

### Web 界面
- ✅ **Wiki Manager**（端口 5000）：知识图谱可视化 + 图搜索 + LLM 精筛 + 审核清理
- ✅ **RAG Server**（端口 8765）：知识库 API（搜索/上传/文档管理）
- ✅ **Wiki Review**：实体/关系审核面板
- ✅ 模型预设切换（AGNES / GLM-4 / 自定义）
- ✅ 知识库检索（search_knowledge_base，top_k=5）

### 知识图谱
- ✅ Canvas 力导向图谱（基于连接数的节点大小和位置）
- ✅ 节点/边交互（拖拽、点击、悬停）
- ✅ "仅已连接"过滤
- ✅ 知识图谱图搜索（基于 ECharts）
- ✅ 详情面板自动关闭（点击空白区域/切换面板/删除实体）

### 关系抽取
- ✅ **批量关系抽取**（CLI：`--all` / Web：一键精炼）
- ✅ AGNES API 集成（agnes-2.0-flash 模型）
- ✅ Web 界面关系预览和确认
- ✅ 自动创建缺失实体
- ✅ 实体-关系数据结构（source/target/type）
- ✅ 支持多领域（machine-learning, novel, ontology）

### LLM 精炼
- ✅ **精炼状态显示**（已精炼/未精炼/无实体，带图标和统计）
- ✅ 实体精筛（jieba TF-IDF + LLM 预过滤）
- ✅ 关系提取（Few-shot + 严格类型）
- ✅ "一键精炼"（精筛 + 关系提取合并）
- ✅ 关系预览和手动导入
- ✅ 实体/关系审核清理面板

### 数据管理
- ✅ **批量关系抽取脚本**（`scripts/batch_extract_relations.py`）
- ✅ 集成到 `import.py`（Step 2+3+4 自动抽取关系）
- ✅ Web 批量导入关系增强（自动创建实体）
- ✅ 实体/关系去重
- ✅ 关系类型分布统计（适用/使用/依赖/优化/组成/关联/传递）

### 经验管理
- ✅ 即时记录机制（troubleshooting-drafts.md → troubleshooting.md）
- ✅ 知识库 + grep 混合检索策略
- ✅ .gitignore 忽略临时文件

---

## 📊 系统状态

- **文档数量**：29,000+ 个块
- **存储架构**：libsql（主）+ ChromaDB（回退）+ FAISS LSH（加速）
- **libsql 数据库**：`storage/knowledge_base.db`
- **ChromaDB 数据库**：`storage/knowledge_base/`（兼容/回退）
- **Python 环境**：ml_env (3.9.25)
- **CLI 统一入口**：`scripts/rag_cli.py`
- **服务管理**：自动检测 + 启动
- **检索性能**：LSH ~0.1ms，ChromaDB 预热后 0.03-0.05s

## 🚀 P0/P1 混合检索架构

### P0: CrossEncoder 语义重排
- 使用 `bert-base-chinese` 模型进行精细语义匹配
- 默认禁用（CPU 推理较慢），可通过 `enable_reranker=True` 启用
- 适用场景：需要高精度排序的查询

### P1: 多路召回
1. **LSH（Locality Sensitive Hashing）**：快速位相似度检索，0.00s
2. **ChromaDB HNSW**：向量相似度检索，0.7s（预热后）
3. **BM25**：关键词检索（暂禁，需优化）

### 性能优化
- **查询向量缓存**：在 `retrieve()` 中预计算 embedding，避免 LSH/HNSW 重复调用
- **ChromaDB 预热**：首次搜索前自动调用 `search("test", top_k=1)` 预热
- **文档 ID 统一**：所有召回路径使用 `chunk_id` 作为统一标识符
- **因果排序**：对小说类文档按 `global_order` 排序，保证上下文连贯性

---

## 🛠️ 开发工具

### Python 脚本（全部深度集成 rag_core）
| 脚本 | 功能 | 集成度 |
|------|------|--------|
| `add_documents.py` | 添加文档到知识库 | ⭐⭐⭐⭐⭐ |
| `check_knowledge_base.py` | 检查知识库状态 | ⭐⭐⭐⭐⭐ |
| `clean_then_reload.py` | 清理并重新加载知识库 | ⭐⭐⭐⭐ |
| `import.py` | 统一文档导入（chunks+entities+relations） | ⭐⭐⭐⭐⭐ |
| `import_novel_chapters.py` | 导入小说章节 | ⭐⭐⭐⭐⭐ |
| `rag_cli.py` | RAG CLI 工具 | ⭐⭐⭐⭐⭐ |
| `rag_server.py` | RAG 服务器 | ⭐⭐⭐⭐⭐ |
| `rag_server_v2.py` | RAG 服务器 V2 | ⭐⭐⭐⭐⭐ |

### Node.js 配置
- `package.json` - 项目依赖和脚本

---

## ⚠️ 注意事项

1. **环境要求**：必须使用 `ml_env` (Python 3.9)
2. **存储路径**：所有数据存储在 `storage/knowledge_base`
3. **备份位置**：`backups/backup_20260705/`
4. **ChromaDB Telemetry**：已禁用，仅产生警告日志
5. **脚本集成**：所有核心脚本已重构为使用 `KnowledgeBase` 类
6. **编码问题**：Windows 控制台使用 GBK 编码，避免使用 Emoji 字符

---

## 📈 项目进展

### 已完成
- ✅ 统一存储路径
- ✅ 修复断点续传逻辑
- ✅ 统一 LSH 索引实例
- ✅ 修复全局计数器
- ✅ 清理垃圾文件（38 个）
- ✅ 整理目录结构（根目录文件减少 90%）
- ✅ 重构核心脚本（集成度提升至 ⭐⭐⭐⭐⭐）
- ✅ **libsql 迁移**（向量存储 + Wiki 数据库统一为 libsql）

### 待改进
- ⏳ 完善文档注释
- ⏳ 添加单元测试
- ⏳ 优化 LSH 索引加载

---

## 📝 更新日志

### 2026-08-02 - 知识图谱增强 + 批量关系抽取集成 + Web 功能完善
- ✅ 修复知识图谱渲染问题（Canvas 节点未创建）
- ✅ 添加力导布局（基于连接数的节点大小和初始位置）
- ✅ 修复节点访问错误（检查节点存在性）
- ✅ 集成批量关系抽取到 `import.py`（Step 2+3+4 自动抽取关系）
- ✅ 修改 `batch_extract_relations.py` 支持 chunks 参数
- ✅ Web 批量导入关系增强（自动创建缺失实体）
- ✅ LLM 精炼状态显示（已精炼/未精炼/无实体，带图标和统计）
- ✅ 知识图谱详情面板自动关闭（点击空白区域/切换面板/删除实体）
- ✅ 创建文档：`RELATION_EXTRACTION_INTEGRATION.md`、`WEB_RELATION_IMPORT_ENHANCEMENT.md`、`LLM_REFINE_STATUS_DISPLAY.md`、`GRAPH_DETAIL_PANEL_AUTO_CLOSE.md`

### 2026-07-31 - 知识图谱修复 + 即时记录机制 + 知识库检索优化
- ✅ 修复知识图谱 JS 错误（connectedChk、showConnected 重复声明、reloadGraphData 未定义）
- ✅ 在 AGENTS.md 中增加"即时记录机制"（troubleshooting-drafts.md → troubleshooting.md）
- ✅ 经验检索策略优化：优先用 search_knowledge_base（top_k=5）→ 失败再 grep
- ✅ 新增 troubleshooting.md 问题 39（JavaScript 重复声明 SyntaxError）
- ✅ .gitignore 忽略临时文件

### 2026-07-26 - libsql 迁移完成
- ✅ 创建 `vector_store_libsql.py` — libsql 向量存储管理器
- ✅ 创建 `wiki_db_libsql.py` — libsql Wiki 数据库
- ✅ 迁移 `wiki_db.py` 重导出 libsql 版本（兼容现有代码）
- ✅ 更新 `knowledge_base.py` 使用 libsql 向量存储
- ✅ 创建迁移脚本：`backup_before_migration.py`、`migrate_to_libsql.py`、`rollback_libsql.py`、`verify_migration.py`
- ✅ 创建文档：`LIBSQL_MIGRATION_GUIDE.md`、`LIBSQL_ROLLBACK_PLAN.md`
- ✅ 更新计划文档：`20260725-libsql-migration-plan.md`

### 2026-07-05 - 脚本重构与目录整理
- ✅ 统一存储路径
- ✅ 修复断点续传逻辑
- ✅ 统一 LSH 索引实例
- ✅ 修复全局计数器
- ✅ 清理垃圾文件（38 个）
- ✅ 整理目录结构（根目录文件减少 90%）
- ✅ 重构 add_documents.py - 使用 KnowledgeBase 替代直接 ChromaDB 操作
- ✅ 重构 check_knowledge_base.py - 使用 KnowledgeBase 替代直接 ChromaDB 操作
- ✅ 重构 import_novel_chapters.py - 使用 KnowledgeBase 替代直接 ChromaDB 操作
- ✅ 所有核心脚本集成度提升至 ⭐⭐⭐⭐⭐

### 2026-07-02
- ✅ 混合检索路由实现
- ✅ 执行总结
- ✅ 加载总结

### 2026-07-01
- ✅ 架构状态
- ✅ 系统状态

---

**项目状态**：✅ 运行正常（libsql 统一存储 + Wiki Manager Web + 知识库检索 + 批量关系抽取 + 知识图谱可视化）
**最后维护**：2026-08-02
