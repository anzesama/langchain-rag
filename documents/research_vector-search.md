# 向量检索实现调研（Vector Search for RAG）

> 调研时间：2026-11-03
> 目标系统：`D:/class/project-config/langchain-rag`
> 数据来源：Crossref API 文献检索 + 本仓库实测基准

---

## 一、执行摘要

| 结论 | 说明 |
|------|------|
| **当前瓶颈不在 ANN 算法** | 12591 chunks 下 `SELECT` 仅 0.12s、余弦扫描 0.4s、`search()` 热态 ~1.1s——对本量级，暴力检索**完全够用** |
| **最优先动作：向量化 + 只解析 top-k** | 已实施：`search()` 热态 **1.05~1.18s → 0.19~0.21s**（~5×） |
| **第二步：算法选型** | 数据量 <10 万时暴力/精确检索可用；破 10 万再上 **HNSW**；>100 万考虑 IVF-PQ / DiskANN |
| **第三步：混合检索** | 仓库已有 `HybridRetriever`（LSH+BM25+reranker），但**服务端未接入** → 一键启用 |
| **第四步：压缩** | int8 / binary 量化可将索引内存降 4~32×，召回损失 <3% |

> ⚠️ **重要更正（2026-11-03）**：本文件初版曾声称“逐行实现 11~51s、向量化快 150×”。
> 该数据来自**冷进程 + 内存压力**（free RAM ~700MB、服务 Private 922MB）下的抖动，
> **不是算法问题**。复测（内存平稳、进程预热）后真实数字见 §2.2。教训：
> **性能结论必须在热态、内存平稳、多次重复后取中位数**，否则会把抖动当成算法缺陷。

---

## 二、当前实现分析（实测）

### 2.1 代码路径

```
/api/search_raw → KnowledgeBase.search_raw() → VectorStoreManager.search()
                                                    └─ _cosine_similarity_query()   ← 瓶颈
```

`rag_core/vector_store_libsql.py:86-132`：

```python
cursor.execute('SELECT chunk_id, vector, metadata, text_content FROM chunks')  # 全表拉取
all_chunks = cursor.fetchall()
...
for chunk_id, vector_blob, metadata_json, text_content in all_chunks:
    vector = self._blob_to_vector(vector_blob)
    norm_q = np.linalg.norm(query_embedding)   # 🔴 每轮循环重算 13198 次
    norm_v = np.linalg.norm(vector)
    similarity = np.dot(query_embedding, vector) / (norm_q * norm_v)
    similarities.append(({... 'metadata': json.loads(metadata_json) ...}, similarity))  # 🔴 全量 json 解析
similarities.sort(...)   # 🔴 全量排序
return similarities[:top_k]
```

**三处浪费**：
1. `np.linalg.norm(query_embedding)` 在循环内 → 应提到循环外（或查询前 L2 归一化，直接点积即余弦）
2. 逐行 `np.dot`（Python 层 13198 次调用）→ 应改成 `matrix @ q` 单次调用
3. 对**所有** 13198 条做 `json.loads` → 应只对 top_k 解析

### 2.2 实测基准（12591 chunks, dim=512, CPU, 热态）

| 操作 | 修正前（旧实现） | 修正后（向量化） |
|------|-----------------|-----------------|
| `SELECT chunk_id, vector, metadata, text_content`（全表） | 0.123s | 0.123s |
| `_cosine_similarity_query()` | 0.38 ~ 0.43s | **0.18 ~ 0.24s** |
| `search()` 端到端（热） | 1.05 ~ 1.18s | **0.19 ~ 0.21s** |
| `get_embeddings()` 冷 / 热 | 14~17s / 0.013s | 同左（未改动） |

> 📌 旧实现 `search()` 比裸扫描多出的 ~0.7s，主要来自**对全部 12591 行做 `json.loads`**。
> 新实现只解析 top-k，故 `search()` 基本等于扫描耗时。

> ❌ **已废弃的错误数据**：初版记录的 `search()` avg 11.19s / max 50.89s —— 系冷进程 + 内存压力抖动，**不具代表性**。

### 2.3 另一个发现：HybridRetriever 未接入

- `rag_core/hybrid_retriever.py`（417 行）已实现 **LSH 召回 + HNSW 召回 + BM25 召回 + RRF 融合 + reranker + 因果排序**
- `rage_core/lsh_index.py`（432 行，FAISS IndexLSH，int8 量化）已实现，索引文件 `storage/novel_lsh.index` (9.5MB) 存在
- 但 `scripts/rag_server_v2.py` 的 `/api/search*` **直接走 `vector_store.search()`**，没走 HybridRetriever
- `rag_pipeline.py` 里才有 `_get_hybrid_retriever()`

→ **已有轮子没装上车**。接上去即可获得混合检索能力。

---

## 三、ANN 算法选型

### 3.1 分类

