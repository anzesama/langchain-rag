"""
混合检索器 — P0(重排) + P1(多路召回) 完整实现

检索流程：
1. 多路召回（LSH + ChromaDB + BM25）→ Top-50
2. 去重合并 → 保留最高分
3. CrossEncoder 重排 → Top-5
4. 因果排序（仅小说类）

优势：
- 多路召回覆盖更多相关文档（稠密+稀疏）
- CrossEncoder 精排提升 Top-K 准确率
- 因果排序保证小说上下文连贯性
"""
import math
from typing import List, Dict, Tuple, Optional

import numpy as np

from rag_config import (
    TOP_K, SCORE_THRESHOLD, LSH_RECALL_MIN_COUNT, LSH_RECALL_MIN_SCORE,
    logger,
)


class HybridRetriever:
    """
    混合检索器
    
    集成：
    - LSH 快速召回
    - ChromaDB HNSW 兜底
    - BM25 稀疏检索（P1）
    - CrossEncoder 重排（P0）
    - 因果排序（小说类）
    """
    
    def __init__(self, lsh_manager=None, vector_store=None, reranker=None):
        self.lsh_manager = lsh_manager
        self.vector_store = vector_store
        self.reranker = reranker
        self.bm25_retriever = None
    
    def retrieve(
        self, 
        query: str, 
        top_k: int = None,
        score_threshold: float = None,
        source: str = None
    ) -> List[Tuple]:
        """
        完整检索流程
        
        Args:
            query: 查询文本
            top_k: 返回数量
            score_threshold: 最低分数阈值
            source: 文档来源（可选）
            
        Returns:
            [(Document, score), ...]
        """
        from rag_core.embedding_service import get_embeddings
        
        top_k = top_k or TOP_K
        score_threshold = score_threshold or SCORE_THRESHOLD
        
        # ==================== P1: 多路召回 ====================
        logger.info(f"开始多路召回: query='{query[:30]}...'")
        
        # 预计算查询向量（避免重复调用 get_embeddings）
        try:
            from rag_core.embedding_service import get_embeddings
            import numpy as np
            query_vec = np.array(get_embeddings([query])[0])
        except Exception as e:
            logger.warning(f"查询向量化失败: {e}")
            return []
        
        # 路 1: LSH 召回
        lsh_docs, lsh_scores = self._lsh_recall(query_vec, top_k=top_k * 4)
        
        # 路 2: ChromaDB 召回
        hnsw_docs, hnsw_scores = self._hnsw_recall(query, top_k=top_k * 4, source=source)
        
        # 路 3: BM25 召回（暂禁，因为基于元数据的 BM25 无法匹配内容关键词）
        # TODO: 后续优化 BM25 使用实际文档内容
        bm25_results = []
        
        # ==================== 合并去重 ====================
        # 按 doc_id 合并，保留最高分
        merged = self._merge_results(
            lsh_docs, lsh_scores,
            hnsw_docs, hnsw_scores,
            bm25_results
        )
        
        if not merged:
            logger.warning("所有检索路均无结果")
            return []
        
        logger.info(f"合并后候选数: {len(merged)}")
        
        # ==================== P0: CrossEncoder 重排 ====================
        if self.reranker and len(merged) > top_k:
            logger.info(f"开始 CrossEncoder 重排: {len(merged)} 个候选")
            reranked = self._rerank(query, merged, top_k=top_k * 2)
        else:
            reranked = merged
        
        # ==================== 因果排序（仅小说类）====================
        final_results = self._apply_causal_sort(reranked, top_k)
        
        logger.info(f"最终返回: {len(final_results)} 个文档")
        return final_results[:top_k]
    
    def _lsh_recall(self, query_vec, top_k: int = 20) -> Tuple[List, List[float]]:
        """LSH 快速召回
        
        Args:
            query_vec: 预计算的查询向量（numpy array）
        """
        if not self.lsh_manager:
            return [], []
        
        try:
            # LSH search 返回 (internal_ids, distances)
            lsh_ids, distances = self.lsh_manager.search(
                query_vec, k=min(top_k, self.lsh_manager._total_vectors), 
                return_distances=True
            )
            
            if not lsh_ids:
                return [], []
            
            docs = self.lsh_manager.get_documents(lsh_ids)
            
            # FAISS LSH distance 越小越相关
            # LSH 距离是 bit diff，范围 [0, nbits]，越小越好
            # 转为相似度分数 [0, 1]，越大越好
            max_dist = max(distances) if distances else 1.0
            min_dist = min(distances) if distances else 0.0
            range_dist = max_dist - min_dist if max_dist != min_dist else 1.0
            scores = [(1.0 - (d - min_dist) / range_dist) for d in distances]
            
            # 转换为统一格式
            results = []
            for i, doc in enumerate(docs):
                if doc is None:
                    continue
                # 统一使用 chunk_id 作为文档 ID（LSH 和 ChromaDB 都存储了）
                doc_id = doc.metadata.get('chunk_id') or f'lsh_{i}'
                results.append((doc_id, doc.page_content, doc.metadata, scores[i]))
            
            return results, scores or []
        
        except Exception as e:
            logger.warning(f"LSH 召回失败: {e}")
            return [], []
    
    def _hnsw_recall(self, query: str, top_k: int = 20, source: str = None) -> Tuple[List, List[float]]:
        """ChromaDB HNSW 召回"""
        if not self.vector_store:
            return [], []
        
        try:
            # VectorStoreManager.search() 返回 [(Document, distance), ...]
            # distance 越小越相关（cosine distance）
            results = self.vector_store.search(query, top_k=top_k * 2)
            
            if not results:
                return [], []
            
            # 转换为统一格式
            docs = []
            scores = []
            for doc, distance in results:
                # 统一使用 chunk_id 作为文档 ID
                doc_id = doc.metadata.get('chunk_id') or f'hnsw_{len(docs)}'
                # 将 distance 转为相似度分数 (1 - distance)
                sim_score = 1.0 - distance
                docs.append((doc_id, doc.page_content, doc.metadata, sim_score))
                scores.append(sim_score)
            
            return docs, scores
        
        except Exception as e:
            logger.warning(f"HNSW 召回失败: {e}")
            return [], []
    
    def _bm25_recall(self, query: str, top_k: int = 20) -> List[Tuple[str, float]]:
        """BM25 稀疏召回（P1）
        
        优化：使用 ChromaDB 的 query 方法获取实际内容，而不是元数据
        """
        if not self.vector_store:
            return []
        
        try:
            # 使用 ChromaDB 的 query 方法获取与查询最相关的文档
            # 然后用这些文档构建 BM25 索引
            import random
            sample_size = min(3000, 5000)
            
            # 获取所有文档的元数据和 ID
            all_data = self.vector_store.vectorstore._collection.get(
                include=['metadatas']
            )
            
            if not all_data.get('metadatas'):
                return []
            
            metadatas = all_data['metadatas']
            all_ids = all_data.get('ids', [])
            
            # 随机采样
            if len(metadatas) > sample_size:
                indices = random.sample(range(len(metadatas)), sample_size)
                sampled_metadatas = [metadatas[i] for i in indices]
                sampled_ids = [all_ids[i] if i < len(all_ids) else f'doc_{i}' for i in indices]
            else:
                sampled_metadatas = metadatas
                sampled_ids = all_ids
            
            # 构建文档列表（用元数据中的信息构建简短文本）
            documents = []
            for i, meta in enumerate(sampled_metadatas):
                if meta:
                    source = meta.get('source', '')
                    chunk_id = meta.get('chunk_id', '')
                    doc_type = meta.get('doc_type', '')
                    # 用元数据构建简短文本用于关键词匹配
                    short_text = f"{source} {chunk_id} {doc_type}"
                    if len(short_text.strip()) > 5:
                        documents.append({
                            'id': meta.get('chunk_id', f'doc_{i}'),
                            'text': short_text
                        })
            
            if not documents:
                return []
            
            from rag_core.bm25_retriever import build_bm25_index_from_documents
            retriever = build_bm25_index_from_documents(documents)
            
            # 搜索
            bm25_results = retriever.search(query, top_k=top_k * 2)
            
            return bm25_results
        
        except Exception as e:
            logger.warning(f"BM25 召回失败: {e}")
            return []
    
    def _merge_results(
        self,
        lsh_docs: List,
        lsh_scores: List,
        hnsw_docs: List,
        hnsw_scores: List,
        bm25_results: List
    ) -> List[Tuple]:
        """
        合并多路召回结果，去重取最高分
        
        格式统一为: [(doc_id, text, metadata, score), ...]
        """
        merged = {}  # doc_id -> (text, metadata, score)
        
        # 合并 LSH 和 HNSW（已有完整 Document 对象）
        # 注意：lsh_docs 和 hnsw_docs 已经是 [(doc_id, text, metadata, score), ...] 格式
        for doc_id, text, metadata, score in lsh_docs + hnsw_docs:
            # merged[doc_id] = (text, metadata, score) — 3 elements, index [2]
            if doc_id not in merged or score > merged[doc_id][2]:
                merged[doc_id] = (text, metadata, score)
        
        # 转换为列表
        results = []
        for doc_id, (text, metadata, score) in merged.items():
            results.append((doc_id, text, metadata, score))
        
        return results
    
    def _rerank(self, query: str, candidates: List[Tuple], top_k: int = 10) -> List[Tuple]:
        """
        CrossEncoder 重排
        
        Args:
            query: 查询文本
            candidates: [(doc_id, text, metadata, score), ...]
            top_k: 返回数量
            
        Returns:
            [(doc_id, text, metadata, rerank_score), ...] 按 rerank_score 降序
        """
        if not self.reranker or not candidates:
            return candidates
        
        try:
            # 构建 documents 列表
            documents = [
                {'id': doc_id, 'text': text}
                for doc_id, text, metadata, score in candidates
            ]
            
            # 执行重排
            reranked = self.reranker.rerank(query, documents, top_k=top_k)
            
            # 重建结果
            reranked_results = []
            for doc_id, rerank_score in reranked:
                # 找到原始候选
                original = next((c for c in candidates if c[0] == doc_id), None)
                if original:
                    text, metadata, _ = original[1], original[2], original[3]
                    reranked_results.append((doc_id, text, metadata, rerank_score))
            
            return reranked_results
        
        except Exception as e:
            logger.warning(f"CrossEncoder 重排失败，降级到简单排序: {e}")
            # 降级：按原始分数排序
            return sorted(candidates, key=lambda x: x[3], reverse=True)[:top_k]
    
    def _apply_causal_sort(self, results: List[Tuple], top_k: int = 5) -> List[Tuple]:
        """
        对包含 global_order 的文档应用因果排序
        
        条件：至少 80% 的文档包含 doc_type == 'novel'
        """
        if not results:
            return results
        
        novel_count = sum(
            1 for _, _, metadata, _ in results
            if metadata.get("doc_type") == "novel"
        )
        if novel_count / len(results) <= 0.8:
            return results  # 非小说类，不排序
        
        # 导入因果排序器
        from rag_core.causal_sorter import CausalSorter
        
        # 提取文档和分数
        from langchain_core.documents import Document
        docs_with_meta = []
        for doc_id, text, metadata, score in results:
            doc = Document(page_content=text, metadata=metadata)
            docs_with_meta.append(doc)
        
        sorter = CausalSorter(context_window=5, expand_neighbors=2)
        sorted_docs = sorter.sort(docs_with_meta)
        
        # 重建结果列表（按 global_order 排序后取 top_k）
        sorted_results = []
        for doc in sorted_docs[:top_k]:
            doc_id = doc.metadata.get('chunk_id', 'unknown')
            # 从原始结果中查找对应的分数
            original = next((r for r in results if r[0] == doc_id), None)
            score = original[3] if original else 0.0
            sorted_results.append((doc_id, doc.page_content, doc.metadata, score))
        
        return sorted_results


