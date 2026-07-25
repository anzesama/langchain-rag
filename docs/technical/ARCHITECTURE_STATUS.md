# 知识库架构状态报告

**时间**: 2026-07-03  
**状态**: ✅ 架构升级完成

---

## 📊 当前架构

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
| **LSH 索引管理器** | `lsh_index.py` | ✅ 完成 | FAISS LSH，int8 量化，保存/加载 |
| **因果排序器** | `causal_sorter.py` | ✅ 完成 | 按 global_order 排序，上下文窗口 |
| **断点续传加载器** | `resume_loader.py` | ✅ 完成 | per-file 进度，全局计数器 |
| **知识库主类** | `knowledge_base.py` | ✅ 重写 | 集成 LSH + 断点续传 + 同步双写 |
| **RAG 管道** | `rag_pipeline.py` | ✅ 重写 | LSH 优先 + HNSW 回退 + 因果排序 |
| **CLI 工具** | `rag_cli.py` | ✅ 更新 | novel 子命令 + rebuild 参数 |
| **配置** | `rag_config.py` | ✅ 更新 | LSH 路径、召回阈值、架构开关 |

---

## 📊 当前知识库状态

**已加载文档**:
- 《蛊真人》精校版 — 章节文件已分割，部分章节已加载
- 其他文档 — 通过 auto-import 自动索引

**存储文件**:
- `storage/novel_lsh.index` — FAISS LSH 索引
- `storage/id_map.pkl` — ID 映射文件
- `storage/progress_*.json` — per-file 进度文件
- `storage/global_counter.json` — 全局计数器
- `storage/knowledge_base/` — ChromaDB 存储

---

## 📋 验收状态

| 验收项 | 状态 |
|--------|------|
| LSH 索引管理器实现 | ✅ 通过 |
| 因果排序器实现 | ✅ 通过 |
| 断点续传加载器实现 | ✅ 通过 |
| KnowledgeBase 重写 | ✅ 通过 |
| RagPipeline 重写 | ✅ 通过 |
| CLI 命令更新 | ✅ 通过 |
| 配置更新 | ✅ 通过 |
| 模块导出更新 | ✅ 通过 |
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

---

**报告生成时间**: 2026-07-03  
**下次更新**: 完成《蛊真人》全量加载后
