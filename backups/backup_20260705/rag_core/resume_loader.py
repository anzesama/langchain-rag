"""
断点续传加载器 — 支持大文件中断恢复

在加载大量文档（如小说）时，可能因为超时或中断导致加载失败。
本模块提供断点续传功能，自动记录已加载的 chunk ID，支持从中断处恢复。

技术特点：
- 从进度文件读取已入库的 chunk ID
- 重新分块文档（使用 EnhancedDocumentProcessor）
- 筛选出缺失的 chunk
- 分批调用嵌入服务生成向量
- 同时写入 FAISS LSH 索引和 ChromaDB
- 每批次后保存进度

使用示例：
    >>> loader = ResumeLoader(
    ...     novel_source="guzhenren.txt",
    ...     chunk_size=500,
    ...     chunk_overlap=50,
    ... )
    >>> loader.load(resume=True)  # 支持断点续传
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Set
import numpy as np

from langchain_core.documents import Document

from rag_config import (
    LOAD_STATE_PATH,
    LSH_INDEX_PATH,
    ID_MAP_PATH,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_BATCH_SIZE,
    LSH_DIM,
    LSH_NBITS,
    STORAGE_DIR,
    logger,
)

from rag_core.document_processor import EnhancedDocumentProcessor, create_enhanced_processor
from rag_core.embedding_service import get_embeddings
from rag_core.lsh_index import LSHIndexManager

logger = logging.getLogger("rag.resume_loader")


class ResumeLoader:
    """
    断点续传加载器

    核心功能：
    - 从进度文件读取已入库的 chunk ID
    - 重新分块文档，筛选缺失的 chunk
    - 分批调用嵌入服务
    - 同时写入 LSH 索引和 ChromaDB
    - 每批次后保存进度

    使用示例：
        >>> loader = ResumeLoader(
        ...     novel_source="guzhenren.txt",
        ...     chunk_size=500,
        ...     chunk_overlap=50,
        ... )
        >>> loader.load(resume=True)
    """

    def __init__(
        self,
        novel_source: str,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        embedding_batch_size: int = EMBEDDING_BATCH_SIZE,
        use_lsh_index: bool = True,
        global_counter: int = None,
    ):
        """
        初始化断点续传加载器

        Args:
            novel_source: 小说源文件路径
            chunk_size: 分块大小
            chunk_overlap: 重叠字符数
            embedding_batch_size: Embedding 批次大小
            use_lsh_index: 是否使用 LSH 索引
            global_counter: 全局递增计数器（用于 global_order）
        """
        self.novel_source = novel_source
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_batch_size = embedding_batch_size
        self.use_lsh_index = use_lsh_index
        self.global_counter = global_counter or 0
        self.chunks = []  # 存储已加载的文档

        # 创建文档处理器
        self.processor = create_enhanced_processor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # LSH 索引管理器
        self.lsh_manager = LSHIndexManager(dim=LSH_DIM, nbits=LSH_NBITS) if use_lsh_index else None

        # 进度文件
        self.progress_file = STORAGE_DIR / f"progress_{Path(novel_source).stem}.json"

        # 已入库的 chunk ID 集合
        self.loaded_ids: Set[str] = set()

        # 统计信息
        self.stats = {
            "total_chunks": 0,
            "loaded_chunks": 0,
            "skipped_chunks": 0,
            "failed_chunks": 0,
        }

    def load(
        self,
        resume: bool = True,
        use_embeddings: bool = True,
    ) -> int:
        """
        加载小说（支持断点续传）

        Args:
            resume: 是否从断点继续
            use_embeddings: 是否生成 embedding（False 时仅写入 ChromaDB）

        Returns:
            新加载的 chunk 数量
        """
        logger.info(f"开始加载: {self.novel_source} (resume={resume})")

        # 1. 读取进度文件
        if resume:
            self._load_progress()

        # 2. 读取并分块小说
        logger.info("读取小说并分块...")
        with open(self.novel_source, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = self.processor.process_single(text, source=self.novel_source)
        
        # 分配全局递增的 global_order
        chunks = self._assign_global_order(chunks)

        self.stats["total_chunks"] = len(chunks)

        # 3. 筛选出缺失的 chunk
        missing_chunks = self._filter_missing_chunks(chunks)

        logger.info(f"总 chunk 数: {len(chunks)}, 已加载: {len(self.loaded_ids)}, "
                   f"缺失: {len(missing_chunks)}")

        if not missing_chunks:
            logger.info("所有 chunk 已加载，无需继续")
            return 0

        # 4. 分批处理缺失的 chunk
        new_chunks = 0
        for i in range(0, len(missing_chunks), self.embedding_batch_size):
            batch = missing_chunks[i:i + self.embedding_batch_size]
            logger.info(f"处理批次 [{i}:{i+len(batch)}]/{len(missing_chunks)}")

            # 生成 embedding
            if use_embeddings:
                texts = [chunk.page_content for chunk in batch]
                embeddings = get_embeddings(texts, batch_size=self.embedding_batch_size)
            else:
                embeddings = None

            # 写入 ChromaDB
            self._write_to_chromadb(batch)

            # 写入 LSH 索引
            if self.use_lsh_index and embeddings is not None:
                self.lsh_manager.add_vectors(
                    np.array(embeddings),
                    batch,
                    progress_file=self.progress_file,
                )

            # 更新进度
            new_chunks += len(batch)
            self.stats["loaded_chunks"] += len(batch)
            
            # 更新 loaded_ids
            for chunk in batch:
                chunk_id = f"novel_{chunk.metadata['global_order']}"
                self.loaded_ids.add(chunk_id)
            
            self._save_progress()
            
            # 保存加载的文档到 self.chunks
            self.chunks.extend(batch)

        logger.info(f"加载完成: 新增 {new_chunks} 个 chunk")

        return new_chunks

    def _load_progress(self):
        """从进度文件读取已入库的 chunk ID"""
        if not self.progress_file.exists():
            logger.info("进度文件不存在，从头开始加载")
            return

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)

            # 加载已入库的 chunk ID
            self.loaded_ids = set(progress.get("loaded_ids", []))
            logger.info(f"从进度文件恢复: loaded_ids={len(self.loaded_ids)}")

            # 更新统计
            self.stats["loaded_chunks"] = progress.get("loaded_chunks", 0)

        except Exception as e:
            logger.error(f"读取进度文件失败: {e}")

    def _filter_missing_chunks(self, chunks: List[Document]) -> List[Document]:
        """
        筛选出缺失的 chunk

        ID 规则: novel_{global_order}

        Args:
            chunks: 所有 chunk 列表

        Returns:
            缺失的 chunk 列表
        """
        missing = []

        for chunk in chunks:
            chunk_id = f"novel_{chunk.metadata['global_order']}"

            if chunk_id not in self.loaded_ids:
                missing.append(chunk)
            else:
                self.stats["skipped_chunks"] += 1

        return missing

    def _write_to_chromadb(self, chunks: List[Document]):
        """
        写入 ChromaDB（直接使用 VectorStoreManager，避免自动导入）

        Args:
            chunks: 待写入的 chunk 列表
        """
        try:
            from rag_core.vector_store import VectorStoreManager
            from rag_core.knowledge_base import KnowledgeBase

            # 获取现有的 VectorStoreManager 实例
            kb = KnowledgeBase(auto_import=False)
            vector_store = kb.vector_store
            # 直接调用 VectorStoreManager.add_documents
            vector_store.add_documents(chunks)
            logger.debug(f"写入 ChromaDB: {len(chunks)} 个 chunk")
        except Exception as e:
            logger.error(f"写入 ChromaDB 失败: {e}")
            self.stats["failed_chunks"] += len(chunks)

    def _assign_global_order(self, chunks: List[Document]) -> List[Document]:
        """
        为 chunk 分配全局递增的 global_order
        
        Args:
            chunks: 待分配的 chunk 列表
        
        Returns:
            分配后的 chunk 列表
        """
        for chunk in chunks:
            self.global_counter += 1
            chunk.metadata["global_order"] = self.global_counter
            chunk.metadata["doc_type"] = "novel"
            chunk.metadata["source_file"] = self.novel_source
        return chunks
    
    def get_progress(self) -> dict:
        """
        返回加载进度
        
        Returns:
            进度信息字典
        """
        return {
            "total_chunks": self.stats["total_chunks"],
            "loaded_chunks": self.stats["loaded_chunks"],
            "skipped_chunks": self.stats["skipped_chunks"],
            "failed_chunks": self.stats["failed_chunks"],
            "global_counter": self.global_counter,
            "chunks": self.chunks,  # 添加已加载的文档列表
            "progress_percent": (
                self.stats["loaded_chunks"] / self.stats["total_chunks"] * 100
                if self.stats["total_chunks"] > 0 else 0
            ),
        }
    
    def _save_progress(self):
        """保存进度到文件"""
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        progress_data = {
            "loaded_chunks": self.stats["loaded_chunks"],
            "total_chunks": self.stats["total_chunks"],
            "skipped_chunks": self.stats["skipped_chunks"],
            "failed_chunks": self.stats["failed_chunks"],
            "loaded_ids": sorted(list(self.loaded_ids)),  # 排序并去重
            "timestamp": __import__("time").time(),
        }

        with open(self.progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    def clear_progress(self):
        """清空进度文件"""
        if self.progress_file.exists():
            self.progress_file.unlink()
        self.loaded_ids.clear()
        logger.info("进度已清空")


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    # 创建测试数据
    test_text = """第一章

这里是第一章的内容。

第二章

这里是第二章的内容。

第三章

这里是第三章的内容。
"""

    test_file = Path(__file__).parent.parent / "storage" / "test_novel.txt"
    test_file.write_text(test_text, encoding="utf-8")

    print("=" * 60)
    print("断点续传加载器测试")
    print("=" * 60)

    # 创建加载器
    loader = ResumeLoader(
        novel_source=str(test_file),
        chunk_size=100,
        chunk_overlap=20,
    )

    # 第一次加载
    print("\n第一次加载...")
    new_chunks = loader.load(resume=False)
    print(f"新增 chunk: {new_chunks}")
    print(f"统计: {loader.get_stats()}")

    # 第二次加载（断点续传）
    print("\n第二次加载（断点续传）...")
    new_chunks = loader.load(resume=True)
    print(f"新增 chunk: {new_chunks}")
    print(f"统计: {loader.get_stats()}")

    # 清理测试文件
    test_file.unlink(missing_ok=True)
    loader.clear_progress()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
