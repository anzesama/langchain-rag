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

    def _is_already_imported(self, source: str) -> bool:
        """检查指定 source 是否已有导入记录"""
        return self.vs.get_chunk_count(source) > 0