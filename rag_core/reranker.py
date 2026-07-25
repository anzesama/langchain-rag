"""
CrossEncoder 重排器 — P0 检索后精排

使用本地 bert-base-chinese 做序列分类，对候选文档进行语义重排。
不依赖外部 API，离线可用。
"""
import math
from typing import List, Tuple, Dict

import numpy as np

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None


class CrossEncoderReranker:
    """
    CrossEncoder 重排器
    
    核心思路：
    1. 从向量检索获取 Top-N 候选（N 通常 20-50）
    2. 用 CrossEncoder 对 (query, doc) 做逐对评分
    3. 按分数重排，取 Top-K
    
    优势：
    - 双塔模型只能做粗排（点积近似）
    - CrossEncoder 能看全文，语义理解更深
    - 效果提升显著，但计算开销更大
    
    注意：使用 bert-base-chinese 作为基座模型，
    该模型未针对排序任务微调，但比无重排好得多。
    """
    
    def __init__(self, model_name: str = 'bert-base-chinese', max_candidates: int = 50):
        """
        Args:
            model_name: CrossEncoder 模型名称
            max_candidates: 最多处理多少候选文档（节省推理时间）
        """
        self.model_name = model_name
        self.max_candidates = max_candidates
        
        if CrossEncoder is None:
            raise RuntimeError("sentence_transformers 未安装")
        
        # 加载本地缓存模型（如果网络不通会自动用缓存）
        try:
            self.model = CrossEncoder(model_name)
        except Exception as e:
            raise RuntimeError(f"加载 CrossEncoder 模型失败: {e}")
    
    def rerank(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        对文档列表进行重排
        
        Args:
            query: 查询文本
            documents: 待重排的文档文本列表（附带 id）
            top_k: 返回数量
            
        Returns:
            [(doc_id, rerank_score), ...] 按分数降序
        """
        if not documents:
            return []
        
        # 限制候选数量（节省推理时间）
        candidates = documents[:self.max_candidates]
        
        # 构建 (query, doc) 对
        pairs = [[query, doc['text']] for doc in candidates]
        
        # 批量预测
        scores = self.model.predict(pairs)
        
        # 转换为 (id, score) 并排序
        results = []
        for i, doc in enumerate(candidates):
            results.append((doc['id'], float(scores[i])))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
    
    def batch_rerank(
        self, 
        queries: List[str], 
        all_documents: Dict[str, List[Dict]],
        top_k_per_query: int = 5
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        批量重排多个查询
        
        Args:
            queries: 查询列表
            all_documents: {query_idx: [{'id': str, 'text': str}, ...]}
            top_k_per_query: 每个查询返回数量
            
        Returns:
            {query_idx: [(doc_id, score), ...]}
        """
        results = {}
        
        for idx, query in enumerate(queries):
            docs = all_documents.get(str(idx), [])
            if docs:
                results[idx] = self.rerank(query, docs, top_k=top_k_per_query)
            else:
                results[idx] = []
        
        return results


# ==================== 便捷函数 ====================

def create_reranker(model_name: str = 'bert-base-chinese') -> CrossEncoderReranker:
    """
    创建重排器实例
    
    Args:
        model_name: 模型名称
        
    Returns:
        CrossEncoderReranker 实例
    """
    return CrossEncoderReranker(model_name=model_name)


# ==================== 测试 ====================

if __name__ == "__main__":
    reranker = create_reranker()
    
    query = "元始仙尊的主修流派是什么"
    
    documents = [
        {'id': 'doc1', 'text': '元始仙尊是气道的开创者，他建立了天庭，主修气道'},
        {'id': 'doc2', 'text': '星宿仙尊是智道的创始人，她的徒弟是童年星宿'},
        {'id': 'doc3', 'text': '巨阳仙尊开创了运道，拥有鸿运齐天仙蛊'},
        {'id': 'doc4', 'text': '幽魂魔尊是魂道的巅峰强者，死后仍被天庭囚禁'},
        {'id': 'doc5', 'text': '盗天魔尊寻找空门想要回家，掌握空间之道'},
    ]
    
    print(f'Query: {query}')
    results = reranker.rerank(query, documents, top_k=3)
    for doc_id, score in results:
        text = next(d['text'] for d in documents if d['id'] == doc_id)
        print(f'  [{score:.4f}] {doc_id}: {text[:30]}...')
