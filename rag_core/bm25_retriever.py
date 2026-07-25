"""
BM25 稀疏检索器 — 基于 jieba 分词 + sklearn TF-IDF 近似实现

不依赖 rank_bm25 库，用现有 jieba + sklearn 实现 BM25 排序。
用于 P1 多路召回：与向量检索结果融合去重。
"""
import math
from typing import List, Dict, Tuple
from pathlib import Path

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


class BM25Retriever:
    """
    BM25 稀疏检索器
    
    核心思路：
    1. 用 jieba 对文档和查询分词
    2. 用 TF-IDF 矩阵近似 BM25 评分
    3. 返回 Top-K 文档 ID
    
    注意：这不是严格 BM25，而是 TF-IDF 近似，
    但在中文场景下效果接近，且无需额外依赖。
    """
    
    # BM25 参数（标准值）
    K1 = 1.5   # 词频饱和参数
    B = 0.75   # 文档长度归一化参数
    
    def __init__(self):
        self.vectorizer = None
        self.tfidf_matrix = None
        self.doc_ids = []
        self.raw_texts = []
        self.tokenized_docs = []
        self._is_fitted = False
    
    def _tokenize(self, text: str) -> List[str]:
        """
        对文本进行分词，过滤标点符号和空格
        
        Args:
            text: 原始文本
            
        Returns:
            分词后的 token 列表
        """
        tokens = list(jieba.cut(text))
        # 过滤标点、空格、单字符（噪音大）
        filtered = []
        for t in tokens:
            stripped = t.strip()
            if stripped and len(stripped) > 1:
                filtered.append(stripped)
        return filtered
    
    def fit(self, documents: List[str], doc_ids: List[str] = None):
        """
        构建 BM25 索引
        
        Args:
            documents: 文档文本列表
            doc_ids: 文档 ID 列表（可选，默认用索引号）
        """
        if doc_ids is None:
            doc_ids = [str(i) for i in range(len(documents))]
        
        self.doc_ids = doc_ids
        self.raw_texts = documents
        
        # 分词（统一过滤逻辑）
        self.tokenized_docs = [self._tokenize(text) for text in documents]
        
        # 用空格连接成 TF-IDF 可处理的格式
        tokenized_strings = [' '.join(tokens) for tokens in self.tokenized_docs]
        
        # 构建 TF-IDF 矩阵
        # 注意：tokenizer 接收已分词的字符串，split 后就是 token 列表
        self.vectorizer = TfidfVectorizer(
            tokenizer=str.split,  # 按空格 split
            preprocessor=lambda x: x,  # 不做额外预处理
            token_pattern=None
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(tokenized_strings)
        self._is_fitted = True
    
    def _compute_bm25(self, query_tokens: List[str]) -> np.ndarray:
        """
        计算查询与所有文档的 BM25 分数
        
        使用 TF-IDF 矩阵近似：
        BM25(q, d) ≈ sum over q terms of: tfidf_score * log((N - df + 0.5) / (df + 0.5))
        """
        if not self._is_fitted:
            raise RuntimeError("请先调用 fit() 构建索引")
        
        N = len(self.raw_texts)  # 文档总数
        
        # 获取查询中每个词在 TF-IDF 矩阵中的列索引
        feature_names = self.vectorizer.get_feature_names_out()
        vocab = {word: idx for idx, word in enumerate(feature_names)}
        
        # 计算每个查询词的文档频率 (df)
        query_scores = np.zeros(N, dtype=np.float32)
        
        for token in query_tokens:
            if token not in vocab:
                continue
            
            col_idx = vocab[token]
            tf_col = self.tfidf_matrix[:, col_idx].toarray().flatten()
            
            # 文档频率：该词出现在多少篇文档中
            df = np.count_nonzero(tf_col)
            if df == 0:
                continue
            
            # BM25 风格加权
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1e-8)
            
            # 累加：term_freq * idf（简化版 BM25）
            # 实际 BM25: tf * (k1 + 1) / (tf + k1 * (1 - b + b * doclen / avgdl))
            doc_lens = np.array([len(t) for t in self.tokenized_docs], dtype=np.float32)
            avg_dl = np.mean(doc_lens) if doc_lens.size > 0 else 1.0
            
            # 文档长度归一化
            norm_factor = 1 - self.B + self.B * (doc_lens / avg_dl)
            numerator = tf_col * (self.K1 + 1)
            denominator = tf_col + self.K1 * norm_factor
            
            query_scores += idf * (numerator / (denominator + 1e-8))
        
        return query_scores
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        搜索文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            [(doc_id, score), ...] 按分数降序
        """
        query_tokens = list(jieba.cut(query))
        scores = self._compute_bm25(query_tokens)
        
        # 取 Top-K
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.doc_ids[idx], float(scores[idx])))
        
        return results
    
    def get_documents(self, doc_ids: List[str]) -> List[str]:
        """根据 doc_id 获取原始文本"""
        return [self.raw_texts[self.doc_ids.index(did)] for did in doc_ids if did in self.doc_ids]


# ==================== 便捷函数 ====================

def build_bm25_index_from_documents(documents: List[Dict]) -> BM25Retriever:
    """
    从 LangChain Document 列表构建 BM25 索引
    
    Args:
        documents: [{'id': str, 'text': str}, ...]
        
    Returns:
        拟合好的 BM25Retriever
    """
    texts = [doc['text'] for doc in documents]
    ids = [doc['id'] for doc in documents]
    
    retriever = BM25Retriever()
    retriever.fit(texts, ids)
    return retriever


if __name__ == "__main__":
    # 测试
    docs = [
        {"id": "doc1", "text": "元始仙尊是气道的开创者，他建立了天庭"},
        {"id": "doc2", "text": "星宿仙尊是智道的创始人，她的徒弟是童年星宿"},
        {"id": "doc3", "text": "巨阳仙尊开创了运道，拥有鸿运齐天仙蛊"},
        {"id": "doc4", "text": "幽魂魔尊是魂道的巅峰强者，死后仍被天庭囚禁"},
        {"id": "doc5", "text": "盗天魔尊寻找空门想要回家，掌握空间之道"},
    ]
    
    retriever = build_bm25_index_from_documents(docs)
    
    # 搜索
    query = "元始仙尊 气道"
    results = retriever.search(query, top_k=3)
    
    print(f"Query: {query}")
    for doc_id, score in results:
        text = next(d['text'] for d in docs if d['id'] == doc_id)
        print(f"  [{score:.4f}] {doc_id}: {text[:30]}...")
    
    # 跨领域搜索（应该召回较低）
    query2 = "元始仙尊 运道"
    results2 = retriever.search(query2, top_k=3)
    print(f"\nQuery: {query2}")
    for doc_id, score in results2:
        text = next(d['text'] for d in docs if d['id'] == doc_id)
        print(f"  [{score:.4f}] {doc_id}: {text[:30]}...")
