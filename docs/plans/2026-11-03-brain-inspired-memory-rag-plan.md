# 脑启发性记忆 RAG + 向量检索优化 —— 实施计划（草案）

> 创建时间：2026-11-03
> 状态：**✅ P0 已修复 + Phase 1 已实施 + Review 已通过（2026-11-04）**
> 最新更新：2026-11-04（Review 阶段发现 2 个 Critical，已修复并清理残留污染）
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

## 1. P0-1：知识库数据事故（✅ 已恢复 + 隔离机制已加固）

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
| P0-1a | 新增 `tests/conftest.py`：所有向量库测试使用 **临时目录 DB**（`tmp_path`），禁止触碰 `storage/` | ✅ 已完成（`730c93c`，Review 阶段**再次加固**） |
| P0-1b | `storage/*.db`、`*.index`、`id_map.pkl` **移出 git 跟踪**（>100MB 二进制入库不当）→ `.gitignore` | ✅ 已完成（`6ef1727`，方案甲） |
| P0-1c | 处理 `stash@{0}` 中未提交代码：`get_chunks_by_source()`、`doc.id = chunk_id`（见 §1.1） | ⏳ 待用户裁决 |

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

### 实测（12591 chunks × 512 dim，热态）

| 阶段 | 旧实现 | 修复后 |
|------|--------|--------|
| `SELECT` 全表 | 0.123s | 0.123s |
| `_cosine_similarity_query` | 0.38~0.43s | **0.18~0.24s** |
| `search()` 端到端（热） | 1.05~1.18s | **0.19~0.21s** |

> ⚠️ **更正**：本文档初版曾写“avg 11.2s / max 50.9s / ~150×”——那是**冷进程 + 内存压力**下的抖动，不是算法问题。
> 真实改善约 **5×**（主要体现在“不再对全表做 json.loads”）。详细复测见 `documents/research_vector-search.md` §2.2。

### 根因（已修复）
`rag_core/vector_store_libsql.py` `_cosine_similarity_query()`：
1. 🔴 循环内重复 `np.linalg.norm(query_embedding)`（每行一次）
2. 🔴 逐行 `np.dot`（Python 层调用）
3. 🔴 对**全部**行做 `json.loads`（这才是 `search()` 比裸扫描多出的 ~0.7s）

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

| # | 任务 | 产出 | 测试 | 状态 |
|---|------|------|------|------|
| 1 | `Chunk` 模型扩展 + DB 迁移 | `vector_store_libsql.py` | `test_memory_schema.py`（7） | ✅ |
| 2 | `compute_importance()` | `rag_core/memory_scoring.py` | 纯函数单测 | ✅ |
| 3 | `forgetting_decay()` | 同上 | 纯函数单测 | ✅ |
| 4 | `compute_final_score()` | 同上 | 纯函数单测 | ✅ |
| 5 | `update_after_retrieval()` | 同上 | 纯函数单测 | ✅ |
| 6 | 检索接入（开关控制） | `vector_store_libsql.py` | `test_memory_retrieval.py`（12） | ✅ |
| 7 | `/api/memories/stats` | `rag_server_v2.py` | `test_memory_stats.py`（10） | ✅ |
| 8 | 记忆层鲁棒性（NaN/±inf/非 str/迁移竞态） | `memory_scoring.py`、`vector_store_libsql.py` | 新增 20 项 | ✅ |
| 9 | 测试隔离彻底化 + 守卫覆盖面 | `tests/conftest.py`、`wiki_db_libsql.py` | `test_guard_coverage.py`（13） | ✅ |

> 纯函数单测共 **35 项**（`test_memory_scoring.py`），覆盖长度/关键词/来源权重/半衰期/边界/封顶。

### ⚠️ 实施中的两处偏离（已记录）

1. **半衰期语义修正**：设计草稿写 `exp(-Δ/H)`（Δ=H 时剩 36.8%），
   但参数名叫 `half_life_days`。已改为真半衰期 `2 ** (-Δ/H)`（Δ=H 时恰为 **50%**），
   与 Q2=A「7 天忘一半」的直觉一致。
