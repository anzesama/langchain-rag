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
from rag_core.vector_store_libsql import VectorStoreManager   # 直接使用 VectorStoreManager，避免循环导入

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
        self.novel_source = novel_source
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_batch_size = embedding_batch_size
        self.use_lsh_index = use_lsh_index
        self.global_counter = global_counter or 0
        self.chunks = []

        self.processor = create_enhanced_processor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self.lsh_manager = LSHIndexManager(dim=LSH_DIM, nbits=LSH_NBITS) if use_lsh_index else None

        self.progress_file = STORAGE_DIR / f"progress_{Path(novel_source).stem}.json"
        self.loaded_ids: Set[str] = set()

        self.stats = {
            "total_chunks": 0,
            "loaded_chunks": 0,
            "skipped_chunks": 0,
            "failed_chunks": 0,
        }

        # ========== 关键：直接使用 VectorStoreManager，避免循环导入 ==========
        self.vs_manager = VectorStoreManager()

    def load(self, resume: bool = True, use_embeddings: bool = True) -> int:
        logger.info(f"开始加载: {self.novel_source} (resume={resume})")

        if resume:
            self._load_progress()
            # 从 libsql 向量库同步已存在的 chunk ID
            self._sync_from_vector_store()
            
            # 优化：如果进度文件存在且向量库中已有数据，直接跳过
            if self.progress_file.exists() and len(self.loaded_ids) > 0:
                logger.info(f"进度文件存在，已加载 {len(self.loaded_ids)} 个 chunk，跳过重新分块")
                # 从 libsql 向量库获取已存在的 chunk 数量
                vs_count = self.vs_manager.get_stats().get('total_documents', 0)
                logger.info(f"向量库中已有 {vs_count} 个 chunk")
                logger.info(f"进度文件记录: {len(self.loaded_ids)} 个 chunk")
                
                # 只有当向量库中的 chunk 数量与进度文件一致时，才认为全部已加载
                if vs_count == len(self.loaded_ids):
                    logger.info(f"向量库中的 chunk 与进度文件一致，全部已加载，无需继续")
                    return 0

        logger.info("读取小说并分块...")
        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030']
        text = None
        for enc in encodings:
            try:
                with open(self.novel_source, 'r', encoding=enc) as f:
                    text = f.read()
                logger.info(f"文件编码: {enc}, 长度: {len(text)} 字符")
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError(f"无法解码文件: {self.novel_source}")

        chunks = self.processor.process_single(text, source=self.novel_source)
        chunks = self._assign_global_order(chunks)

        self.stats["total_chunks"] = len(chunks)
        missing_chunks = self._filter_missing_chunks(chunks)

        logger.info(f"总 chunk 数: {len(chunks)}, 已加载: {len(self.loaded_ids)}, 缺失: {len(missing_chunks)}")

        if not missing_chunks:
            logger.info("所有 chunk 已加载，无需继续")
            return 0

        new_chunks = 0
        for i in range(0, len(missing_chunks), self.embedding_batch_size):
            batch = missing_chunks[i:i + self.embedding_batch_size]
            logger.info(f"处理批次 [{i}:{i+len(batch)}]/{len(missing_chunks)}")

            if use_embeddings:
                texts = [chunk.page_content for chunk in batch]
                embeddings = get_embeddings(texts, batch_size=self.embedding_batch_size)
            else:
                embeddings = None

            self._write_to_chromadb(batch)

            if self.use_lsh_index and embeddings is not None:
                self.lsh_manager.add_vectors(
                    np.array(embeddings),
                    batch,
                    progress_file=self.progress_file,
                )

            new_chunks += len(batch)
            self.stats["loaded_chunks"] += len(batch)

            for chunk in batch:
                chunk_id = chunk.metadata.get("chunk_id")
                if chunk_id:
                    self.loaded_ids.add(chunk_id)
                else:
                    # 向后兼容旧版本
                    self.loaded_ids.add(f"novel_{chunk.metadata['global_order']}")

            self._save_progress()
            self.chunks.extend(batch)

        logger.info(f"加载完成: 新增 {new_chunks} 个 chunk")
        return new_chunks

    def _load_progress(self):
        if not self.progress_file.exists():
            logger.info("进度文件不存在，从头开始加载")
            return
        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
            self.loaded_ids = set(progress.get("loaded_ids", []))
            logger.info(f"从进度文件恢复: loaded_ids={len(self.loaded_ids)}")
            self.stats["loaded_chunks"] = progress.get("loaded_chunks", 0)
        except Exception as e:
            logger.error(f"读取进度文件失败: {e}")

    def _sync_from_vector_store(self):
        """从 libsql 向量库同步已存在的 chunk ID，避免重复分块"""
        try:
            docs = self.vs_manager.list_documents()
            current_file_count = 0
            for doc in docs:
                meta = doc.get('metadata', {})
                # 只同步当前文件的 chunk ID
                source_file = meta.get('source_file') or meta.get('source', '')
                if source_file == self.novel_source:
                    current_file_count += 1
                    # 同步 chunk_id（如果存在）
                    chunk_id = meta.get('chunk_id')
                    if chunk_id and chunk_id not in self.loaded_ids:
                        self.loaded_ids.add(chunk_id)
                    # 同步 novel_{global_order}（向后兼容）
                    global_order = meta.get('global_order')
                    if global_order:
                        novel_id = f"novel_{global_order}"
                        if novel_id not in self.loaded_ids:
                            self.loaded_ids.add(novel_id)
            logger.info(f"从 libsql 向量库同步: loaded_ids={len(self.loaded_ids)}, 当前文件 chunk 数={current_file_count}")
        except Exception as e:
            logger.warning(f"从 libsql 向量库同步失败: {e}")

    def _filter_missing_chunks(self, chunks: List[Document]) -> List[Document]:
        missing = []
        for chunk in chunks:
            chunk_id = chunk.metadata.get("chunk_id", f"novel_{chunk.metadata['global_order']}")  # 向后兼容
            if chunk_id not in self.loaded_ids:
                missing.append(chunk)
            else:
                self.stats["skipped_chunks"] += 1
        return missing

    def _write_to_chromadb(self, chunks: List[Document]):
        """使用复用的 VectorStoreManager"""
        try:
            self.vs_manager.add_documents(chunks)
            logger.debug(f"Write to ChromaDB: {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to write to ChromaDB: {e}")
            self.stats["failed_chunks"] += len(chunks)

    def _assign_global_order(self, chunks: List[Document]) -> List[Document]:
        import hashlib
        for chunk in chunks:
            self.global_counter += 1
            chunk.metadata["global_order"] = self.global_counter
            chunk.metadata["doc_type"] = "novel"
            chunk.metadata["source_file"] = self.novel_source
            # 新增：基于内容生成稳定的 chunk_id
            content_hash = hashlib.md5(chunk.page_content.encode('utf-8', errors='ignore')).hexdigest()[:16]
            chunk.metadata["chunk_id"] = f"novel_{content_hash}"  # 用哈希作为 ID
        return chunks

    def get_progress(self) -> dict:
        return {
            "total_chunks": self.stats["total_chunks"],
            "loaded_chunks": self.stats["loaded_chunks"],
            "skipped_chunks": self.stats["skipped_chunks"],
            "failed_chunks": self.stats["failed_chunks"],
            "global_counter": self.global_counter,
            "chunks": self.chunks,
            "progress_percent": (
                self.stats["loaded_chunks"] / self.stats["total_chunks"] * 100
                if self.stats["total_chunks"] > 0 else 0
            ),
        }

    def _save_progress(self):
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        progress_data = {
            "loaded_chunks": self.stats["loaded_chunks"],
            "total_chunks": self.stats["total_chunks"],
            "skipped_chunks": self.stats["skipped_chunks"],
            "failed_chunks": self.stats["failed_chunks"],
            "loaded_ids": sorted(list(self.loaded_ids)),
            "timestamp": __import__("time").time(),
        }
        with open(self.progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2)

    def get_stats(self) -> dict:
        return self.stats.copy()

    def clear_progress(self):
        if self.progress_file.exists():
            self.progress_file.unlink()
        self.loaded_ids.clear()
        logger.info("进度已清空")