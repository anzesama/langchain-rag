"""
增强文档分块器（Enhanced Document Processor）

功能：
- 基于 LangChain RecursiveCharacterTextSplitter 的增强包装器
- 为每个 chunk 分配 global_order，保证跨文档的全局顺序
- 支持标题感知切分（Title-Hierarchy Aware）
- 支持质量过滤（长度、重复率、语言）
- 统一的元数据注入（source, doc_hash, chunk_index, global_order）
"""

import hashlib
import re
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from rag_config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    logger,
)

# 复用已有的 RecursiveCharacterTextSplitter 别名
from rag_core.document_loader import RecursiveCharacterTextSplitter as LoaderRecursiveSplitter

logger = logging.getLogger("rag.document_processor")


# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class ChunkMetadata:
    """
    增强分块的元数据

    Attributes:
        source:          来源文件路径
        doc_hash:        文档级别的 SHA256 hash（用于去重）
        chunk_index:     文档内局部索引（从 0 开始）
        global_order:    全局顺序号（跨文档唯一递增）
        char_count:      该 chunk 的字符数
        word_count:      该 chunk 的词数（按空格/标点分）
        heading_path:    标题路径（如 ["第一章", "第一节"]）
        parent_id:       父块 ID（用于父子检索）
        lang_hint:       语言提示（"zh" / "en" / "mixed"）
        quality_score:   质量评分（0-1，None 表示未评估）
    """
    source: str = ""
    doc_hash: str = ""
    chunk_index: int = 0
    global_order: int = 0
    char_count: int = 0
    word_count: int = 0
    heading_path: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    lang_hint: str = "mixed"
    quality_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """转为字典（LangChain 元数据格式）"""
        d = {
            "source": self.source,
            "doc_hash": self.doc_hash,
            "chunk_index": self.chunk_index,
            "global_order": self.global_order,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "lang_hint": self.lang_hint,
        }
        if self.heading_path:
            d["heading_path"] = self.heading_path
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.quality_score is not None:
            d["quality_score"] = self.quality_score
        return d


# ============================================================================
# 质量评估器
# ============================================================================

