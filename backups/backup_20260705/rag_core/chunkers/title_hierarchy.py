"""
基于标题层级的文档切分器

功能：
- 解析 Markdown 文档的标题层级（H1, H2, H3）
- 根据标题边界切分文档，而非固定长度
- 保留标题层级信息作为元数据
"""

import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from langchain_core.documents import Document


@dataclass
class Heading:
    """标题信息"""
    level: int  # 1-6
    text: str
    start_pos: int
    end_pos: int


@dataclass
class Chunk:
    """切分后的块"""
    content: str
    metadata: Dict


class TitleHierarchyChunker:
    """基于标题层级的文档切分器"""

    def __init__(self, max_chunk_size: int = 500):
        """
        初始化切分器

        Args:
            max_chunk_size: 每个 chunk 的最大字符数（仅当标题不完整时使用）
        """
        self.max_chunk_size = max_chunk_size

    def split_by_headings(self, markdown_text: str) -> List[Document]:
        """
        基于标题层级切分 Markdown 文档

        Args:
            markdown_text: Markdown 格式的文本

        Returns:
            切分后的 Document 列表
        """
        if not markdown_text or not markdown_text.strip():
            return []

        # 1. 解析所有标题
        headings = self._parse_headings(markdown_text)

        if not headings:
            # 没有标题，按固定长度切分
            return self._split_by_size(markdown_text)

        # 2. 按标题边界切分
        chunks = self._create_chunks(headings, markdown_text)

        # 3. 转换为 LangChain Document
        documents = self._to_documents(chunks)

        return documents

    def _parse_headings(self, text: str) -> List[Heading]:
        """
        解析文本中的所有标题

        Args:
            text: Markdown 文本

        Returns:
            标题列表，按出现顺序排序
        """
        headings = []

        # 匹配 # 标题 到 ###### 标题
        pattern = r'^(#{1,6})\s+(.+)$'
        matches = list(re.finditer(pattern, text, re.MULTILINE))

        for match in matches:
            level = len(match.group(1))
            text_content = match.group(2).strip()
            start_pos = match.start()
            end_pos = match.end()

            headings.append(Heading(
                level=level,
                text=text_content,
                start_pos=start_pos,
                end_pos=end_pos
            ))

        return headings

    def _create_chunks(self, headings: List[Heading], text: str) -> List[Chunk]:
        """
        根据标题边界创建 chunk

        Args:
            headings: 标题列表
            text: 原始文本

        Returns:
            Chunk 列表
        """
        chunks = []
        prev_heading = None

        # 添加开头内容（H1 之前）
        if headings:
            first_heading = headings[0]
            content = text[:first_heading.start_pos].strip()
            if content:
                chunks.append(Chunk(
                    content=content,
                    metadata={
                        'heading_path': [],
                        'level': 0
                    }
                ))

        # 按标题边界切分
        for i, heading in enumerate(headings):
            # 确定内容的起始位置
            start_pos = heading.start_pos

            # 确定内容的结束位置（下一个标题的开始，或文本末尾）
            if i < len(headings) - 1:
                end_pos = headings[i + 1].start_pos
            else:
                end_pos = len(text)

            # 提取内容
            content = text[start_pos:end_pos].strip()

            # 如果内容为空，跳过
            if not content:
                continue

            # 获取标题路径（用于元数据）
            heading_path = self._get_heading_path(headings[:i + 1])

            chunks.append(Chunk(
                content=content,
                metadata={
                    'heading_path': heading_path,
                    'heading_text': heading.text,
                    'heading_level': heading.level,
                    'level': heading.level
                }
            ))

        # 添加结尾内容（最后一个标题之后）
        if headings:
            last_heading = headings[-1]
            content = text[last_heading.end_pos:].strip()
            if content:
                heading_path = self._get_heading_path(headings)
                chunks.append(Chunk(
                    content=content,
                    metadata={
                        'heading_path': heading_path,
                        'heading_text': last_heading.text,
                        'heading_level': last_heading.level,
                        'level': last_heading.level
                    }
                ))

        return chunks

    def _get_heading_path(self, headings: List[Heading]) -> List[str]:
        """
        获取标题路径（用于元数据）

        Args:
            headings: 标题列表

        Returns:
            标题路径（如 ["标题1", "标题2"]）
        """
        path = []
        for heading in headings:
            if heading.text:
                path.append(heading.text)
        return path

    def _split_by_size(self, text: str) -> List[Document]:
        """
        按固定大小切分（无标题时使用）

        Args:
            text: 原始文本

        Returns:
            Document 列表
        """
        documents = []
        words = text.split()

        for i in range(0, len(words), self.max_chunk_size):
            chunk_text = ' '.join(words[i:i + self.max_chunk_size])
            documents.append(Document(
                page_content=chunk_text,
                metadata={
                    'heading_path': [],
                    'level': 0
                }
            ))

        return documents

    def _to_documents(self, chunks: List[Chunk]) -> List[Document]:
        """
        将 Chunk 转换为 LangChain Document

        Args:
            chunks: Chunk 列表

        Returns:
            Document 列表
        """
        documents = []
        for chunk in chunks:
            documents.append(Document(
                page_content=chunk.content,
                metadata=chunk.metadata
            ))
        return documents


# 测试代码
if __name__ == '__main__':
    test_markdown = """# 一级标题

这是 H1 下的内容。

## 二级标题

这是 H2 下的内容。

### 三级标题

这是 H3 下的内容。

## 另一个 H2 标题

这是另一个 H2 标题下的内容。

### 三级标题 2

这是 H3 下的内容。

# 另一个 H1 标题

这是另一个 H1 标题下的内容。
"""

    chunker = TitleHierarchyChunker(max_chunk_size=500)
    documents = chunker.split_by_headings(test_markdown)

    print(f"切分结果：{len(documents)} 个文档\n")
    for i, doc in enumerate(documents):
        print(f"--- 文档 {i + 1} ---")
        print(f"标题路径: {doc.metadata.get('heading_path', [])}")
        print(f"标题级别: {doc.metadata.get('level', 0)}")
        print(f"内容: {doc.page_content[:100]}...")
        print()
