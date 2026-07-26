"""
混合检索路由 — 自动判断走「普通模式」还是「父子模式」

核心设计：
1. 文档属性判断：小说/长文本 → 父子模式，技术文档/短文本 → 普通模式
2. 查询意图判断：因果/背景/人物关系 → 父子模式，关键词/事实 → 普通模式
3. 两者结合，取最优路径

路由策略：
- 如果文档是小说类（guzhenren.txt），默认走父子模式
- 如果查询包含"为什么""背景""关系""经过"等意图词，走父子模式
- 否则走普通模式
"""
import re
from typing import List, Tuple, Dict, Optional
from pathlib import Path

from langchain_core.documents import Document

from rag_config import logger
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.parent_document_retriever import ParentDocumentRetriever


# ==================== 文档类型判断 ====================

# 小说类文件（适合父子模式）
NOVEL_FILES = {
    "guzhenren.txt",
    "蛊真人.txt",
}

# 短文本文件（适合普通模式）
SHORT_TEXT_FILES = {
    ".md", ".json", ".csv", ".txt",
}

# 长文档文件（适合父子模式）
LONG_DOC_FILES = {
    ".pdf", ".docx",
}


def classify_document(source: str) -> str:
    """
    根据文档来源分类
    
    Returns:
        "novel" | "long_doc" | "short_doc"
    """
    filename = Path(source).name
    
    if filename in NOVEL_FILES:
        return "novel"
    
    ext = Path(source).suffix.lower()
    if ext in LONG_DOC_FILES:
        return "long_doc"
    
    return "short_doc"


# ==================== 查询意图判断 ====================

# 父子模式意图关键词（需要上下文理解）
PARENT_INTENT_KEYWORDS = [
    r"为什么.*",       # 因果
    r"什么.*背景",     # 背景
    r".*关系",         # 关系
    r"怎么.*",         # 过程
    r"经过.*",         # 经历
    r"起因.*",         # 起因
    r"结局.*",         # 结局
    r"动机.*",         # 动机
    r"心理.*",         # 心理
    r"性格.*",         # 性格
    r"人物.*",         # 人物分析
    r"背叛.*",         # 复杂情节
    r"阴谋.*",         # 复杂情节
    r"布局.*",         # 复杂情节
    r"战略.*",         # 战略分析
    r"战术.*",         # 战术分析
    r"目标.*",         # 目标分析
    r"目的.*",         # 目的分析
    r"计划.*",         # 计划分析
]

# 普通模式意图关键词（关键词匹配即可）
CHILD_INTENT_KEYWORDS = [
    r".*[0-9]+.*",     # 包含数字
    r".*[A-Z]+.*",     # 包含英文
    r".*代码.*",       # 技术问题
    r".*配置.*",       # 配置问题
    r".*安装.*",       # 安装问题
    r".*错误.*",       # 错误信息
    r".*报错.*",       # 报错信息
]


def analyze_query_intent(query: str) -> str:
    """
    分析查询意图
    
    Returns:
        "parent" | "child" | "neutral"
    """
    # 检查父子模式意图
    for pattern in PARENT_INTENT_KEYWORDS:
        if re.search(pattern, query):
            return "parent"
    
    # 检查普通模式意图
    for pattern in CHILD_INTENT_KEYWORDS:
        if re.search(pattern, query):
            return "child"
    
    return "neutral"


# ==================== 混合路由 ====================

class HybridRouter:
    """
    混合检索路由器
    
    决策逻辑：
    1. 文档类型 + 查询意图 → 决定走哪个模式
    2. 默认 fallback 到普通模式（更快）
    """
    
    def __init__(self, vector_store: VectorStoreManager = None):
        self.vector_store = vector_store or VectorStoreManager()
        self._parent_retriever: Optional[ParentDocumentRetriever] = None
    
    def route(self, query: str, source: str = None) -> str:
        """
        路由决策
        
        Args:
            query: 用户查询
            source: 文档来源（可选）
            
        Returns:
            "parent" | "child"
        """
        # 1. 如果没有 source，默认使用普通模式（更快）
        if source is None:
            return "child"
        
        # 2. 文档类型判断
        doc_type = classify_document(source)
        
        # 3. 查询意图判断
        intent = analyze_query_intent(query)
        
        # 4. 决策逻辑
        # 小说 + 复杂意图 → 父子模式
        if doc_type == "novel" and intent in ("parent", "neutral"):
            return "parent"
        
        # 小说 + 简单意图 → 普通模式（更快）
        if doc_type == "novel" and intent == "child":
            return "child"
        
        # 长文档 + 复杂意图 → 父子模式
        if doc_type == "long_doc" and intent == "parent":
            return "parent"
        
        # 短文档 → 普通模式
        if doc_type == "short_doc":
            return "child"
        
        # 默认 → 普通模式（更快）
        return "child"
    
    def search(self, query: str, top_k: int = 5, source: str = None) -> List[Tuple[Document, float]]:
        """
        根据路由结果执行搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            source: 文档来源
            
        Returns:
            (文档, 距离) 列表
        """
        mode = self.route(query, source)
        logger.info(f"路由决策: query='{query[:30]}...', mode={mode}, source={source}")
        
        if mode == "parent":
            return self._search_parent(query, top_k)
        else:
            return self._search_child(query, top_k)
    
    def _search_child(self, query: str, top_k: int) -> List[Tuple[Document, float]]:
        """普通模式：直接搜索 chunk"""
        return self.vector_store.search(query, top_k=top_k)
    
    def _search_parent(self, query: str, top_k: int) -> List[Tuple[Document, float]]:
        """父子模式：搜索子块，返回父块"""
        try:
            from rag_core.parent_document_retriever import VectorStoreWithParentRetriever
            
            # 创建 parent retriever
            parent_vs = VectorStoreWithParentRetriever(
                persist_dir=self.vector_store.persist_dir,
                embedding_model="BAAI/bge-small-zh-v1.5",
                embedding_device="cpu"
            )
            
            # 执行父子模式检索
            parent_docs = parent_vs.search_parent_mode(query, top_k)
            
            # 转换为 (Document, float) 格式
            return [(doc, 0.0) for doc in parent_docs]
            
        except Exception as e:
            logger.warning(f"父子模式检索失败，降级到普通模式: {e}")
            return self._search_child(query, top_k)


# ==================== 便捷函数 ====================

def hybrid_search(query: str, top_k: int = 5, source: str = None) -> List[Tuple[Document, float]]:
    """
    混合检索便捷函数
    
    Args:
        query: 查询文本
        top_k: 返回数量
        source: 文档来源
        
    Returns:
        (文档, 距离) 列表
    """
    router = HybridRouter()
    return router.search(query, top_k, source)