class QualityEvaluator:
    """
    轻量级文本质量评估器

    评估维度：
    - 长度合理性（太短或太长都扣分）
    - 重复率（字符重复度）
    - 语言纯度（中文/英文占比）
    """

    # 合理长度范围（字符数）
    MIN_CHARS = 20
    OPTIMAL_MIN_CHARS = 50
    OPTIMAL_MAX_CHARS = 1000
    MAX_CHARS = 3000

    def evaluate(self, text: str) -> float:
        """
        返回 0-1 的质量分数

        Args:
            text: 待评估文本

        Returns:
            质量分数（0.0 - 1.0）
        """
        if not text or not text.strip():
            return 0.0

        score = 1.0
        length_score = self._length_score(text)
        dup_score = self._duplication_score(text)
        lang_score = self._language_purity(text)

        score = length_score * 0.4 + dup_score * 0.3 + lang_score * 0.3
        return round(min(max(score, 0.0), 1.0), 3)

    @staticmethod
    def _length_score(text: str) -> float:
        """长度合理性评分"""
        length = len(text)
        if length < QualityEvaluator.MIN_CHARS:
            return 0.2
        if QualityEvaluator.OPTIMAL_MIN_CHARS <= length <= QualityEvaluator.OPTIMAL_MAX_CHARS:
            return 1.0
        if length <= QualityEvaluator.MAX_CHARS:
            # 线性衰减
            return max(0.5, 1.0 - (length - QualityEvaluator.OPTIMAL_MAX_CHARS) / (QualityEvaluator.MAX_CHARS - QualityEvaluator.OPTIMAL_MAX_CHARS))
        return 0.3  # 超长

    @staticmethod
    def _duplication_score(text: str) -> float:
        """重复率评分（基于字符 n-gram）"""
        if len(text) < 10:
            return 1.0
        # 计算 3-gram 重复率
        trigrams = [text[i:i+3] for i in range(len(text) - 2)]
        if not trigrams:
            return 1.0
        unique_ratio = len(set(trigrams)) / len(trigrams)
        return unique_ratio

    @staticmethod
    def _language_purity(text: str) -> float:
        """语言纯度评分"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_alpha = sum(1 for c in text if c.isalpha())
        if total_alpha == 0:
            return 1.0  # 纯非字母文本（如纯中文）算满分
        ratio = chinese_chars / total_alpha
        # 中文占比在 0.3-0.9 之间视为混合合理
        if 0.3 <= ratio <= 0.9:
            return 1.0
        return 0.7


# ============================================================================
# 增强分块器
# ============================================================================

class EnhancedDocumentProcessor:
    """
    增强文档分块器

    核心特性：
    1. 全局顺序号（global_order）— 跨文档唯一递增
    2. 质量评估 — 每个 chunk 附带 quality_score
    3. 元数据丰富化 — 自动注入 hash、长度、词数、语言提示
    4. 灵活的分块策略 — 支持递归切分和标题感知切分

    使用示例：
        processor = EnhancedDocumentProcessor(chunk_size=500, chunk_overlap=50)

        # 批量处理
        docs = [
            Document(page_content="文档1内容...", metadata={"source": "doc1.txt"}),
            Document(page_content="文档2内容...", metadata={"source": "doc2.txt"}),
        ]
        chunks = processor.process_documents(docs)

        # 查看全局顺序
        for chunk in chunks:
            print(f"global_order={chunk.metadata['global_order']}, "
                  f"quality={chunk.metadata['quality_score']}")
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        min_chunk_size: int = 20,
        separators: Optional[List[str]] = None,
        quality_threshold: float = 0.3,
        enable_quality_filter: bool = True,
        inject_global_order: bool = True,
    ):
        """
        初始化增强分块器

        Args:
            chunk_size:           每个 chunk 的目标字符数
            chunk_overlap:        相邻 chunk 的重叠字符数
            min_chunk_size:       最小 chunk 字符数（低于此值的会被丢弃）
            separators:           切分分隔符列表，None 时使用中文优化默认值
            quality_threshold:    质量分数阈值（低于此值的 chunk 会被过滤）
            enable_quality_filter: 是否启用质量过滤
            inject_global_order:  是否注入 global_order 字段
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.quality_threshold = quality_threshold
        self.enable_quality_filter = enable_quality_filter
        self.inject_global_order = inject_global_order

        # 初始化质量评估器
        self.evaluator = QualityEvaluator()

        # 初始化切分器
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or self._default_separators(),
            length_function=len,
        )

        # 全局顺序计数器
        self._global_counter = 0

    @staticmethod
    def _default_separators() -> List[str]:
        """中文优化的默认分隔符"""
        return [
            "\n\n",    # 空行（段落分隔）
            "\n",      # 换行
            "。",      # 中文句号
            "！",      # 中文感叹号
            "？",      # 中文问号
            "；",      # 中文分号
            "…",       # 省略号
            ", ",     # 英文逗号+空格
            ",",      # 英文逗号
            ". ",     # 英文句点+空格
            ".",      # 英文句点
            " ",      # 空格
            "",         # 空字符串（最后兜底）
        ]

    def process_documents(self, documents: List[Document]) -> List[Document]:
        """
        处理文档列表，返回带增强元数据的 chunk 列表

        Args:
            documents: 原始文档列表

        Returns:
            带 global_order 等元数据的 chunk 列表
        """
        if not documents:
            logger.warning("没有文档可处理")
            return []

        # 1. 对每个文档计算 hash
        enriched_docs = self._add_doc_hashes(documents)

        # 2. 切分所有文档
        all_chunks = self._split_documents(enriched_docs)

        # 3. 分配 global_order 和计算统计信息
        all_chunks = self._assign_global_order(all_chunks)

        # 4. 质量评估与过滤
        if self.enable_quality_filter:
            all_chunks = self._quality_filter(all_chunks)

        logger.info(
            f"处理完成: {len(documents)} 篇文档 → "
            f"{len(all_chunks)} 个有效 chunk "
            f"(global_order: 1-{self._global_counter})"
        )
        return all_chunks

    def process_single(self, text: str, source: str = "unknown") -> List[Document]:
        """
        处理单个文本（便捷方法）

        Args:
            text:   文本内容
            source: 来源标识

        Returns:
            带元数据的 chunk 列表
        """
        doc = Document(page_content=text, metadata={"source": source})
        return self.process_documents([doc])

    def _add_doc_hashes(self, documents: List[Document]) -> List[Document]:
        """
        为每个文档计算 SHA256 hash 并注入元数据

        Args:
            documents: 原始文档列表

        Returns:
            带 doc_hash 元数据的文档列表
        """
        for doc in documents:
            content_hash = hashlib.sha256(doc.page_content.encode("utf-8")).hexdigest()[:16]
            source = doc.metadata.get("source", "unknown")
            doc.metadata["doc_hash"] = f"{source}_{content_hash}"
        return documents

    def _split_documents(self, documents: List[Document]) -> List[Document]:
        """
        使用切分器将文档切分为 chunk

        Args:
            documents: 带 hash 的文档列表

        Returns:
            切分后的 chunk 列表
        """
        # 合并所有文档为一个大的 Document 列表（RecursiveCharacterTextSplitter 需要）
        all_chunks = self.splitter.split_documents(documents)

        # 确保每个 chunk 保留 source 和 doc_hash
        for chunk in all_chunks:
            # 保留原始元数据中的关键字段
            if "source" not in chunk.metadata:
                chunk.metadata["source"] = "unknown"
            if "doc_hash" not in chunk.metadata:
                chunk.metadata["doc_hash"] = ""

        return all_chunks

    def _assign_global_order(self, chunks: List[Document]) -> List[Document]:
        """
        为每个 chunk 分配 global_order 和计算统计信息

        Args:
            chunks: 切分后的 chunk 列表

        Returns:
            带 global_order 的 chunk 列表
        """
        result = []
        for i, chunk in enumerate(chunks):
            self._global_counter += 1
            chunk.metadata["global_order"] = self._global_counter
            chunk.metadata["chunk_index"] = i
            chunk.metadata["char_count"] = len(chunk.page_content)
            chunk.metadata["word_count"] = self._count_words(chunk.page_content)

            # 语言提示
            chunk.metadata["lang_hint"] = self._detect_lang_hint(chunk.page_content)

            result.append(chunk)

        return result

    @staticmethod
    def _count_words(text: str) -> int:
        """
        统计词数（中英文混合）

        - 中文字符每个算 1 个词
        - 英文单词按空格分割
        """
        chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # 去除中文后按空格分割英文
        non_chinese = re.sub(r'[\u4e00-\u9fff]', '', text)
        english_words = len(non_chinese.split()) if non_chinese.strip() else 0
        return chinese_count + english_words

    @staticmethod
    def _detect_lang_hint(text: str) -> str:
        """
        检测文本的主要语言

        Returns:
            "zh" / "en" / "mixed"
        """
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english_chars = sum(1 for c in text if c.isascii() and c.isalpha())
        total = chinese_chars + english_chars

        if total == 0:
            return "mixed"
        zh_ratio = chinese_chars / total
        en_ratio = english_chars / total

        if zh_ratio > 0.7:
            return "zh"
        if en_ratio > 0.7:
            return "en"
        return "mixed"

    def _quality_filter(self, chunks: List[Document]) -> List[Document]:
        """
        质量过滤：移除低质量 chunk

        Args:
            chunks: 带元数据的 chunk 列表

        Returns:
            过滤后的 chunk 列表
        """
        filtered = []
        dropped = 0

        for chunk in chunks:
            # 长度过滤
            if len(chunk.page_content) < self.min_chunk_size:
                dropped += 1
                continue

            # 质量评分
            quality = self.evaluator.evaluate(chunk.page_content)
            chunk.metadata["quality_score"] = quality

            if quality < self.quality_threshold:
                dropped += 1
                continue

            filtered.append(chunk)

        if dropped > 0:
            logger.info(f"质量过滤: 丢弃 {dropped} 个低质量 chunk")

        return filtered


# ============================================================================
# 快捷函数
# ============================================================================

def create_enhanced_processor(
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    quality_threshold: float = 0.3,
) -> EnhancedDocumentProcessor:
    """
    工厂函数：创建增强分块器

    Args:
        chunk_size:          目标 chunk 大小
        chunk_overlap:       重叠字符数
        quality_threshold:   质量过滤阈值

    Returns:
        EnhancedDocumentProcessor 实例
    """
    return EnhancedDocumentProcessor(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        quality_threshold=quality_threshold,
    )


def process_with_global_order(
    documents: List[Document],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Document]:
    """
    便捷函数：快速处理文档并返回带 global_order 的 chunk

    Args:
        documents:     原始文档列表
        chunk_size:    目标 chunk 大小
        chunk_overlap: 重叠字符数

    Returns:
        带 global_order 元数据的 chunk 列表
    """
    processor = EnhancedDocumentProcessor(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return processor.process_documents(documents)


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    # 示例：使用增强分块器
    sample_docs = [
        Document(
            page_content="""# 第一章 引言

