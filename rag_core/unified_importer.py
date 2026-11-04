"""
统一导入流水线 - 将文档导入统一为 vectors(chunks) + entities + relationships 三步入库
"""
import hashlib
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_config import logger
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.wiki_db_libsql import get_wiki_db


class UnifiedImporter:
    """统一导入器 - 协调 chunks/entities/relationships 三条写入链路"""

    def __init__(self):
        self.vs = VectorStoreManager()
        self.wiki_db = get_wiki_db()
        self.lsh = None       # LSHIndexManager，延迟加载
        self.extractor = None  # LLMExtractor，延迟加载

    def _split_text(self, text: str, source: str) -> list:
        """文本分块 (chunk_size=500, overlap=50)"""
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.create_documents([text], [{'source': source}])
        return chunks

    def _source_fingerprint(self, filename: str) -> str:
        """为文件名生成唯一指纹（增量导入判断用）"""
        return hashlib.md5(filename.encode()).hexdigest()[:12]

    def _import_chunks(self, documents, source: str, overwrite: bool = False):
        """
        将 Document 列表写入 libsql chunks 表

        Args:
            documents: Document 列表
            source: 来源文件名
            overwrite: True 时先删除已有同 source 的记录

        Returns:
            写入的 Document 列表
        """
        if overwrite:
            deleted = self.vs.delete_by_source(source)
            if deleted:
                logger.info(f"  overwrite: 删除 {deleted} 个旧的 chunks (source={source})")
        if documents:
            self.vs.add_documents(documents)
            logger.info(f"  chunks: {len(documents)} 条入库")

            # Sync LSH index
            from rag_core.lsh_index import LSHIndexManager
            from rag_config import LSH_DIM, LSH_NBITS
            try:
                if self.lsh is None:
                    self.lsh = LSHIndexManager(dim=LSH_DIM, nbits=LSH_NBITS)
                    self.lsh.load_index()
                from rag_core.embedding_service import get_embeddings
                import numpy as np
                texts = [d.page_content for d in documents]
                if texts:
                    embs = np.array(get_embeddings(texts), dtype=np.float32)
                    self.lsh.add_documents(documents, embs)
                    self.lsh.save_index()
                    logger.info(f"  LSH: {len(texts)} vectors indexed")
            except Exception as e:
                logger.warning(f"LSH sync failed (non-blocking): {e}")

        return documents

    def _import_entities_and_relations(self, text: str, source: str) -> dict:
        """
        从文本中提取实体和关系并写入 WikiDB

        主路: jieba TF-IDF 实体提取
        辅路: LLM 关系提取（通过 SKIP_LLM 环境变量控制，导入阶段默认关闭）

        Returns:
            {'entities_added': N, 'relations_added': M}
        """
        stats = {"entities_added": 0, "relations_added": 0, "relations_error": None}
        if not text or not text.strip():
            return stats

        try:
            from rag_core.llm_extractor import LLMExtractor
            if self.extractor is None:
                self.extractor = LLMExtractor()

            result = self.extractor.extract_all(text, source)

            # Write entities (jieba main + LLM supplement)
            added_names = set()
            for entity in result.get('entities', []):
                name = entity.get('name', '').strip()
                if not name or name in added_names:
                    continue
                etype = entity.get('type', '')
                try:
                    self.wiki_db.add_entity(name, etype, source_chapter=source)
                except Exception:
                    try:
                        self.wiki_db.add_entity(name, etype, source_chapter=source)
                    except Exception as e:
                        logger.warning(f"add_entity retry failed: {name} {e}")
                        continue
                added_names.add(name)
                stats['entities_added'] += 1

            # Step 4: LLM 批量关系抽取（唯一入口：rag_core.relation_extractor）
            #   SKIP_LLM=1 时入口内部会直接跳过（零 LLM 调用）。
            from rag_core.relation_extractor import extract_relations_for_source

            try:
                chunks = self.vs.get_chunks_by_source(source)
            except Exception as e:
                chunks = None
                stats["relations_error"] = f"get_chunks_by_source: {type(e).__name__}: {e}"
                logger.warning(f"  关系抽取取 chunks 失败: {type(e).__name__}: {e}")

            if chunks is not None:
                res = extract_relations_for_source(source, chunks=chunks)
                stats["relations_added"] = res.get("relations_imported", 0)
                stats["relations_error"] = res.get("error")
                if res.get("error"):
                    logger.warning(f"  关系抽取未完成: {res['error']}")
                else:
                    logger.info(f"  关系抽取完成: {stats['relations_added']} 条")

            logger.info(
                f"  Jieba entities: {stats['entities_added']}, LLM relations: {stats['relations_added']}"
            )
        except Exception as e:
            logger.error(f"Entity/Relation extraction error: {e}")

        return stats

    def _is_already_imported(self, source: str) -> bool:
        """检查指定 source 是否已有导入记录"""
        return self.vs.get_chunk_count(source) > 0