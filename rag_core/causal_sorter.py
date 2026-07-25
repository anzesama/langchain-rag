"""
因果排序器 — 按 global_order 对文档进行因果排序

在 RAG 检索后，使用 global_order 元数据对候选文档进行排序，
确保返回的上下文按因果顺序排列，这对于理解"为什么"和"如何"
的问题非常重要。

技术特点：
- 按 metadata.global_order 排序
- 支持上下文窗口大小配置
- 支持扩展相邻 chunk（expand_neighbors）
- 保留原始文档对象（不修改 metadata）
"""

from typing import List, Optional, Dict
import logging
from langchain_core.documents import Document

from rag_config import logger

logger = logging.getLogger("rag.causal_sorter")


class CausalSorter:
    """
    因果排序器

    核心功能：
    - 按 global_order 对 Document 列表排序
    - 支持上下文窗口大小配置
    - 支持扩展相邻 chunk

    使用示例：
        >>> sorter = CausalSorter(context_window=10, expand_neighbors=2)
        >>> docs = [
        ...     Document(page_content="...", metadata={"global_order": 1}),
        ...     Document(page_content="...", metadata={"global_order": 5}),
        ...     Document(page_content="...", metadata={"global_order": 3}),
        ... ]
        >>> sorted_docs = sorter.sort(docs)
        >>> print(sorted_docs[0].metadata["global_order"])  # 1
    """

    def __init__(
        self,
        context_window: int = 10,
        expand_neighbors: int = 2,
    ):
        """
        初始化因果排序器

        Args:
            context_window: 上下文窗口大小（返回前 N 个 chunk）
            expand_neighbors: 是否扩展相邻 chunk（默认 2）
        """
        self.context_window = context_window
        self.expand_neighbors = expand_neighbors

    def sort(self, documents: List[Document]) -> List[Document]:
        """
        按 global_order 对文档列表排序

        Args:
            documents: 待排序的文档列表

        Returns:
            排序后的文档列表
        """
        if not documents:
            return []

        # 按全局顺序排序
        sorted_docs = sorted(
            documents,
            key=lambda d: d.metadata.get("global_order", 0)
        )

        logger.debug(f"因果排序完成: {len(sorted_docs)} 个文档，"
                    f"global_order 范围 [{sorted_docs[0].metadata.get('global_order', 0)} - "
                    f"{sorted_docs[-1].metadata.get('global_order', 0)}]")

        return sorted_docs

    def get_context(
        self,
        documents: List[Document],
        context_window: Optional[int] = None,
    ) -> List[Document]:
        """
        获取排序后的上下文文档

        Args:
            documents: 候选文档列表
            context_window: 上下文窗口大小（None 使用默认值）

        Returns:
            上下文文档列表
        """
        if context_window is None:
            context_window = self.context_window

        # 排序
        sorted_docs = self.sort(documents)

        # 截取上下文窗口
        context_docs = sorted_docs[:context_window]

        return context_docs

    def get_expanded_context(
        self,
        documents: List[Document],
        context_window: Optional[int] = None,
        expand_neighbors: Optional[int] = None,
    ) -> List[Document]:
        """
        获取扩展后的上下文文档（包含相邻 chunk）

        Args:
            documents: 候选文档列表
            context_window: 上下文窗口大小（None 使用默认值）
            expand_neighbors: 扩展相邻 chunk 的数量（None 使用默认值）

        Returns:
            扩展后的上下文文档列表
        """
        if context_window is None:
            context_window = self.context_window
        if expand_neighbors is None:
            expand_neighbors = self.expand_neighbors

        # 排序
        sorted_docs = self.sort(documents)

        if not sorted_docs:
            return []

        # 获取中心 chunk（当前窗口的第一个）
        center_order = sorted_docs[0].metadata.get("global_order", 0)

        # 计算扩展范围
        start_order = max(0, center_order - expand_neighbors)
        end_order = center_order + context_window + expand_neighbors - 1

        # 筛选在范围内的文档
        expanded_docs = [
            doc for doc in sorted_docs
            if start_order <= doc.metadata.get("global_order", 0) <= end_order
        ]

        logger.debug(f"扩展上下文完成: 中心 order={center_order}, "
                    f"窗口={context_window}, 扩展={expand_neighbors}, "
                    f"结果={len(expanded_docs)} 个文档")

        return expanded_docs

    def get_range(
        self,
        documents: List[Document],
        start_order: int,
        end_order: int,
    ) -> List[Document]:
        """
        获取指定 global_order 范围内的文档

        Args:
            documents: 候选文档列表
            start_order: 起始 order（包含）
            end_order: 结束 order（包含）

        Returns:
            范围内的文档列表
        """
        if not documents:
            return []

        # 排序
        sorted_docs = self.sort(documents)

        # 筛选
        range_docs = [
            doc for doc in sorted_docs
            if start_order <= doc.metadata.get("global_order", 0) <= end_order
        ]

        return range_docs

    def get_document_count(self, documents: List[Document]) -> Dict[str, int]:
        """
        统计文档的 global_order 分布

        Args:
            documents: 文档列表

        Returns:
            统计信息字典
        """
        if not documents:
            return {"count": 0, "min_order": 0, "max_order": 0, "range": 0}

        orders = [doc.metadata.get("global_order", 0) for doc in documents]
        return {
            "count": len(documents),
            "min_order": min(orders),
            "max_order": max(orders),
            "range": max(orders) - min(orders) + 1,
        }


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    # 创建测试数据
    docs = [
        Document(
            page_content=f"这是文档 {i}",
            metadata={"source": f"doc_{i}.txt", "global_order": i}
        )
        for i in range(1, 11)
    ]

    print("=" * 60)
    print("因果排序器测试")
    print("=" * 60)

    # 创建排序器
    sorter = CausalSorter(context_window=5, expand_neighbors=2)

    # 测试排序
    print("\n测试排序...")
    unsorted_docs = docs[::2]  # 打乱顺序
    print(f"排序前: {[d.metadata['global_order'] for d in unsorted_docs]}")

    sorted_docs = sorter.sort(unsorted_docs)
    print(f"排序后: {[d.metadata['global_order'] for d in sorted_docs]}")

    # 测试上下文窗口
    print("\n测试上下文窗口...")
    context = sorter.get_context(sorted_docs, context_window=3)
    print(f"上下文窗口 (3): {[d.metadata['global_order'] for d in context]}")

    # 测试扩展上下文
    print("\n测试扩展上下文...")
    expanded = sorter.get_expanded_context(sorted_docs, context_window=3, expand_neighbors=2)
    print(f"扩展上下文: {[d.metadata['global_order'] for d in expanded]}")

    # 测试范围查询
    print("\n测试范围查询...")
    range_docs = sorter.get_range(sorted_docs, start_order=3, end_order=7)
    print(f"范围 [3, 7]: {[d.metadata['global_order'] for d in range_docs]}")

    # 测试统计信息
    print("\n测试统计信息...")
    stats = sorter.get_document_count(sorted_docs)
    print(f"统计: {stats}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