2. **返回分数语义**：开关开启时 `search()` 返回的分数是**记忆综合分**（保证“按分数降序”成立），
   原始余弦相似度放在 `metadata["similarity"]`。关闭时不变。

---

### 3.6 Review 阶段发现与加固（2026-11-04）

> 完整报告：`docs/reviews/2026-11-04-phase1-memory-review.md`
> 方式：2 个 code-reviewer 子代理 + 1 次人工实证（范围 C 子代理派发失败：403 并行 / 429 限流 / 120s 无响应）
> 原则：**所有审查结论先实证再采信** —— 14 项发现中 **4 项为误报**，已驳回并写明理由

#### 🔴 Critical 1：测试一直在写生产库（守卫升级后才抓到）

前两次事故（13198→690、+607 块）的**清场并不彻底** —— 守卫只盯 3 个文件，给了虚假安全感。

```
id_map.pkl:        +173B
knowledge_base.db: size 不变、mtime 变   ← INSERT OR REPLACE，只看 size/行数必然漏报
novel_lsh.index:   +256B
```

**根因（三层，逐层实证）**：
1. `WikiDB` 默认路径**从 `__file__` 推算**而非读 `rag_config` 常量 → monkeypatch 无效；且 `get_wiki_db()` 是**全局单例**
2. `conftest` 扫描 `sys.modules` 批量 patch 时，**把自身的 `STORAGE_DIR` 也 patch 了** → 后续 `_is_under(v, STORAGE_DIR)` 的比较基准被污染 → `rag_config.*` 一个都没 patch 上（探测输出 `patched 1`，本该 ~10）
3. 旧守卫覆盖面太窄（`vector_store.db` / `wiki.db` / `progress_*.json` / `global_counter.json` 全裸奔）

**修复**：`PRODUCTION_STORAGE` 不可变基准 + 跳过 conftest 自身 + 守卫覆盖 `storage/` 全量（排除 `*.log`）+ `WikiDB` 改走配置常量 + 重置单例。

> ✅ 教训：**窄守卫比没有守卫更危险**（虚假安全感）；指纹必须用 `(size, mtime_ns)` 而非计数/size；验收隔离要看**实际路径**而不是“守卫没报警”。

#### 🔴 Critical 2：NaN 相似度会排到**最前**

`max(0.0, min(1.0, nan)) == 1.0`（NaN 比较恒为 False）→ 损坏向量直接霸榜。
修复：`memory_scoring._unit()` 统一钳制（NaN→default；±inf 按实数序）；`_safe_count()` 防 NaN 计数。

#### 🟡 Important

- DB 迁移并发 → `duplicate column` → `VectorStoreManager.__init__` 崩溃 → `_add_column_if_missing()` 捕获 `sqlite3.OperationalError`
  - ⚠️ 审查建议的 `ADD COLUMN IF NOT EXISTS` **SQLite 并不支持**（实测 3.51.2 语法错误）→ 改用 try/except
- `_reinforce` 加显式 `rollback()`；`get_memories_stats` 加 `WHERE last_access IS NOT NULL`
- `_memory_rerank` 改显式排序键（原元组排序尾部混有 `None`/`datetime`，理论可 `TypeError`）

#### ❌ 被驳回的误报（4 项）

| 审查结论 | 实证 |
|---------|------|
| `.{0,6}` 正则跨行匹配 | 不成立 — Python `.` 默认不匹配 `\n`（实测 False） |
| 测试注释写 “1 microsecond” | 不成立 — 代码中无此注释（幻觉） |
| `_reinforce` 逐条 UPDATE 会部分提交 | 不成立 — `isolation_level=''` 隐式事务，提交原子 |
| 建议改 `ADD COLUMN IF NOT EXISTS` | **建议本身有误** — SQLite 不支持 |

#### 🧹 残留污染清理

审计出测试窗口写入的 **10 块**（`_pytest_*` / `test*.txt|md|json` / `subdir\nested.txt` / `integration_test.txt`）→ 先备份 `knowledge_base.db.pre-testfix-20261104` → 按**精确 chunk_id** 删除 → **12596 → 12586**，残留测试命名源：无。

---

> 本轮提交：`10424db`（fix）、`66ae7df`（复盘）

