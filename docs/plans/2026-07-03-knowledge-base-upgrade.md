# LangChain RAG 知识库架构升级实施计划

> **Goal:** 重写 KnowledgeBase 集成 LSH 索引、断点续传、因果排序，实现高性能语义检索引擎
> **Architecture:** 以 ResumeLoader 为加载引擎，同步双写 LSH+ChromaDB，查询时 LSH 优先 + HNSW 回退，小说类文档启用因果排序
> **Tech Stack:** FAISS LSH, ChromaDB HNSW, CausalSorter, EnhancedDocumentProcessor

---

## 清理旧数据（实施前执行）

```bash
# 清理旧备份目录
rm -rf storage/knowledge_backup/
rm -rf storage/knowledge_backup_20260628/
rm -rf storage/novel_kb/

# 清空主数据库（重建）
rm -f storage/knowledge_base/chroma.sqlite3
rm -rf storage/knowledge_base/01dcfc62-7d5e-4d54-9c70-0e618b88c169/
```

---

## Task 1: 修改 rag_config.py 新增配置项

**TDD scenario:** Trivial change — 直接修改配置，测试在后续任务中验证

**Files:**
- Modify: `rag_config.py`

**步骤：**

### 步骤 1: 在 rag_config.py 末尾添加新配置

```python
# ==================== 小说加载配置 ====================
NOVEL_SPLIT_PATTERN = r"第[一二三四五六七八九十百千0-9]+[章节回卷集篇]"
NOVEL_CHAPTERS_DIR = DOCUMENTS_DIR / "novel_chapters"

# ==================== LSH 索引存储 ====================
LSH_INDEX_DIR = STORAGE_DIR / "lsh_index"
LSH_INDEX_FILE = LSH_INDEX_DIR / "index.faiss"
LSH_ID_MAP_FILE = LSH_INDEX_DIR / "id_map.pkl"
LSH_LOAD_STATE_FILE = LSH_INDEX_DIR / "load_state.json"

# ==================== 召回阈值 ====================
LSH_RECALL_MIN_COUNT = 5       # LSH 最少返回数
LSH_RECALL_MIN_SCORE = 0.6     # 最低相似度分数

# ==================== 同步双写 ====================
SYNC_DOUBLE_WRITE = True       # True=同步双写, False=仅写ChromaDB

# ==================== 架构开关 ====================
USE_NEW_ARCHITECTURE = True    # True=使用新架构, False=回滚到旧版本
```

**验证：**
```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" -c "from rag_config import LSH_RECALL_MIN_COUNT, SYNC_DOUBLE_WRITE, USE_NEW_ARCHITECTURE; print(f'LSH_MIN={LSH_RECALL_MIN_COUNT}, SYNC={SYNC_DOUBLE_WRITE}, NEW_ARCH={USE_NEW_ARCHITECTURE}')"
```

---

## Task 2: 修改 LSHIndexManager 接口

**TDD scenario:** 修改已有代码 — 先运行现有测试，修改后重新运行

**Files:**
- Modify: `rag_core/lsh_index.py`

**步骤 1: 添加 `add_documents` 新方法**

在 `LSHIndexManager` 类中添加：

```python
def add_documents(self, documents: List[Document], embeddings: np.ndarray) -> int:
    """
    添加文档到 LSH 索引（新接口）
    
    Args:
        documents: Document 列表（含 metadata）
        embeddings: 对应的向量数组 (N, dim)
    
    Returns:
        成功添加的文档数
    """
    if len(documents) != len(embeddings):
        raise ValueError(f"文档数量 ({len(documents)}) 与向量数量 ({len(embeddings)}) 不匹配")
    
    if embeddings.shape[1] != self.dim:
        raise ValueError(f"向量维度 ({embeddings.shape[1]}) 与索引维度 ({self.dim}) 不匹配")
    
    # 量化向量
    vectors_quantized = self._quantize_vector(embeddings)
    
    # 添加到 FAISS 索引
    self.index.add(vectors_quantized)
    
    # 更新 id_map
    start_idx = self._total_vectors
    for i, doc in enumerate(documents):
        internal_id = start_idx + i
        self.id_map[internal_id] = doc
    
    self._total_vectors += len(documents)
    logger.info(f"添加 {len(documents)} 个文档到 LSH 索引（当前总计 {self._total_vectors} 个）")
    
    return len(documents)
```

**步骤 2: 添加辅助方法**

