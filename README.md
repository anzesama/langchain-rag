# RAG 知识库系统

**项目路径**：D:/class/project-config/langchain-rag
**Python 版本**：3.9 (ml_env)
**最后更新**：2026-07-09

---

## 📁 目录结构

```
langchain-rag/
├── scripts/                    # 📜 核心脚本
│   ├── rag_cli.py              # RAG CLI 工具（统一入口）
│   ├── rag_server_v2.py        # RAG HTTP 服务器
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
│   ├── vector_store.py         # 向量存储
│   ├── rag_pipeline.py         # RAG 管道
│   ├── resume_loader.py        # 断点续传加载器
│   ├── lsh_index.py            # LSH 索引
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
│   ├── knowledge_base/         # ChromaDB 数据库
│   ├── novel_lsh.index         # LSH 索引
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
- ✅ **断点续传**（进度文件 + ChromaDB 同步）
- ✅ LSH 索引加速检索
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

### 服务管理
- ✅ RAG 服务自动启动（pi 扩展中集成）
- ✅ 健康检查端点
- ✅ 命令行服务管理

### 文档管理
- ✅ 多格式文档支持
- ✅ 大文件分批加载
- ✅ 内容去重
- ✅ 全局计数器

---

## 📊 系统状态

- **文档数量**：18,738 个块（蛊真人精校版）
- **存储路径**：`storage/knowledge_base`
- **Python 环境**：ml_env (3.9.25)
- **CLI 统一入口**：`scripts/rag_cli.py`
- **服务管理**：自动检测 + 启动
- **检索性能**：首次 4.9s，后续 0.03-0.05s

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

### 待改进
- ⏳ 完善文档注释
- ⏳ 添加单元测试
- ⏳ 优化 LSH 索引加载

---

## 📝 更新日志

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

**项目状态**：✅ 运行正常
**最后维护**：2026-07-05
