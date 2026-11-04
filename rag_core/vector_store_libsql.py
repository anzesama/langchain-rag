"""
libsql 向量存储 - 替代 ChromaDB
"""
import hashlib
import json
import os
import sqlite3
import numpy as np
import struct
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from langchain_core.documents import Document

from rag_config import (
    VECTOR_STORE_NAME, VECTOR_STORE_PERSIST_DIR,
    LIBSQL_DICTIONARY_PATH,
    LOCAL_EMBEDDING_DIM, ADD_BATCH_SIZE, logger
)

from rag_core.embedding_service import get_embeddings
from rag_core.memory_scoring import (
    CONSOLIDATE_THRESHOLD,
    compute_final_score,
    forgetting_decay,
    update_after_retrieval,
)

#: 记忆重排的候选池大小（先向量粗排，再按记忆精排）
MEMORY_RERANK_POOL = 50

#: 新 chunk 的 importance 默认值（与 DB DEFAULT 保持一致）
DEFAULT_IMPORTANCE = 0.5


#: 记忆字段迁移定义（零侵入：ALTER TABLE ADD COLUMN，全部带默认值）
MEMORY_COLUMNS = (
    ("importance", "REAL DEFAULT 0.5"),
    ("access_count", "INTEGER DEFAULT 0"),
    ("last_access", "TIMESTAMP DEFAULT NULL"),
    ("memory_type", "TEXT DEFAULT 'semantic'"),
    ("consolidated", "INTEGER DEFAULT 0"),
)


