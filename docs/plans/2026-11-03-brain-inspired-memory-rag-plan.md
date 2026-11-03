# 脑启发性记忆 RAG + 向量检索优化 —— 实施计划（草案）

> 创建时间：2026-11-03
> 状态：**✅ 决策已确认（Q1=C / Q2=A / Q3=甲），待执行**
> 关联设计：`docs/plans/2026-11-03-brain-inspired-memory-rag-design.md`
> 关联调研：`documents/research_brain-inspired-rag.md`、`documents/research_vector-search.md`

---

## 0. 背景与目标

用户对 RAG 系统提出两条主线诉求：

1. **知识飞轮**：不断补充、**压缩**知识
2. **记忆保留**：突破上下文限制，清晰记住**重要时刻**而非模糊压缩

核心机制选定：**仿照人脑 + 艾宾浩斯遗忘曲线**（软遗忘、重要性加权）。

同时，本轮调研中**发现两个必须先处理的既有问题**（P0），否则新功能会建立在不可靠的地基上。

---

## 1. P0-1：知识库数据事故（🔴 已恢复，机制待修）

### 事故现象
- 服务 `/health` 报告 `total_documents = 12572 ~ 12586`
- 但 `storage/knowledge_base.db` 实际只剩 **690 chunks / 3.1MB**
- 真实生产 KB = **13198 chunks / 118MB**

### 根因（两层）
1. **测试无数据库隔离**：`tests/` 下无 `conftest.py`，`test_vector_store_libsql.py::test_delete_collection` 等直接对**生产 DB** 操作（`delete_collection()` 会 drop 表）
2. **`git stash` 把工作区大 DB（118MB）换成了 HEAD 里的旧小 DB（688 chunks）**，且 `git stash pop` 未成功 → 表现为"数据丢失"

### 已执行恢复
- ✅ 从 `stash@{0}` 提取 `storage/knowledge_base.db` → 恢复 **13198 chunks / 118MB**
- ⚠️ `stash@{0}` **暂不删除**（内含未提交代码，见下）

### 遗留待办
| # | 事项 | 优先级 |
|---|------|--------|
| P0-1a | 新增 `tests/conftest.py`：所有向量库测试使用 **临时目录 DB**（`tmp_path`），禁止触碰 `storage/` | 高 |
| P0-1b | `storage/*.db`、`*.index`、`id_map.pkl` **移出 git 跟踪**（>100MB 二进制入库不当）→ `.gitignore` | 中 |
| P0-1c | 处理 `stash@{0}` 中未提交代码：`get_chunks_by_source()`、`doc.id = chunk_id`（见 §1.1） | 中 |

### 1.1 stash 中的未提交代码（待用户裁决）

```diff
# rag_core/vector_store_libsql.py (+45 行)
+ doc.id = chunk_data['chunk_id']          # 搜索结果带 chunk_id（引用溯源需要）

+ def get_chunks_by_source(self, source_filename, limit=None):
+     """按来源获取 chunk（修复日志中的 AttributeError）"""
```

- 日志证据：`ERROR rag: Entity/Relation extraction error: 'VectorStoreManager' object has no attribute 'get_chunks_by_source'`
- ⚠️ stash 同时含**过时**改动（`rag_config.py` 把 API base 改成 `.cn`，与当前 `.com` 结论冲突）→ **不可整体 pop**

---

## 2. P0-2：向量检索性能（实测瓶颈）

| 指标 | 当前值 |
|------|--------|
| 数据量 | 13198 chunks × 512 dim |
| `/api/search_raw` 端到端 | **avg 11.2s / max 50.9s** |
| 纯向量化 `matrix @ q` | **0.072s** |
| 差距 | **~150×** |

### 根因
`rag_core/vector_store_libsql.py:86` `_cosine_similarity_query()`：
1. 🔴 循环内重复 `np.linalg.norm(query_embedding)`（13198 次）
2. 🔴 逐行 `np.dot`（Python 层调用）
3. 🔴 对全部 13198 行做 `json.loads`

### 附带发现
`HybridRetriever`（LSH+BM25+RRF+reranker）**已实现但服务端未接入**。

详见 `documents/research_vector-search.md`。

---

## 3. Phase 1：记忆系统最小可行实现（核心）

> 遵循设计文档的三层记忆模型 + LUFY 六维评分。**YAGNI：先做叠加载荷最小的版本。**

### 3.1 数据模型扩展（零侵入）

在 `chunks` 表新增列（均带默认值，可回滚）：

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| `importance` | REAL | 0.5 | 静态重要性（导入时计算） |
| `access_count` | INTEGER | 0 | 被检索命中次数 |
| `last_access` | TIMESTAMP | NULL | 最近一次命中时间 |
| `memory_type` | TEXT | `'semantic'` | `semantic` / `episodic` |
| `consolidated` | INTEGER | 0 | 是否已压缩巩固 |

> 迁移策略：`ALTER TABLE ... ADD COLUMN`（SQLite 支持，无需重建）

### 3.2 核心纯函数（全部可单测）

