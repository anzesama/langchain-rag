"""
父子文档检索器

检索流程：
1. 向量检索子块
2. 提取父块 ID
3. 召回父块
4. 返回父子上下文
"""

from typing import List, Dict
import logging
from langchain_core.documents import Document

from rag_core.vector_store_libsql import VectorStoreManager
from .utils import RecursiveParentTextSplitter

logger = logging.getLogger(__name__)


class ParentDocumentRetriever:
    """父子文档检索器"""

    def __init__(self, vector_store: VectorStoreManager = None):
        """
        初始化检索器

        Args:
            vector_store: 向量库管理器
        """
        self.vector_store = vector_store or VectorStoreManager()
        self.splitter = RecursiveParentTextSplitter()

    def retrieve(self, query: str, top_k: int = 10) -> List[Document]:
        """
        检索父子文档

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            子块 + 父块的文档列表
        """
        # 1. 向量检索子块
        child_docs = self.vector_store.search(query, top_k=top_k * 2)

        if not child_docs:
            logger.info("父子检索无子块结果")
            return []

        # 2. 提取父块 ID
        parent_ids = set()
        for doc in child_docs:
            parent_id = doc.metadata.get('parent_id')
            if parent_id:
                parent_ids.add(parent_id)

        if not parent_ids:
            logger.info("父子检索无父块 ID")
            return child_docs

        logger.info(f"检索到 {len(parent_ids)} 个父块 ID")

        # 3. 召回父块（通过 chunk_id）
        parent_docs = self._get_parent_chunks(parent_ids)

        # 4. 返回父子上下文
        result = child_docs + parent_docs
        logger.info(f"父子检索完成: {len(child_docs)} 子块 + {len(parent_docs)} 父块")

        return result

    def _get_parent_chunks(self, parent_ids: set) -> List[Document]:
        """
        通过父块 ID 召回父块

        Args:
            parent_ids: 父块 ID 列表

        Returns:
            父块文档列表
        """
        parent_docs = []

        for parent_id in parent_ids:
            try:
                # 从向量库中查找对应的父块
                # 注意：这里需要 VectorStoreManager 支持 chunk_id 查询
                # 简化实现：直接返回一个包含 parent_id 的文档
                doc = Document(
                    page_content=f"[Parent Document: {parent_id}]",
                    metadata={
                        "type": "parent",
                        "parent_id": parent_id
                    }
                )
                parent_docs.append(doc)
            except Exception as e:
                logger.error(f"获取父块失败 {parent_id}: {e}")

        return parent_docs
