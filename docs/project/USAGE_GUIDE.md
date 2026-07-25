# 知识库使用指南

## 🚀 快速开始

### 1. 添加新文档到主知识库

```bash
# 添加单个文档
D:/class/miniconda3/envs/ml_env/python.exe add_documents.py "documents/政策分析/新政策.txt"

# 批量添加整个文件夹
D:/class/miniconda3/envs/ml_env/python.exe add_documents.py "documents/视频教程"
```

### 2. 添加新小说章节

```bash
# 将新章节放入 novel_chapters/ 目录
# 然后运行导入脚本
D:/class/miniconda3/envs/ml_env/python.exe import_novel_chapters.py
```

### 3. 检查知识库状态

```bash
D:/class/miniconda3/envs/ml_env/python.exe check_knowledge_base.py
```

## 📁 目录结构

```
langchain-rag/
├── documents/           # 普通文档存放处
│   ├── 视频教程/
│   ├── 政策分析/
│   ├── 趋势情报/
│   └── _tavily_search/
├── novel_chapters/      # 小说章节存放处
├── storage/             # 知识库存储
│   ├── knowledge_base_clean/  # 主知识库
│   └── novel_kb/          # 小说知识库
├── add_documents.py     # 文档添加脚本
├── import_novel_chapters.py  # 小说导入脚本
└── check_knowledge_base.py   # 状态检查脚本
```

## ⚡ 常用命令

```bash
# 检查知识库状态
python check_knowledge_base.py

# 添加文档
python add_documents.py <文件路径> [分类]

# 批量添加
python add_documents.py <文件夹路径>

# 导入小说章节
python import_novel_chapters.py

# 启动 RAG 服务
python rag_server.py
```

## ❓ 常见问题

**Q: 添加文档后搜索不到？**
A: 确保文档格式正确（.txt, .md, .pdf, .docx），编码为UTF-8

**Q: 如何查看知识库状态？**
A: 运行 `python check_knowledge_base.py`

**Q: 小说章节命名规范？**
A: `chapter_XXXX_章节名.txt` (XXXX为四位数字序号)

---

**最后更新**: 2026-07-01

## ⚙️ 分批加载配置

系统已内置大文件分批加载机制，无需手动干预：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ADD_BATCH_SIZE` | 500 | ChromaDB 每批插入文档数 |
| `EMBEDDING_BATCH_SIZE` | 256 | Embedding 模型每批处理文本数 |

如需调整，修改 `rag_core/vector_store.py` 中的 `ADD_BATCH_SIZE` 和 `rag_core/embedding_service.py` 中的 `DEFAULT_EMBEDDING_BATCH_SIZE`。