## 4. Phase 2：向量检索优化（Tier 1）

| # | 任务 | 状态 | 收益 |
|---|------|------|------|
| 1 | 向量化余弦（矩阵拼接 + `mat @ q` + `argpartition` + 只解析 top-k） | ✅ 已完成 | `search()` 热态 **1.05~1.18s → 0.19~0.21s** |
| 2 | 入库时向量预归一化（检索退化为纯点积） | 待办 | 再省一次除法 |
| 3 | 确认 `_query_cache` 命中 | 待办 | 重复查询免 embedding |
| 4 | 服务端接入 `HybridRetriever`（LSH+BM25+RRF） | 待办 | 术语召回提升 |

> 注：`/api/search_raw` 的剩余耗时主要在 **query embedding（冷 14~17s / 热 0.013s）** 与多路召回/融合，
> 而非余弦扫描。若要继续压总延迟，优先看这两处。

---

## 5. Phase 3（可选/长期）

- HNSW 索引（`hnswlib`，支撑百万级）
- int8 量化（DB 体积 /4）
- 双轨存储落地（情景 vs 语义自动分层）
- 查询意图分类 + 选择性上下文注入

---

## 6. 验收标准

| 编号 | 验收项 | 通过条件 | 状态 |
|------|--------|---------|------|
| V1 | 测试隔离 | `pytest` 全量跑完后 `chunks` 计数**不变** | ✅ 守卫零触发（**12586** 不变，已升级为全目录守卫） |
| V2 | KB 完整性 | 生产库记忆列已迁移且数据无损 | ✅ 5 列已加，12591 不变 |
| V3 | 检索性能 | `_cosine_similarity_query` 在 N=20000 下 **< 0.35s** | ✅ 0.239s（回归测试） |
| V4 | 记忆开关 | `RAG_MEMORY_ENABLED=0` 时行为与旧版**逐字节一致** | ✅ 12 项测试（含“不写库”） |
| V5 | 纯函数测试 | `memory_scoring` 单测覆盖 6 维度边界 | ✅ 35 passed |
| V6 | 可观测性 | `/api/memories/stats` 返回结构正确 | ✅ 10 passed + 生产库实测 |
| V7 | 回归 | `node --test` + `pytest` 目标测试全绿 | ✅ node 25 / pytest **178 passed**（1 failed 为预存 `test_path_config`）/ 0 errors |
| V8 | 隔离实证 | 测试内构造 `UnifiedImporter`，`vs.db_path` 与 `wiki_db.db_path` 必须都落在 `tmp_path` | ✅ 探测确认（Review 阶段新增） |

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
- ~~`storage/*.db`（118MB）是否移出 git 跟踪？~~ → **已决（2026-11-04，方案甲）**：移出跟踪 + `.gitignore`，**保留历史不做 filter-repo**；`.git` 仍 438MB
- `stash@{0}` **仍待裁决**（含 `get_chunks_by_source()` / `doc.id = chunk_id`；⚠️ 含过时 `.cn` 配置，**不可整体 pop**）
- 备份文件去留：`knowledge_base.db.pre-cleanup-20261104`、`.pre-testfix-20261104`（各 118MB）

---

## 9. 产出物清单

- 🆕 `rag_core/memory_scoring.py`
- ✏️ `rag_core/vector_store_libsql.py`（迁移 + 向量化）
- ✏️ `scripts/rag_server_v2.py`（`/api/memories/stats`）
- 🆕 `tests/conftest.py`（DB 隔离）
- 🆕 `tests/test_memory_scoring.py`、`tests/test_memory_schema.py`、`tests/test_memory_retrieval.py`、`tests/test_memory_stats.py`
- 🆕 `tests/test_guard_coverage.py`（守卫覆盖面，13 项）
- 🆕 `docs/reviews/2026-11-04-phase1-memory-review.md`（Review 报告）
- ✏️ `rag_core/wiki_db_libsql.py`（默认路径走配置常量 + 自动建父目录）
- ✏️ `tests/conftest.py`（不可变基准 + 全目录守卫）
- ✏️ `.gitignore`（storage 二进制）