```python
# rag_core/memory_scoring.py（新文件，平铺，不过度模块化）

def compute_importance(text: str, metadata: dict) -> float:
    """静态重要性评分（LUFY 六维，规则版先行）
    维度：情感强度 / 新颖性 / 有用性 / 频率 / 时效性 / 关联度
    返回 0.0 ~ 1.0
    """

def forgetting_decay(last_access, now, half_life_days=7.0) -> float:
    """艾宾浩斯软遗忘：exp(-Δt / half_life)  → 0~1
    Q2=A：默认半衰期 7 天（可用 RAG_RECALL_HALF_LIFE 覆盖）
    """

def compute_final_score(similarity, importance, decay, access_count) -> float:
    """综合评分：similarity × f(importance, decay, access_count)"""

def update_after_retrieval(access_count, importance) -> tuple[int, float]:
    """检索命中后强化：count+1，importance × 1.05（封顶 1.0）"""
```

### 3.3 接入检索

在 `_cosine_similarity_query` 排序时用 `compute_final_score` 替换裸 `similarity`（**可配置开关**，默认关闭，`RAG_MEMORY_ENABLED=1` 启用 → 零风险回滚）。

### 3.4 可观测性

新增只读端点 `GET /api/memories/stats`：
```json
{"total": 13198, "episodic": 12, "avg_importance": 0.53,
 "top_accessed": [...], "decayed_below_threshold": 4021}
```

### 3.5 任务清单

| # | 任务 | 产出 | 测试 |
|---|------|------|------|
| 1 | `Chunk` 模型扩展 + DB 迁移 | `vector_store_libsql.py` | `test_memory_schema.py` |
| 2 | `compute_importance()` | `rag_core/memory_scoring.py` | 纯函数单测 |
| 3 | `forgetting_decay()` | 同上 | 纯函数单测 |
| 4 | `compute_final_score()` | 同上 | 纯函数单测 |
| 5 | `update_after_retrieval()` | 同上 | 纯函数单测 |
| 6 | 检索接入（开关控制） | `vector_store_libsql.py` | 集成测试 |
| 7 | `/api/memories/stats` | `rag_server_v2.py` | API 测试 |

---

## 4. Phase 2：向量检索优化（Tier 1 快速胜利）

| # | 任务 | 预期收益 |
|---|------|---------|
| 1 | 向量化余弦（`matrix @ q` + 查询预归一化 + top-k 才解析 JSON） | 11s → **<0.3s** |
| 2 | 入库时向量预归一化（检索退化为纯点积） | 再省一次除法 |
| 3 | 确认 `_query_cache` 命中 | 重复查询免 embedding |
| 4 | 服务端接入 `HybridRetriever`（LSH+BM25+RRF） | 术语召回提升 |

> 目标：`/api/search_raw` **< 0.5s**（当前基线 2.2s 为小库时的旧数据）

---

## 5. Phase 3（可选/长期）

- HNSW 索引（`hnswlib`，支撑百万级）
- int8 量化（DB 体积 /4）
- 双轨存储落地（情景 vs 语义自动分层）
- 查询意图分类 + 选择性上下文注入

---

## 6. 验收标准

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| V1 | 测试隔离 | `pytest` 全量跑完后 `chunks` 计数**不变** |
| V2 | KB 完整性 | `/health` `total_documents` = 13198 |
| V3 | 检索性能 | `/api/search_raw` P50 **< 0.5s** |
| V4 | 记忆开关 | `RAG_MEMORY_ENABLED=0` 时行为与旧版**逐字节一致** |
| V5 | 纯函数测试 | `memory_scoring` 单测覆盖 6 维度边界 |
| V6 | 可观测性 | `/api/memories/stats` 返回结构正确 |
| V7 | 回归 | `node --test` 15 passed / `pytest` 目标测试全绿 |

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| DB 迁移失败 | 迁移前自动备份 `knowledge_base.db`；新列全有默认值 |
| 评分拖慢检索 | 纯函数、无 IO；开关可关 |
| 遗忘误杀重要 chunk | **软遗忘**（只降权不删除）；支持手动 pin |
| 测试再污染 | P0-1a 先落地（临时 DB）+ CI 断言计数 |

---

## 8. 决策记录（已确认 2026-11-03）

- **Q1 = C**：重要性评分采用**混合方案**（规则引擎打底 + LLM 复核灰区）
- **Q2 = A**：遗忘半衰期 **7 天**（`RAG_RECALL_HALF_LIFE` 可覆盖）
- **Q3 = 甲**：**先修 P0**（测试隔离 + 检索向量化），再进 Phase 1

### 仍未决（不阻塞 P0/Phase 1）
- `storage/*.db`（118MB）是否移出 git 跟踪？当前 `.git` 已 **438MB**

---

## 9. 产出物清单（预期）

- 🆕 `rag_core/memory_scoring.py`
- ✏️ `rag_core/vector_store_libsql.py`（迁移 + 向量化）
- ✏️ `scripts/rag_server_v2.py`（`/api/memories/stats`）
- 🆕 `tests/conftest.py`（DB 隔离）
- 🆕 `tests/test_memory_scoring.py`、`tests/test_memory_schema.py`
- ✏️ `.gitignore`（storage 二进制）
