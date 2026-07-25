"""
libsql 向量存储 - 替代 ChromaDB
"""
import hashlib
import json
import sqlite3
import numpy as np
import struct
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from langchain_core.documents import Document

from rag_config import (
    VECTOR_STORE_NAME, VECTOR_STORE_PERSIST_DIR,
    LOCAL_EMBEDDING_DIM, ADD_BATCH_SIZE, logger
)

from rag_core.embedding_service import get_embeddings


class VectorStoreManager:
    """libsql 向量存储管理器（替代 ChromaDB）

    使用 libsql 存储向量数据，支持：
    - 向量相似度检索（使用元积计算）
    - 批量插入优化
    - 查询向量缓存
    - 与 ChromaDB 版本的接口兼容
    """

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = persist_dir or VECTOR_STORE_PERSIST_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # libsql 数据库文件路径
        self.db_path = self.persist_dir / "knowledge_base.db"

        # 查询向量缓存（query_embedding_id -> embedding）
        self._query_cache = {}

        # 初始化数据库
        self._init_database()

    def _init_database(self):
        """初始化 libsql 数据库和表结构"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 创建 chunks 表（向量存储）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    text_content TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    metadata TEXT,
                    source TEXT,
                    page_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建向量索引（加速检索）
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_created ON chunks(created_at)')

            conn.commit()
            conn.close()

            logger.info(f"libsql 数据库初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"libsql 数据库初始化失败: {e}")
            raise

    def _vector_to_blob(self, vector: List[float]) -> bytes:
        """将向量转换为 BLOB 格式"""
        import struct
        return struct.pack('f' * len(vector), *vector)

    def _blob_to_vector(self, blob: bytes) -> np.ndarray:
        """将 BLOB 转换为向量"""
        return np.frombuffer(blob, dtype=np.float32)

    def _cosine_similarity_query(self, query_embedding: np.ndarray, top_k: int) -> List[Tuple[dict, float]]:
        """
        余弦相似度检索

        使用 Python 计算余弦相似度（libsql 不支持向量扩展）
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 获取所有向量
            cursor.execute('SELECT chunk_id, vector, metadata, text_content FROM chunks')
            all_chunks = cursor.fetchall()

            conn.close()

            if not all_chunks:
                return []

            # 计算余弦相似度
            similarities = []
            for chunk_id, vector_blob, metadata_json, text_content in all_chunks:
                vector = self._blob_to_vector(vector_blob)

                # 计算余弦相似度
                norm_q = np.linalg.norm(query_embedding)
                norm_v = np.linalg.norm(vector)
                if norm_q == 0 or norm_v == 0:
                    similarity = 0.0
                else:
                    similarity = np.dot(query_embedding, vector) / (norm_q * norm_v)

                similarities.append(({
                    'chunk_id': chunk_id,
                    'metadata': json.loads(metadata_json) if metadata_json else {},
                    'text_content': text_content
                }, similarity))

            # 按相似度降序排列
            similarities.sort(key=lambda x: x[1], reverse=True)

            # 返回 top_k 个结果
            return similarities[:top_k]

        except Exception as e:
            logger.error(f"余弦相似度检索失败: {e}")
            return []

    def add_documents(self, documents: List[Document], ids: Optional[List[str]] = None) -> None:
        """添加文档到向量库（分批处理）

        Args:
            documents: 文档列表
            ids: 可选的唯一 ID 列表，如果不提供则自动生成
        """
        if not documents:
            logger.warning("没有文档可添加")
            return

        total = len(documents)

        # 生成唯一 ID（如果未提供）
        if ids is None:
            ids = [
                f"doc_{hashlib.md5((str(doc.metadata.get('global_order', i)) + doc.metadata.get('source', '')).encode()).hexdigest()[:12]}"
                for i, doc in enumerate(documents)
            ]

        # 批量生成向量
        all_texts = [doc.page_content for doc in documents]
        logger.info(f"开始生成全体向量: {len(all_texts)} 个文本")

        try:
            all_embeddings = get_embeddings(all_texts)
        except Exception as e:
            logger.error(f"向量生成失败: {e}")
            raise

        if len(all_embeddings) != len(all_texts):
            logger.warning(f"向量数量 ({len(all_embeddings)}) 与文本数量 ({len(all_texts)}) 不匹配，可能部分生成失败")

        # 分批插入
        added = 0
        conn = sqlite3.connect(str(self.db_path))

        try:
            for start in range(0, total, ADD_BATCH_SIZE):
                end = min(start + ADD_BATCH_SIZE, total)
                batch_docs = documents[start:end]
                batch_ids = ids[start:end]
                batch_embeddings = all_embeddings[start:end] if start < len(all_embeddings) else []

                conn.execute('BEGIN TRANSACTION')
                cursor = conn.cursor()

                for i, doc in enumerate(batch_docs):
                    chunk_id = batch_ids[i]
                    text_content = doc.page_content
                    metadata_json = json.dumps(doc.metadata, ensure_ascii=False) if doc.metadata else '{}'
                    source = doc.metadata.get('source', 'unknown') if doc.metadata else 'unknown'

                    # 向量转换为 BLOB
                    if i < len(batch_embeddings):
                        vector_blob = self._vector_to_blob(batch_embeddings[i])
                    else:
                        vector_blob = b''

                    # 插入数据
                    cursor.execute('''
                        INSERT OR REPLACE INTO chunks (chunk_id, text_content, vector, metadata, source)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (chunk_id, text_content, vector_blob, metadata_json, source))

                    added += 1

                conn.commit()
                logger.info(f"添加进度: {added}/{total} ({added * 100 // total}%)")

            conn.close()

            logger.info(f"✅ 全部添加完成: {total} 个文档块到向量库")
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"添加批次失败: {e}")
            raise

    def add_documents_batched(self, documents: List[Document], batch_size: int = None) -> None:
        """显式分批添加文档（兼容旧接口）

        Args:
            documents: 文档列表
            batch_size: 每批数量，默认使用 ADD_BATCH_SIZE
        """
        if batch_size is None:
            batch_size = ADD_BATCH_SIZE

        if not documents:
            logger.warning("没有文档可添加")
            return

        total = len(documents)
        added = 0

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_docs = documents[start:end]

            try:
                self.add_documents(batch_docs)
                added += len(batch_docs)
                logger.info(
                    f"添加进度: {added}/{total} ({added * 100 // total}%) "
                    f"— 本批 {len(batch_docs)} 个文档块"
                )
            except Exception as e:
                logger.error(f"添加批次 [{start}:{end}] 失败: {e}")
                raise

        logger.info(f"✅ 全部添加完成: {total} 个文档块到向量库")

    def search(self, query: str, top_k: int = 5, score_threshold: float = None) -> List[Tuple[Document, float]]:
        """相似度搜索（兼容 ChromaDB 接口）

        Args:
            query: 查询文本
            top_k: 返回最大结果数
            score_threshold: 相似度阈值（已废弃，保留参数兼容性）

        Returns:
            (Document, distance分数) 列表，按distance分数升序排列（越小越相关）
        """
        # 检查缓存
        cache_key = f"{query}_{top_k}"
        if cache_key in self._query_cache:
            logger.debug(f"使用缓存的向量: {query[:30]}...")
            query_embedding = self._query_cache[cache_key]
        else:
            # 生成查询向量
            logger.debug(f"生成查询向量: {query[:30]}...")
            embeddings = get_embeddings([query])
            if not embeddings:
                logger.error("查询向量生成失败")
                return []
            query_embedding = embeddings[0]
            self._query_cache[cache_key] = query_embedding

        # 执行余弦相似度检索
        similarities = self._cosine_similarity_query(query_embedding, top_k)

        # 转换为 LangChain Document 格式
        results = []
        for chunk_data, similarity in similarities:
            doc = Document(
                page_content=chunk_data['text_content'],
                metadata=chunk_data['metadata']
            )
            results.append((doc, similarity))

        logger.info(f"搜索 '{query[:30]}...', 返回 {len(results)}/{top_k} 个结果")
        return results

    def delete_collection(self) -> None:
        """删除整个向量库（重建用）"""
        import shutil
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)
            logger.info(f"已删除向量库: {self.persist_dir}")

    def get_stats(self) -> dict:
        """获取向量库统计信息"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM chunks")
            count = cursor.fetchone()[0]

            conn.close()

            return {
                "total_documents": count,
                "persist_dir": str(self.persist_dir),
                "dictionary_path": str(self.db_path),
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_documents": 0,
                "persist_dir": str(self.persist_dir),
            }

    def list_documents(self) -> List[dict]:
        """列出所有已入库文档"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('SELECT chunk_id, metadata, source FROM chunks')
            rows = cursor.fetchall()

            conn.close()

            docs = []
            for chunk_id, metadata_json, source in rows:
                metadata = json.loads(metadata_json) if metadata_json else {}
                docs.append({
                    "id": chunk_id,
                    "source": source,
                    "metadata": metadata,
                })

            return docs
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []

    def get_chunk_count(self, source_filename: str) -> int:
        """获取特定来源的 chunk 数量"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM chunks WHERE source LIKE ?', (f"%{source_filename}%",))
            count = cursor.fetchone()[0]

            conn.close()
            return count
        except Exception as e:
            logger.error(f"获取 chunk 计数失败: {e}")
            return 0

    def delete_by_source(self, source_filename: str) -> int:
        """按来源删除文档块

        Args:
            source_filename: 文件名或路径的一部分

        Returns:
            删除的数量
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 查找匹配的文档
            cursor.execute('SELECT chunk_id FROM chunks WHERE source LIKE ?', (f"%{source_filename}%",))
            ids_to_delete = [row[0] for row in cursor.fetchall()]

            count = len(ids_to_delete)

            # 执行删除
            if count > 0:
                cursor.execute('DELETE FROM chunks WHERE source LIKE ?', (f"%{source_filename}%",))
                conn.commit()
                logger.info(f"已删除包含 '{source_filename}' 的 {count} 个 chunk")

            conn.close()
            return count
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return 0

    def reload(self):
        """重新加载（对于 libsql 不需要操作）"""
        logger.debug("重新加载（libsql 自动刷新）")

    def _cosine_similarity_search(self, query_embedding: np.ndarray, top_k: int) -> List[Tuple[dict, float]]:
        """余弦相似度检索（内部方法）

        Args:
            query_embedding: 查询向量
            top_k: 返回最大结果数

        Returns:
            (文档数据, 相似度) 列表，按相似度降序排列
        """
        return self._cosine_similarity(query_embedding, top_k)