```python
def get_documents(self, ids: List[int]) -> List[Document]:
    """根据内部 ID 获取文档对象"""
    return [self.id_map.get(idx) for idx in ids if idx in self.id_map]

def get_scores(self, query_vec: np.ndarray, k: int = 20) -> List[float]:
    """获取检索结果的相似度分数"""
    query_quantized = self._quantize_vector(query_vec.reshape(1, -1))
    distances, indices = self.index.search(query_quantized, k)
    # FAISS LSH 返回的是 Hamming 距离，越小越相似
    # 转换为相似度分数: 1 / (1 + distance)
    scores = [1.0 / (1.0 + d) for d in distances[0]]
    return scores
```

**步骤 3: 运行现有测试验证**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" test_lsh_search.py
```

---

## Task 3: 修改 ResumeLoader 支持 global_counter

**TDD scenario:** 修改已有代码 — 先运行现有测试，修改后重新运行

**Files:**
- Modify: `rag_core/resume_loader.py`

**步骤 1: 修改 __init__ 接受 global_counter**

```python
def __init__(
    self,
    novel_source: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    embedding_batch_size: int = EMBEDDING_BATCH_SIZE,
    use_lsh_index: bool = True,
    global_counter: int = None,  # 新增：全局递增计数器
):
    ...
    self.global_counter = global_counter or 0
```

**步骤 2: 在 load() 方法中分配 global_order**

在 `_assign_global_order` 方法中修改：

```python
def _assign_global_order(self, chunks: List[Document]) -> List[Document]:
    """为 chunk 分配全局递增的 global_order"""
    for chunk in chunks:
        self.global_counter += 1
        chunk.metadata["global_order"] = self.global_counter
        chunk.metadata["doc_type"] = "novel"
        chunk.metadata["source_file"] = self.novel_source
    return chunks
```

**步骤 3: 添加 get_progress 方法**

```python
def get_progress(self) -> dict:
    """返回加载进度"""
    return {
        "total_chunks": self.stats["total_chunks"],
        "loaded_chunks": self.stats["loaded_chunks"],
        "skipped_chunks": self.stats["skipped_chunks"],
        "failed_chunks": self.stats["failed_chunks"],
        "global_counter": self.global_counter,
        "progress_percent": (
            self.stats["loaded_chunks"] / self.stats["total_chunks"] * 100
            if self.stats["total_chunks"] > 0 else 0
        ),
    }
```

**步骤 4: 运行现有测试验证**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" test_resume_loader.py
```

---

## Task 4: 重写 KnowledgeBase

**TDD scenario:** 修改已有代码 — 保留原有 API 签名，修改内部实现

**Files:**
- Modify: `rag_core/knowledge_base.py`

**核心改动：**

```python
class KnowledgeBase:
    def __init__(self, documents_dir=None, auto_import=True, auto_build_parent=True):
        self.documents_dir = documents_dir or DOCUMENTS_DIR
        self.vector_store = VectorStoreManager()
        self.auto_importer = AutoImportManager(...) if auto_import else None
        self.auto_build_parent = auto_build_parent
        self._pipeline = None
        
        # 新增：LSH 索引管理器
        from rag_core.lsh_index import LSHIndexManager
        self.lsh_manager = LSHIndexManager(dim=LSH_DIM, nbits=LSH_NBITS)
        
        # 新增：全局递增计数器
        self._global_order_counter = 0
        self._load_global_counter()
    
    def _load_global_counter(self):
        """从 LSH 索引加载已有的 global_counter"""
        if self.lsh_manager and self.lsh_manager._total_vectors > 0:
            self._global_order_counter = self.lsh_manager._total_vectors
    
    def add_document(self, filepath: str) -> bool:
        """添加单个文档（自动判断是否为小说）"""
        path = Path(filepath)
        if not path.exists():
            logger.error(f"文件不存在: {filepath}")
            return False
        
        # 判断是否为小说类文档
        if self._is_novel_file(filepath):
            return self._add_novel_document(filepath)
        else:
            return self._add_regular_document(filepath)
    
    def _add_regular_document(self, filepath: str) -> bool:
        """添加普通文档（保持原有逻辑）"""
        # ... 原有的 add_document 逻辑不变
        pass
    
    def _add_novel_document(self, filepath: str) -> bool:
        """添加小说文档（使用 ResumeLoader + 同步双写）"""
        try:
            # 1. 使用 ResumeLoader 加载
            loader = ResumeLoader(
                novel_source=filepath,
                global_counter=self._global_order_counter,
            )
            chunks = loader.load(resume=True)
            
            if not chunks:
                logger.warning(f"文档 {filepath} 加载后无新 chunk")
                return True  # 可能已全部加载
            
            # 2. 获取嵌入向量
            from rag_core.embedding_service import get_embeddings
            texts = [c.page_content for c in chunks]
            embeddings = get_embeddings(texts, batch_size=EMBEDDING_BATCH_SIZE)
            
            # 3. 同步双写
            if SYNC_DOUBLE_WRITE:
                # 写 LSH
                self.lsh_manager.add_documents(chunks, embeddings)
                # 写 ChromaDB
                self.vector_store.add_documents(chunks)
                # 更新全局计数器
                self._global_order_counter = loader.global_counter
                self._save_global_counter()
            
            logger.info(f"✅ 小说文档已入库: {filepath} ({len(chunks)} 个块)")
            return True
            
        except Exception as e:
            logger.error(f"添加小说文档失败 {filepath}: {e}")
            return False
    
    def _is_novel_file(self, filepath: str) -> bool:
        """判断是否为小说类文档"""
        path = Path(filepath)
        # 在 novel_chapters 目录下的文件视为小说
        if NOVEL_CHAPTERS_DIR and path.resolve().is_relative_to(NOVEL_CHAPTERS_DIR.resolve()):
            return True
        # 文件名包含"蛊真人"等关键词
        if "蛊真人" in path.name or "novel" in path.name.lower():
            return True
        return False
    
    def search(self, query: str, top_k: int = None, score_threshold: float = None, source: str = None) -> dict:
        """搜索知识库（LSH 优先 + 回退 + 因果排序）"""
        # 关键优化：搜索时不触发自动导入
        return self.pipeline.ask(query, top_k, score_threshold, source)
    
    def get_novel_status(self) -> dict:
        """获取小说加载状态"""
        return {
            "global_counter": self._global_order_counter,
            "lsh_total_vectors": self.lsh_manager._total_vectors if self.lsh_manager else 0,
        }
    
    def rebuild(self, novel_only: bool = False) -> int:
        """重建知识库"""
        if novel_only:
            # 仅清空小说数据
            logger.info("开始重建小说知识库...")
            # 清空 LSH 索引
            if self.lsh_manager:
                self.lsh_manager.clear()
            self._global_order_counter = 0
            return 0
        else:
            # 清空全部
            logger.info("开始重建知识库...")
            self.vector_store.delete_collection()
            self.vector_store = VectorStoreManager()
            self._pipeline = None
            if self.lsh_manager:
                self.lsh_manager.clear()
            self._global_order_counter = 0
            return self.add_directory()
```

