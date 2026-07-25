# P2 实施计划：混合检索与缓存机制

> 创建时间：2026-06-30 22:00
> 状态：🔄 进行中

---

## 目标

1. **混合检索** — 结合 BM25 关键词检索和向量语义检索
2. **LRU 缓存** — 对频繁查询结果进行缓存，提升响应速度
3. **结果融合** — 将两种检索结果进行加权融合

---

## 任务分解

### 任务 1：BM25 检索器（BM25Retriever）

**文件**：`langchain-rag/rag_core/retrievers/bm25_retriever.py`

**功能**：
- 实现基于 BM25 算法的关键词检索
- 与向量检索并行执行
- 返回排序后的文档列表

**实现要点**：
```python
class BM25Retriever:
    def __init__(self, vector_store: VectorStoreManager):
        self.vector_store = vector_store
        self.bm25 = BM25Model()  # 使用 rank_bm25 库
    
    def retrieve(self, query: str, top_k: int = 5) -> List[Document]:
        """执行 BM25 检索"""
        # 1. 预处理查询（分词、去停用词）
        query_tokens = self._tokenize(query)
        # 2. 计算每个文档的 BM25 分数
        scores = self._calculate_bm25_scores(query_tokens)
        # 3. 返回 top-k 结果
        return self._get_top_k(scores, top_k)
```

**验收标准**：
- [ ] 能正确处理中文分词（使用 jieba）
- [ ] 检索速度与向量检索相当
- [ ] 对关键词匹配的查询效果更好

### 任务 2：结果融合器（ResultFusion）

**文件** `langchain-rag/rag_core/retrievers/result_fusion.py`

**功能**：
- 将 BM25 和向量检索的结果进行融合
- 使用加权平均或 RRFC（倒数排名融合）算法

**实现要点**：
```python
class ResultFusion:
    def fuse(self, bm25_results: List[Document], 
             vector_results: List[Document],
             weights: Tuple[float, float] = (0.4, 0.6)) -> List[Document]:
        """融合两种检索结果"""
        # 1. 计算每个文档的融合分数
        scores = self._calculate_fusion_scores(bm25_results, vector_results, weights)
        # 2. 按融合分数排序
        ranked = self._rank_by_score(scores)
        # 3. 返回最终结果
        return ranked
```

**验收标准**：
- [ ] 融合效果优于单一检索方法
- [ ] 可配置权重参数
- [ ] 支持多种融合算法（加权平均、RRFC）

### 任务 3：LRU 缓存管理器（CacheManager）

**文件**：`langchain-rag/rag_core/cache/cache_manager.py`

**功能**：
- 对查询结果进行缓存
- 使用 LRU 策略管理缓存大小
- 支持缓存失效机制

**实现要点**：
```python
class CacheManager:
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
    
    def get(self, query_hash: str) -> Optional[Any]:
        """获取缓存结果"""
        if query_hash in self.cache:
            self.cache.move_to_end(query_hash)  # 标记为最近使用
            return self.cache[query_hash]
        return None
    
    def put(self, query_hash: str, result: Any):
        """存入缓存"""
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)  # 移除最久未使用的
        self.cache[query_hash] = result
        self.cache.move_to_end(query_hash)
```

**验收标准**：
- [ ] 缓存命中率 > 50%（对于重复查询）
- [ ] 缓存查询响应时间 < 10ms
- [ ] 支持缓存失效和清理

---

## 依赖关系

- [ ] 任务 1 → 任务 2（结果融合需要 BM25 检索结果）
- [ ] 任务 2 → 任务 3（缓存可以应用于融合结果）
- [ ] 任务 1 → 任务 3（缓存也可以应用于 BM25 结果）

---

## 预计工作量

- 任务 1：2-3 小时
- 任务 2：1-2 小时
- 任务 3：2-3 小时

**总计**：5-8 小时

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| BM25 中文分词效果差 | 检索质量下降 | 使用专业中文分词库（jieba） |
| 缓存一致性 | 结果不准确 | 实现文档更新时自动清除缓存 |
| 融合算法复杂 | 效果不佳 | 先从简单加权平均开始 |

---

*计划创建完成，等待实施。*