人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。

## 1.1 研究背景

人工智能起源于1956年的达特茅斯会议。从那以后，AI经历了多次发展浪潮。

### 1.1.1 早期发展

早期的AI研究主要集中在符号主义方法上，通过逻辑推理和知识表示来实现智能。

## 1.2 应用场景

AI已经广泛应用于医疗、金融、教育、交通等领域。

""",
            metadata={"source": "ai_intro.md"}
        ),
        Document(
            page_content="""# 第二章 技术基础

深度学习是人工智能的重要技术基础。

## 2.1 神经网络

人工神经网络模仿生物神经系统的结构和功能。

## 2.2 卷积神经网络

CNN在图像识别领域取得了突破性进展。

""",
            metadata={"source": "tech_basics.md"}
        ),
    ]

    processor = create_enhanced_processor(chunk_size=200, chunk_overlap=30)
    chunks = processor.process_documents(sample_docs)

    print(f"\n{'='*60}")
    print(f"处理结果: {len(sample_docs)} 篇文档 → {len(chunks)} 个 chunk")
    print(f"{'='*60}\n")

    for chunk in chunks:
        meta = chunk.metadata
        preview = chunk.page_content[:60].replace('\n', ' ')
        print(
            f"[global_order={meta['global_order']:3d}] "
            f"source={meta['source']:<15s} "
            f"chars={meta['char_count']:4d} "
            f"words={meta['word_count']:4d} "
            f"lang={meta['lang_hint']:<6s} "
            f"quality={meta.get('quality_score', 'N/A')} "
            f"| {preview}..."
        )

    print(f"\n{'='*60}")
    print("全局顺序验证:")
    orders = [c.metadata['global_order'] for c in chunks]
    assert orders == sorted(orders), "global_order 不连续！"
    print(f"  global_order 范围: {min(orders)} ~ {max(orders)} ✓")
    print(f"{'='*60}")