**步骤 1: 备份原有文件**

```bash
copy rag_core\knowledge_base.py rag_core\knowledge_base.py.bak
```

**步骤 2: 重写 knowledge_base.py**

**步骤 3: 验证 API 兼容性**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" -c "
from rag_core import KnowledgeBase
kb = KnowledgeBase()
print(f'List docs: {len(kb.list_documents())} documents')
print(f'Stats: {kb.get_stats()}')
"
```

---

## Task 5: 修改 rag_pipeline.py 集成 LSH 检索

**TDD scenario:** 修改已有代码 — 先运行现有搜索测试

**Files:**
- Modify: `rag_core/rag_pipeline.py`

**核心改动：**

在 `RagPipeline` 的 `search()` 方法中增加 LSH 优先逻辑：

```python
class RagPipeline:
    def __init__(self, vector_store=None):
        self.vector_store = vector_store or VectorStoreManager()
        # 新增：LSH 管理器引用
        self.lsh_manager = None  # 由 KnowledgeBase 注入
    
    def set_lsh_manager(self, lsh_manager):
        """注入 LSH 管理器"""
        self.lsh_manager = lsh_manager
    
    def search(self, query: str, top_k: int = 5):
        """
        混合检索：LSH 优先 + HNSW 回退
        
        1. 先用 LSH 检索
        2. 如果召回不足（数量 < top_k 或 分数 < 0.6），回退到 HNSW
        3. 对小说类文档启用因果排序
        """
        from rag_core.embedding_service import get_embedding
        from rag_config import LSH_RECALL_MIN_COUNT, LSH_RECALL_MIN_SCORE
        
        # 1. 获取查询向量
        query_vec = get_embedding(query)
        
        # 2. LSH 优先检索
        lsh_results = []
        lsh_scores = []
        if self.lsh_manager:
            lsh_ids = self.lsh_manager.search(query_vec, k=top_k * 2)
            if lsh_ids:
                lsh_results = self.lsh_manager.get_documents(lsh_ids)
                lsh_scores = self.lsh_manager.get_scores(query_vec, k=len(lsh_ids))
        
        # 3. 判断是否需要回退
        need_fallback = (
            len(lsh_results) < LSH_RECALL_MIN_COUNT or
            (lsh_scores and max(lsh_scores) < LSH_RECALL_MIN_SCORE)
        )
        
        if need_fallback:
            # 回退到 ChromaDB HNSW
            hnsw_docs = self.vector_store.search(query, top_k=top_k * 2)
            # 合并去重
            all_results = self._merge_results(lsh_results, hnsw_docs)
        else:
            all_results = lsh_results
        
        # 4. 条件因果排序
        all_results = self._apply_causal_sort(all_results)
        
        # 5. 截断到 top_k
        return all_results[:top_k]
    
    def _apply_causal_sort(self, documents: List[Document]) -> List[Document]:
        """对包含 global_order 的文档应用因果排序"""
        from rag_core.causal_sorter import CausalSorter
        
        # 检查是否有足够的小说类文档
        novel_count = sum(1 for d in documents if d.metadata.get("doc_type") == "novel")
        if novel_count / max(len(documents), 1) <= 0.8:
            return documents  # 非小说类，不排序
        
        # 应用因果排序
        sorter = CausalSorter(context_window=5, expand_neighbors=2)
        return sorter.sort(documents)
