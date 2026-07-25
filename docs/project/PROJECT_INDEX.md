# RAG 知识库项目

- 项目位置：D:/class/project-config/langchain-rag
- 归档时间：2026-07-03
- 状态：✅ 架构升级完成

## 📖 全局文档

- [文档管理配置](../../DOCUMENT_POLICY.md) - 全局文档规范
- [项目开发规范](../../AGENTS.md)
- [项目规则](../../PROJECT_RULES.md)
- [故障排除](../../troubleshooting.md)

## 📁 目录结构

```
langchain-rag/
├── README.md              # 项目说明（已更新，含新架构）
├── rag_core/              # 核心模块
│   ├── knowledge_base.py  # 知识库主类（重写，集成 LSH + 断点续传）
│   ├── rag_pipeline.py    # RAG 管道（重写，LSH 优先 + 因果排序）
│   ├── lsh_index.py       # LSH 索引管理器 (NEW!)
│   ├── causal_sorter.py   # 因果排序器 (NEW!)
│   ├── resume_loader.py   # 断点续传加载器 (NEW!)
│   ├── auto_importer.py   # 自动导入
│   ├── document_loader.py # 文档加载
│   ├── document_processor.py # 增强分块器
│   ├── embedding_service.py # Embedding服务
│   ├── vector_store.py    # ChromaDB存储
│   ├── hybrid_router.py   # 混合检索路由
│   ├── parent_index_builder.py  # 后台异步构建父子索引
│   └── parent_document_retriever.py
├── rag_extension/         # pi Agent集成
│   └── rag_tool.py        # Tool注册
├── kb_manager/            # 知识库管理器
├── tools/                 # 工具模块
│   ├── tavily_search.py
│   └── bayesian_analyzer.py
├── docs/                  # 项目文档
├── documents/             # 文档存放（自动索引）
│   ├── novel_chapters/    # 小说章节文件 (NEW!)
│   └── 《蛊真人》精校版_utf8.txt
├── novel_chapters/        # 小说章节源文件
├── storage/               # 数据存储
│   ├── novel_lsh.index    # FAISS LSH 索引 (NEW!)
│   ├── id_map.pkl         # ID 映射 (NEW!)
│   ├── progress_*.json    # per-file 进度 (NEW!)
│   └── knowledge_base/    # ChromaDB 存储
├── rag_server.py          # HTTP API服务
├── rag_cli.py             # 命令行工具（已更新）
├── rag_config.py          # 统一配置（已更新）
├── split_novel_final.py   # 小说章节分割脚本 (NEW!)
├── ARCHITECTURE_STATUS.md # 架构状态报告
├── UPGRADE_SUMMARY.md     # 升级总结
└── requirements.txt       # 依赖列表
```

## 📖 文档导航

### 核心文档
- **README.md** - RAG系统使用说明（已更新）
- **ARCHITECTURE_STATUS.md** - 架构状态报告（已更新）
- **UPGRADE_SUMMARY.md** - 升级总结（已更新）
- **PROJECT_SUMMARY.md** - 项目总结

## 🚀 核心功能

1. **文档管理** - 自动索引、增量更新
2. **分批加载** - 大文件自动分批（Embedding 256/批，ChromaDB 500/批）
3. **向量检索** - LSH 优先 (~0.1ms) + ChromaDB HNSW 回退
4. **因果排序** - 按 global_order 对小说类文档排序
5. **断点续传** - 大文件加载支持中断恢复
5. **生成回答** - RAG检索增强生成
6. **混合检索路由** - 自动根据文档属性和查询意图选择检索模式
7. **后台异步构建父子索引** - 文件入库后自动在后台构建父子索引
8. **API服务** - HTTP API + pi Agent集成
9. **小说管理** - 章节分割、批量加载、进度跟踪

## 📊 项目统计

| 类别 | 数量 |
|------|------|
| 核心模块 | 16个（+3 新模块） |
| 工具模块 | 3个 |
| Streamlit应用 | 4个 |
| 项目文档 | 20+个 |
| 文档脚本 | 10+个 |
| 知识库源文件 | 50+个 |
| 知识库 chunks | 29,000+ |
| **总计** | **50+ 文件 + 29,000+ chunks** |

## 🔧 快速链接

- [RAG系统说明](README.md)
- [架构状态](ARCHITECTURE_STATUS.md)
- [升级总结](UPGRADE_SUMMARY.md)
- [归档指南](docs/archive/ARCHIVE_GUIDE.md)

---

*最后更新：2026-07-03（LSH 优先检索 + 因果排序 + 断点续传架构升级完成）*