| 类别 | 代表 | 构建 | 查询 | 内存 | 适用规模 |
|------|------|------|------|------|---------|
| **图索引** | HNSW, NSG, DiskANN | 慢 | **最快** | 中 | 1k ~ 100M |
| **倒排+量化** | IVF-Flat, IVF-PQ | 中 | 快 | **低** | 100k ~ 1B |
| **哈希** | LSH（本仓库采用） | 最快 | 快 | 低 | 中，召回偏低 |
| **树** | Annoy（随机投影树） | 中 | 中 | 低 | 静态数据集 |

### 3.2 HNSW（首选）

- **原理**：多层可导航小世界图，上层稀疏做"高速公路"，底层稠密做精搜
- **参数**：`M`（每节点连接数，16~48）、`efConstruction`（200~500）、`efSearch`（64~256）
- **优势**：召回 95%+ 时 QPS 最高；增量插入友好（本项目边导边查）
- **劣势**：内存 ≈ `N × dim × 4B × (1 + 图开销)`；删除需墓碑标记
- **实现**：`hnswlib`（轻量，pip 可装）、FAISS `IndexHNSWFlat`

> 文献：*Zonal HNSW: Scalable ANN for Billion-Scale Datasets* — DOI [10.1109/icssas66150.2025.11081070](https://doi.org/10.1109/icssas66150.2025.11081070)

### 3.3 IVF-PQ（大规模首选）

- **原理**：k-means 聚类分桶（IVF）+ 子空间乘积量化（PQ）压缩向量
- **优势**：内存可降 4~64×；十亿级可行
- **劣势**：召回对 `nprobe` 敏感；构建成本高
- **文献**：*Optimizing Vector Embedding Storage and Indexing for AI at Scale*（2026）提出 **渐进量化流水线 PQP**：MRL 降维 + 熵引导位宽分配 + 残差 PQ，**最高 256× 压缩、召回损失 <3%** — DOI [10.47363/jaicc/2026(5)518](https://doi.org/10.47363/jaicc/2026(5)518)

### 3.4 LSH（本仓库现状）

- 已用 `FAISS.IndexLSH(nbits=2048)` + int8 量化
- 优点：**构建极快、增量友好**；缺点：召回率低于 HNSW（尤其高维）
- 建议：保留作为"粗召回"，用 HNSW 或 reranker 兜精度

---

## 四、量化与压缩

| 方案 | 压缩比 | 召回损失 | 备注 |
|------|-------|---------|------|
| float32 → **int8** 标量量化 | 4× | 很小 (<1%) | 实现简单，先做这个 |
| **binary**（1 bit/维） | 32× | 中等 | 需 RaBitQ 类误差界补偿 |
| **PQ** 乘积量化 | 8~64× | 中等 | 需训练码本 |
| **MRL**（Matryoshka 表示学习） | 可变 | 小 | bge-m3 等模型原生支持，可直接截断维度 |

**文献**：
- *4bit-Quantization in Vector-Embedding for RAG*（IEEE ICMLA 2024）— DOI [10.1109/icmla61862.2024.00156](https://doi.org/10.1109/icmla61862.2024.00156)
- *SMEC: Rethinking Matryoshka Representation Learning for Retrieval Embedding Compression*（EMNLP 2025）— DOI [10.18653/v1/2025.emnlp-main.1332](https://doi.org/10.18653/v1/2025.emnlp-main.1332)

> ✅ 本仓库 `lsh_index.py` 注释已提到"支持 int8 动态量化"，可复用。

---

## 五、混合检索（Dense + Sparse）

### 5.1 为什么

纯向量相似度存在**语义漂移**：术语/专有名词（如 `pi_rag_tool.ts`、`RAG_SHELL`）用 BM25 精确匹配远好于 embedding。

**文献支撑**：*When Retrieval Similarity Hurts: A Diagnostic Framework for Document Weighting in Black-Box RAG*（EMNLP 2026 Findings）— 高相似但低重要性的文档会**伤害**生成质量 — DOI [10.18653/2026.findings-emnlp.594](https://doi.org/10.18653/2026.findings-emnlp.594)

### 5.2 融合算法

| 算法 | 说明 | 推荐 |
|------|------|------|
| **RRF**（Reciprocal Rank Fusion） | `score = Σ 1/(k + rank)`，k=60 | ✅ 无需调参，最稳 |
| 加权线性 | `α·dense + (1-α)·sparse` | 需调权重 |
| 学习排序 | 需标注数据 | 后期 |

### 5.3 本仓库现状

`rag_core/fusion/hybrid_fusion.py` 与 `hybrid_retriever.py` 已实现 RRF 式融合 → **接线即可**。

---

## 六、重排序（Reranking）

| 类型 | 代表 | 延迟 | 效果 |
|------|------|------|------|
| **Cross-Encoder** | bge-reranker-base | 中（需对每个候选跑一次） | 最好 |
| **Late Interaction** | ColBERT / ColBERTv2 | 低（预计算 token 向量） | 接近 cross-encoder |
| LLM 重排 | 直接用 agnes 模型打分 | 高 | 灵活 |

本仓库已有 `rag_core/reranker.py`（150 行）。

**文献**：
- *Interaction-Budget-Matched Analysis of Compact Cross-Encoder Reranking in Hybrid Retrieval*（IEEE Access 2026）— DOI [10.1109/access.2026.3745756](https://doi.org/10.1109/access.2026.3745756)
- *Caraman at SemEval-2026 Task 8: Three-Stage Multi-Turn Retrieval with Query Rewriting, Hybrid Search, and Cross-Encoder Reranking* — DOI [10.18653/v1/2026.semeval-1.225](https://doi.org/10.18653/v1/2026.semeval-1.225)

---

## 七、嵌入式向量库对比

本项目是**本地/边缘部署**（Windows + ml_env），不宜引入独立服务。

| 方案 | 形态 | 优势 | 劣势 |
|------|------|------|------|
| **现状：SQLite BLOB + numpy** | 纯 Python | 零依赖、可 git 版本化 | 需自己写索引 |
| **sqlite-vec** | SQLite 扩展 | 与现有 `.db` 无缝、支持 KNN | 生态较新 |
| **hnswlib**（推荐） | 进程内库 | 快、轻、增量插入 | 需持久化自己管 |
| **FAISS**（已用 FAISS LSH） | 进程内库 | 算法最全（HNSW/IVF/PQ） | 接口偏底层 |
| LanceDB / Qdrant | 嵌入式/服务 | 功能全 | 引入额外依赖 |

**文献**：*A Comparative Analysis of Efficient Similarity Search in Qdrant as a Vector Database and FAISS as a Vector Search Library*（2026）— DOI [10.21203/rs.3.rs-11169373/v1](https://doi.org/10.21203/rs.3.rs-11169373/v1)

**建议**：**继续用 FAISS**（最小改动，已有 LSH，加 `IndexHNSWFlat` + `IndexIVFPQ` 即可）。

---

## 八、RAG 检索质量（非索引层面）

- *Chunking Is Not the Bottleneck: Why RAG Evaluation Must Look beyond Segmentation Strategy*（2026）— DOI [10.5220/0015150400004091](https://doi.org/10.5220/0015150400004091)
  → 分块策略不如**检索+重排**重要
- *Retrieval-Ready Pipelines: Benchmarking Chunking and Embedding Strategies for Enterprise RAG*（2026）— DOI [10.2139/ssrn.7323278](https://doi.org/10.2139/ssrn.7323278)
- *Optimizing RAG of Medical Content for Spaced Repetition Learning*（SuperMemo）→ RAG + 间隔重复结合

---

## 九、改进路线（按性价比排序）

### 🟢 Tier 1 — 快速胜利（改动 <50 行）

1. ✅ **向量化余弦检索**（已完成）：矩阵拼接 + 单次 `mat @ q` + `argpartition` + 只解析 top-k
   - 实测：`search()` 热态 **1.05~1.18s → 0.19~0.21s**（~5×）
2. **查询 embedding 缓存**（已有 `_query_cache`，确认命中率）
3. **入库时预归一化向量**（存单位向量，检索退化为纯点积，省一次除法）

### 🟡 Tier 2 — 算法升级

4. **接入 HNSW**：`hnswlib.Index(space='cosine', dim=512)`，`M=32, efSearch=128`
   - 预期：13k 规模 <5ms；可支撑 100 万级
5. **服务端接入 HybridRetriever**（LSH + BM25 + RRF），术语查询召回显著提升
6. **int8 量化**向量存储，DB 体积降 ~4×

### 🔵 Tier 3 — 长期

7. IVF-PQ / DiskANN（若数据量破百万）
8. ColBERT late-interaction 多向量检索
9. 检索评估集（recall@k / nDCG）自动化回归

---

## 十、参考文献（DOI 汇总）

1. Zonal HNSW — 10.1109/icssas66150.2025.11081070
2. PQP 渐进量化（256× 压缩） — 10.47363/jaicc/2026(5)518
3. 4bit 量化 for RAG — 10.1109/icmla61862.2024.00156
4. SMEC / MRL 压缩 — 10.18653/v1/2025.emnlp-main.1332
5. When Retrieval Similarity Hurts — 10.18653/2026.findings-emnlp.594
6. Compact Cross-Encoder Reranking — 10.1109/access.2026.3745756
7. Hybrid Biomedical Sparse+Dense+Cross-Encoder — 10.1109/icietsd68684.2026.11584705
8. Qdrant vs FAISS — 10.21203/rs.3.rs-11169373/v1
9. Chunking Is Not the Bottleneck — 10.5220/0015150400004091
10. HNSW 实现对比 — 10.36227/techrxiv.175321947.71782908/v1
