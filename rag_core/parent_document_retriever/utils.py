"""
递归父子文本分割器

支持多级父子关系（章→节→段）
"""

from pathlib import Path
from typing import List, Dict, Optional
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from rag_config import logger

logger = logging.getLogger(__name__)


class RecursiveParentTextSplitter:
    """递归父子文本分割器"""

    def __init__(
        self,
        parent_chunk_size: int = 2000,
        child_chunk_size: int = 500,
        parent_overlap: int = 100,
        child_overlap: int = 50
    ):
        """
        初始化分割器

        Args:
            parent_chunk_size: 父块大小（字符数）
            child_chunk_size: 子块大小（字符数）
            parent_overlap: 父块重叠字符数
            child_overlap: 子块重叠字符数
        """
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.parent_overlap = parent_overlap
        self.child_overlap = child_overlap

        # 子块分割器（使用 RecursiveCharacterTextSplitter）
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_overlap,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "],
            length_function=len
        )

    def split_text(self, text: str, parent_id: Optional[str] = None) -> List[Dict]:
        """
        递归分割文本

        Args:
            text: 要分割的文本
            parent_id: 父块 ID（用于关联）

        Returns:
            分割后的块列表，每个块是字典格式：
            {
                "chunk_id": str,
                "content": str,
                "parent_id": str,
                "source": str,
                "page_number": str,
                "metadata": dict
            }
        """
        # 先分割成父块
        parent_chunks = self._split_parents(text, parent_id)

        # 对每个父块，继续分割成子块
        all_chunks = []
        for parent_chunk in parent_chunks:
            child_chunks = self._split_children(parent_chunk['content'], parent_chunk['chunk_id'])
            all_chunks.extend(child_chunks)

        return all_chunks

    def _split_parents(self, text: str, parent_id: Optional[str] = None) -> List[Dict]:
        """
        分割父块（按章节标题）

        Args:
            text: 要分割的文本
            parent_id: 父块 ID

        Returns:
            父块列表，每个父块是字典格式：
            {
                "chunk_id": str,
                "content": str,
                "parent_id": str
            }
        """
        # 简化实现：按章节标题分割
        # 实际场景中，章节标题可能是 "第1章"、"## 章节" 等
        # 这里使用简单的正则匹配章节标题

        import re

        # 匹配常见章节标题格式
        chapter_pattern = re.compile(r'^(第[一二三四五六七八九十百千0-9]+章|##\s+[^\n]+|\d+\.\s+[^\n]+)', re.MULTILINE)

        # 找到所有章节位置
        matches = list(chapter_pattern.finditer(text))

        if not matches:
            # 没有章节标题，整个文本作为父块
            chunk_id = self._generate_chunk_id(parent_id, 0)
            return [{
                "chunk_id": chunk_id,
                "content": text,
                "parent_id": parent_id
            }]

        # 分割成父块
        parent_chunks = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            content = text[start:end].strip()

            # 限制父块大小
            if len(content) > self.parent_chunk_size:
                # 超过大小，强制分割
                for j in range(0, len(content), self.parent_chunk_size - self.parent_overlap):
                    chunk_id = self._generate_chunk_id(parent_id, i, j)
                    parent_chunks.append({
                        "chunk_id": chunk_id,
                        "content": content[j:j + self.parent_chunk_size].strip(),
                        "parent_id": parent_id
                    })
            else:
                chunk_id = self._generate_chunk_id(parent_id, i)
                parent_chunks.append({
                    "chunk_id": chunk_id,
                    "content": content,
                    "parent_id": parent_id
                })

        return parent_chunks

    def _split_children(self, content: str, parent_id: str) -> List[Dict]:
        """
        分割子块（使用 RecursiveCharacterTextSplitter）

        Args:
            content: 父块内容
            parent_id: 父块 ID

        Returns:
            子块列表
        """
        child_docs = self.child_splitter.create_documents([content])

        child_chunks = []
        for i, doc in enumerate(child_docs):
            chunk_id = self._generate_chunk_id(parent_id, child_index=i)

            # 从 metadata 中提取 source 和 page_number
            metadata = doc.metadata
            source = metadata.get('source', '')
            page_number = metadata.get('page_number', '')

            child_chunks.append({
                "chunk_id": chunk_id,
                "content": doc.page_content,
                "parent_id": parent_id,
                "source": source,
                "page_number": page_number,
                "metadata": metadata
            })

        return child_chunks

    def _generate_chunk_id(self, parent_id: Optional[str], index: int, sub_index: int = 0) -> str:
        """
        生成 chunk_id

        Args:
            parent_id: 父块 ID
            index: 块索引
            sub_index: 子块索引

        Returns:
            chunk_id
        """
        import hashlib

        if parent_id:
            # 父子关系
            return f"{parent_id}_{index}_{sub_index}"
        else:
            # 独立块
            return f"doc_{hashlib.md5(f'{index}_{sub_index}'.encode()).hexdigest()[:12]}"