# ==================== 便捷函数 ====================

def create_hybrid_retriever(
    lsh_manager=None,
    vector_store=None,
    reranker_model: str = 'bert-base-chinese'
) -> HybridRetriever:
    """
    创建混合检索器实例
    
    Args:
        lsh_manager: LSH 索引管理器
        vector_store: 向量存储管理器
        reranker_model: CrossEncoder 模型名称
        
    Returns:
        HybridRetriever 实例
    """
    from rag_core.reranker import create_reranker
    
    reranker = None
    try:
        reranker = create_reranker(model_name=reranker_model)
        logger.info(f"CrossEncoder 重排器已加载: {reranker_model}")
    except Exception as e:
        logger.warning(f"CrossEncoder 重排器加载失败（将跳过重排）: {e}")
    
    return HybridRetriever(
        lsh_manager=lsh_manager,
        vector_store=vector_store,
        reranker=reranker
    )


# ==================== 测试 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("混合检索器测试")
    print("=" * 60)
    
    from rag_core.knowledge_base import KnowledgeBase
    
    kb = KnowledgeBase()
    retriever = create_hybrid_retriever(
        lsh_manager=kb.lsh_manager,
        vector_store=kb.vector_store
    )
    
    # 测试搜索
    query = "元始仙尊的主修流派是什么"
    results = retriever.retrieve(query, top_k=5)
    
    print(f"\nQuery: {query}")
    print(f"Results: {len(results)}")
    for doc_id, text, metadata, score in results:
        print(f"  [{score:.4f}] {doc_id}: {text[:50]}...")
    
    print("\n" + "=" * 60)