```

---

## Task 6: 修改 rag_cli.py 新增命令

**TDD scenario:** 修改已有代码 — 保留原有命令

**Files:**
- Modify: `rag_cli.py`

**新增命令：**

```python
def cmd_novel_list(args):
    """列出已加载的小说章节"""
    kb = KnowledgeBase()
    docs = kb.list_documents()
    novel_docs = [d for d in docs if d.get('source', '').startswith('novel_chapters')]
    print(f"📚 小说文档: {len(novel_docs)} 个文件")
    for d in novel_docs[:20]:
        print(f"  - {d['source']}")

def cmd_novel_add(args):
    """添加单个小说章节"""
    kb = KnowledgeBase()
    success = kb.add_document(args.file)
    print(f"{'✅' if success else '❌'} 添加{'成功' if success else '失败'}: {args.file}")

def cmd_novel_add_all(args):
    """批量加载所有章节"""
    kb = KnowledgeBase()
    chapter_dir = NOVEL_CHAPTERS_DIR
    if not chapter_dir.exists():
        print(f"❌ 章节目录不存在: {chapter_dir}")
        return
    
    chapters = sorted(chapter_dir.glob("*.txt"))
    print(f"📚 找到 {len(chapters)} 个章节文件")
    
    for i, chapter in enumerate(chapters, 1):
        print(f"[{i}/{len(chapters)}] 加载: {chapter.name}")
        kb.add_document(str(chapter))
    
    print(f"✅ 批量加载完成: {len(chapters)} 个章节")

def cmd_novel_status(args):
    """查看加载进度"""
    kb = KnowledgeBase()
    status = kb.get_novel_status()
    print(f"📊 小说加载状态:")
    print(f"  Global Counter: {status['global_counter']}")
    print(f"  LSH 总向量: {status['lsh_total_vectors']}")

def cmd_rebuild(args):
    """重建知识库"""
    kb = KnowledgeBase()
    novel_only = getattr(args, 'novel_only', False)
    count = kb.rebuild(novel_only=novel_only)
    print(f"✅ 知识库重建完成")

# 在 main() 中添加子命令：
# novel list
# novel add <file>
# novel add-all
# novel status
# rebuild --all
# rebuild --novel-only
```

---

## Task 7: 运行完整测试

**TDD scenario:** 修改已有代码 — 运行所有测试

**步骤 1: 运行 LSH 测试**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" test_lsh_search.py
```

**步骤 2: 运行 ResumeLoader 测试**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" test_resume_loader.py
```

**步骤 3: 验证 KnowledgeBase API 兼容性**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" -c "
from rag_core import KnowledgeBase
kb = KnowledgeBase()
print(f'List docs: {len(kb.list_documents())} documents')
stats = kb.get_stats()
print(f'Stats: {stats}')
"
```

**步骤 4: 验证 CLI 命令**

```bash
cd D:/class/project-config/langchain-rag
"D:/class/miniconda3/envs/ml_env/python.exe" rag_cli.py stats
"D:/class/miniconda3/envs/ml_env/python.exe" rag_cli.py list
```

---

## 验收标准

- [ ] `rag_config.py` 新增配置项正确
- [ ] `LSHIndexManager.add_documents()` 接口工作正常
- [ ] `ResumeLoader` global_counter 全局递增
- [ ] `KnowledgeBase` 重写后 API 兼容
- [ ] `RagPipeline` LSH 优先检索 + HNSW 回退
- [ ] `CausalSorter` 条件启用（doc_type == "novel" 占比 > 80%）
- [ ] CLI 新增 `novel list/add/add-all/status` 命令
- [ ] CLI `rebuild --all/--novel-only` 参数正确
- [ ] 所有现有测试通过
- [ ] 小说章节加载成功

---

**计划创建时间**: 2026-07-03
**预计实施时间**: 4-6 小时