class VectorStoreManager:
    """libsql 向量存储管理器（替代 ChromaDB）

    使用 libsql 存储向量数据，支持：
    - 向量相似度检索（使用元积计算）
    - 批量插入优化
    - 查询向量缓存
    - 与 ChromaDB 版本的接口兼容
    """

    def __init__(self, persist_dir: Optional[Path] = None):
        """初始化向量存储。

        显式传入 `persist_dir` 时，数据库落在该目录下（测试隔离用）；
        不传时使用生产配置 `LIBSQL_DICTIONARY_PATH`。

        ⚠️ 2026-11-03 事故：旧实现忽略 `persist_dir`、永远用全局
           `LIBSQL_DICTIONARY_PATH`，导致测试的临时目录 fixture 形同虚设。
        """
        if persist_dir is not None:
            self.persist_dir = Path(persist_dir)
            self.db_path = self.persist_dir / "knowledge_base.db"
        else:
            self.persist_dir = VECTOR_STORE_PERSIST_DIR
            self.db_path = LIBSQL_DICTIONARY_PATH
        self.persist_dir.mkdir(parents=True, exist_ok=True)

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

            # 记忆字段迁移（幂等；旧库补齐列，不重建表、不丢数据）
            self._migrate_memory_columns(cursor)

            conn.commit()
            conn.close()

            logger.info(f"libsql 数据库初始化完成: {self.db_path}")
        except Exception as e:
            logger.error(f"libsql 数据库初始化失败: {type(e).__name__}: {e}")
            raise

    @staticmethod
    def _migrate_memory_columns(cursor) -> None:
        """为 chunks 表补齐脑启发性记忆所需字段（幂等）。

        为什么用 ADD COLUMN：SQLite 支持带默认值加列，无需重建表，
        旧库可平滑升级，且新列有默认值 → 关闭功能即可回滚（验收 V4）。
        """
        existing = {row[1] for row in cursor.execute("PRAGMA table_info(chunks)").fetchall()}
        for name, ddl in MEMORY_COLUMNS:
            if name not in existing:
                VectorStoreManager._add_column_if_missing(cursor, name, ddl)

    @staticmethod
    def _add_column_if_missing(cursor, name: str, ddl: str) -> None:
        """加列，容忍并发迁移下的重复列（幂等）。

        ⚠️ SQLite **不支持** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
        （实测 3.51.2 报 `near "EXISTS": syntax error`），只能捕获 OperationalError。
        若不捕获：两个进程同时启动时，后一个的 ALTER 会抛错 → 冒泡到
        `_init_database` 的 except → 整个 `VectorStoreManager.__init__` 失败。
        """
        try:
            cursor.execute(f"ALTER TABLE chunks ADD COLUMN {name} {ddl}")
            logger.info(f"记忆字段迁移完成: chunks.{name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                logger.debug(f"记忆字段已存在，跳过: chunks.{name}")
                return
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
        余弦相似度检索（向量化实现）。

        旧实现逐行 `np.dot`，且**每轮循环重算** `np.linalg.norm(query_embedding)`，
        并对**全部**行做 `json.loads`。现改为：
        1. BLOB 拼接后一次性 `np.frombuffer` 构造矩阵
        2. 单次矩阵乘法 `mat @ q` 计算全部相似度
        3. `argpartition` 选 top-k，**只**解析 top-k 的 metadata
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # 获取所有向量（含记忆字段；关闭记忆功能时这些列不会被使用）
            cursor.execute(
                'SELECT chunk_id, vector, metadata, text_content, '
                'importance, access_count, last_access FROM chunks'
            )
            all_chunks = cursor.fetchall()

            conn.close()

            n = len(all_chunks)
            if n == 0:
                return []

            q = np.asarray(query_embedding, dtype=np.float32)
            dim = q.shape[0]

            # 一次性构造矩阵（避免逐行 np.dot 的 Python 层开销）
            raw = b''.join(row[1] for row in all_chunks)
            if len(raw) == n * dim * 4:
                mat = np.frombuffer(raw, dtype=np.float32).reshape(n, dim)
            else:
                # 维度不一致时退化为逐行（容错）
                mat = np.zeros((n, dim), dtype=np.float32)
                for i, row in enumerate(all_chunks):
                    vec = np.frombuffer(row[1], dtype=np.float32)
                    if vec.shape[0] == dim:
                        mat[i] = vec

            q_norm = float(np.linalg.norm(q))
            norms = np.linalg.norm(mat, axis=1)
            denom = norms * q_norm

            sims = np.zeros(n, dtype=np.float32)
            valid = denom > 0
            if q_norm > 0:
                sims[valid] = (mat[valid] @ q) / denom[valid]

            k = min(top_k, n)
            memory_on = self._memory_enabled()

            # 记忆重排需要更大的候选池：先向量粗排，再按记忆精排
            fetch = n if k >= n else min(n, max(k, MEMORY_RERANK_POOL if memory_on else k))
            if fetch >= n:
                order = np.argsort(-sims)
            else:
                order = np.argpartition(-sims, fetch - 1)[:fetch]
                order = order[np.argsort(-sims[order])]

            if memory_on:
                return self._memory_rerank(all_chunks, sims, order, k)

            results: List[Tuple[dict, float]] = []
            for i in order[:k]:
                row = all_chunks[int(i)]
                metadata_json = row[2]
                results.append(({
                    'chunk_id': row[0],
                    'metadata': json.loads(metadata_json) if metadata_json else {},
                    'text_content': row[3],
                }, float(sims[int(i)])))
            return results

        except Exception as e:
            logger.error(f"余弦相似度检索失败: {type(e).__name__}: {e}")
            return []

    # ------------------------------------------------------------ 记忆层

    @staticmethod
    def _memory_enabled() -> bool:
        """脑启发性记忆检索开关（默认关闭 → 与旧行为逐字节一致，验收 V4）"""
        return os.environ.get("RAG_MEMORY_ENABLED", "0").strip().lower() in (
            "1", "true", "yes", "on"
        )

    @staticmethod
    def _memory_fields(row) -> Tuple[float, int, Any]:
        """从一行 chunk 中安全取出 (importance, access_count, last_access)"""
        importance = DEFAULT_IMPORTANCE if row[4] is None else float(row[4])
        access_count = int(row[5] or 0)
        last_access = row[6]
        return importance, access_count, last_access

    def _memory_rerank(
        self,
        all_chunks: list,
        sims: np.ndarray,
        order: np.ndarray,
        k: int,
    ) -> List[Tuple[dict, float]]:
        """按记忆评分（重要性 × 衰减 × 访问频率）对候选池精排，并强化命中项。

        ⚠️ 本方法**有写副作用**（`_reinforce`），仅在 `RAG_MEMORY_ENABLED=1` 时进入。
        """
        now = datetime.utcnow()
        scored = []
        for idx in order:
            i = int(idx)
            importance, access_count, last_access = self._memory_fields(all_chunks[i])
            decay = forgetting_decay(last_access, now)
            final = compute_final_score(float(sims[i]), importance, decay, access_count)
            scored.append({
                "score": final,
                "similarity": float(sims[i]),
                "index": i,
                "importance": importance,
                "access_count": access_count,
                "decay": decay,
                "last_access": last_access,
            })

        # 显式排序键：综合分降序 → 相似度降序 → 行号升序。
        # ⚠️ 不要直接 `sort()` 整个元组：尾部含 last_access（可为 None 或 datetime），
        #    一旦前面各元素全部相等就会退化为 datetime vs None 比较 → TypeError。
        scored.sort(key=lambda item: (-item["score"], -item["similarity"], item["index"]))
        top = scored[:k]

        self._reinforce([item["index"] for item in top], all_chunks, now)

        results: List[Tuple[dict, float]] = []
        for item in top:
            i = item["index"]
            row = all_chunks[i]
            metadata_json = row[2]
            metadata = dict(json.loads(metadata_json) if metadata_json else {})
            metadata.update({
                "importance": item["importance"],
                "access_count": item["access_count"],
                "last_access": str(item["last_access"]) if item["last_access"] else None,
                "similarity": item["similarity"],
                "decay": item["decay"],
                "memory_score": item["score"],
            })
            results.append(({
                'chunk_id': row[0],
                'metadata': metadata,
                'text_content': row[3],
            }, item["score"]))
        return results

    def _reinforce(self, indices: List[int], all_chunks: list, now: datetime) -> None:
        """检索即强化：命中项 access_count +1、importance ×1.05、刷新 last_access。

        达到 `CONSOLIDATE_THRESHOLD` 次命中则标记为已「巩固」（长期记忆）。
        失败只记日志，不影响检索结果。
        """
        if not indices:
            return
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                for i in indices:
                    chunk_id = all_chunks[i][0]
                    importance, access_count, _ = self._memory_fields(all_chunks[i])
                    new_count, new_importance = update_after_retrieval(access_count, importance)
                    consolidated = 1 if new_count >= CONSOLIDATE_THRESHOLD else 0
                    conn.execute(
                        "UPDATE chunks SET access_count = ?, importance = ?, "
                        "last_access = ?, consolidated = ? WHERE chunk_id = ?",
                        (new_count, new_importance, timestamp, consolidated, chunk_id),
                    )
                conn.commit()
            except Exception:
                # 显式回滚：单条 UPDATE 失败时不留下部分写入
                conn.rollback()
                raise
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"记忆强化写回失败: {type(e).__name__}: {e}")

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

    def get_memories_stats(self, top_n: int = 10, decay_threshold: float = 0.1) -> dict:
        """脑启发性记忆层聚合统计（只读）。

        ⚠️ 只读：不写库、不触发导入，可安全高频轮询。
        """
        now = datetime.utcnow()
        empty = {
            "total": 0, "semantic": 0, "episodic": 0, "consolidated": 0,
            "avg_importance": 0.0, "top_accessed": [],
            "decayed_below_threshold": 0, "memory_enabled": self._memory_enabled(),
        }
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                if not total:
                    return empty

                by_type = dict(conn.execute(
                    "SELECT COALESCE(memory_type, 'semantic'), COUNT(*) "
                    "FROM chunks GROUP BY 1"
                ).fetchall())
                consolidated = conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE consolidated = 1"
                ).fetchone()[0]
                avg_importance = conn.execute(
                    "SELECT AVG(COALESCE(importance, ?)) FROM chunks", (DEFAULT_IMPORTANCE,)
                ).fetchone()[0]
                top_rows = conn.execute(
                    "SELECT chunk_id, COALESCE(source, ''), COALESCE(access_count, 0), "
                    "COALESCE(importance, ?) FROM chunks "
                    "ORDER BY access_count DESC, importance DESC LIMIT ?",
                    (DEFAULT_IMPORTANCE, int(top_n)),
                ).fetchall()
                # 只取有 last_access 的行：NULL 行 decay 恒为 1.0，不可能低于阈值
                last_access_rows = conn.execute(
                    "SELECT last_access FROM chunks WHERE last_access IS NOT NULL"
                ).fetchall()
            finally:
                conn.close()

            decayed = sum(
                1 for (last_access,) in last_access_rows
                if forgetting_decay(last_access, now) < decay_threshold
            )

            return {
                "total": total,
                "semantic": int(by_type.get("semantic", 0)),
                "episodic": int(by_type.get("episodic", 0)),
                "consolidated": int(consolidated),
                "avg_importance": float(avg_importance or 0.0),
                "top_accessed": [
                    {
                        "chunk_id": row[0],
                        "source": row[1],
                        "access_count": int(row[2]),
                        "importance": float(row[3]),
                    }
                    for row in top_rows
                ],
                "decayed_below_threshold": decayed,
                "memory_enabled": self._memory_enabled(),
            }
        except Exception as e:
            logger.error(f"记忆统计失败: {type(e).__name__}: {e}")
            return empty

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

    def get_chunks_by_source(self, source: str, limit: Optional[int] = None) -> List[dict]:
        """按 source **精确**获取 chunks（供关系抽取等下游使用）

        Args:
            source: 精确来源（对应 chunks.source 列，不做模糊匹配）
            limit: 可选返回条数上限

        Returns:
            [{"chunk_id":…, "text_content":…, "chunk_text":…, "metadata": {...}}, …]
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                sql = "SELECT chunk_id, text_content, metadata FROM chunks WHERE source = ?"
                params: List[Any] = [source]
                if limit:
                    sql += " LIMIT ?"
                    params.append(limit)
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                conn.close()

            out: List[dict] = []
            for row in rows:
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                except (TypeError, ValueError):
                    meta = {}
                out.append(
                    {
                        "chunk_id": row["chunk_id"],
                        "text_content": row["text_content"],
                        "chunk_text": row["text_content"],
                        "metadata": meta,
                    }
                )
            return out
        except Exception as e:
            logger.error(f"按来源获取 chunks 失败: {type(e).__name__}: {e}")
            return []

    def list_sources(self) -> List[str]:
        """列出所有已入库来源（去重、升序）"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    "SELECT DISTINCT source FROM chunks WHERE source IS NOT NULL ORDER BY source"
                ).fetchall()
            finally:
                conn.close()
            return [r[0] for r in rows if r[0]]
        except Exception as e:
            logger.error(f"列出来源失败: {type(e).__name__}: {e}")
            return []

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