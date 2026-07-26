"""
父子文档检索器(ParentDocumentRetriever)
用于长文本(小说、年报等)的RAG检索

核心思路:
- 存的时候存"细粒度"(孩子)
- 搜的时候搜"粗粒度"(父亲)

好处:
- 孩子块用于精确匹配关键词
- 父块(如整章)保留完整上下文,让LLM能理清因果关系
"""
import hashlib
import numpy as np
from pathlib import Path
from typing import Optional, Union
from sentence_transformers import SentenceTransformer
from typing import List, Optional, Dict, Any, Tuple
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain.storage import InMemoryStore

from rag_config import logger


def _hash_embedding(text: str) -> list:
    """Hash-based embedding for ChromaDB queries"""
    h = hashlib.sha256(text.encode('utf-8')).digest()
    vec = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
    if len(vec) < 384:
        vec = np.pad(vec, (0, 384 - len(vec)), mode='constant')
    elif len(vec) > 384:
        vec = vec[:384]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()
from rag_core.embedding_service import get_embeddings
from rag_core.document_loader import RecursiveCharacterTextSplitter

import chromadb


class ParentDocumentRetriever(BaseRetriever):
    """
    父子文档检索器

    工作流程:
    1. 用户提问
    2. 向量检索匹配到"孩子块"(细粒度,如200字)
    3. 根据"孩子块"的元数据找到对应的"父块"(粗粒度,如整章2000字)
    4. 返回父块(完整章节文本)给LLM

    使用场景:
    - 小说:父子块分别是200字和2000字(按章节切分)
    - 年报:父子块分别是500字和5000字(按章节切分)
    """

    def __init__(
        self,
        vectorstore: chromadb.PersistentClient,
        parent_splitter: Optional[RecursiveCharacterTextSplitter] = None,
        child_splitter: Optional[RecursiveCharacterTextSplitter] = None,
        parent_id_key: str = "parent_id",
        chunk_key: str = "chunk_index",
        return_docs: bool = True,
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
        embedding_device: str = "cpu",
    ):
        """
        初始化父子文档检索器
        
        Args:
            vectorstore: ChromaDB 客户端
            parent_splitter: 父块切分器（粗粒度）
            child_splitter: 子块切分器（细粒度）
            parent_id_key: 父块ID的元数据键名
            chunk_key: 子块索引的元数据键名
            return_docs: 是否返回文档
            embedding_model: Sentence Transformers 模型名称
            embedding_device: 模型设备 ('cpu' 或 'cuda')
        """
        # 直接设置属性，避免 Pydantic 验证问题
        object.__setattr__(self, "tags", [])  # BaseRetriever 需要的属性
        object.__setattr__(self, "metadata", {})  # BaseRetriever 需要的属性
        object.__setattr__(self, "_vectorstore", vectorstore)
        object.__setattr__(self, "_collection", vectorstore.get_collection("knowledge_base"))
        object.__setattr__(self, "_parent_splitter", parent_splitter)
        object.__setattr__(self, "_child_splitter", child_splitter)
        object.__setattr__(self, "_parent_id_key", parent_id_key)
        object.__setattr__(self, "_chunk_key", chunk_key)
        object.__setattr__(self, "_return_docs", return_docs)
        object.__setattr__(self, "_docstore", InMemoryStore())
        
        # 初始化 Sentence Transformers 模型
        try:
            object.__setattr__(self, "_embedding_model", SentenceTransformer(embedding_model, device=embedding_device))
            object.__setattr__(self, "_embedding_dim", self._embedding_model.get_sentence_embedding_dimension())
            logger.info(f"嵌入模型加载成功: {embedding_model}, 维度: {self._embedding_dim}")
        except Exception as e:
            logger.warning(f"无法加载嵌入模型，将使用hash-based embedding: {e}")
            object.__setattr__(self, "_embedding_model", None)
            object.__setattr__(self, "_embedding_dim", 384)  # hash-based embedding 默认维度
        
        # 创建自定义 ChromaDB EmbeddingFunction
        class CustomEmbeddingFunction(chromadb.EmbeddingFunction):
            def __init__(self, model, dim):
                self.model = model
                self.dim = dim
            
            def __call__(self, input: list):
                embeddings = self.model.encode(input, convert_to_numpy=True)
                return embeddings.tolist()
        
        object.__setattr__(self, "_embedding_function", CustomEmbeddingFunction(self._embedding_model, self._embedding_dim))

        # 默认切分器配置
        if parent_splitter is None:
            object.__setattr__(self, "_parent_splitter", RecursiveCharacterTextSplitter(
                chunk_size=2000,
                chunk_overlap=200,
                separators=["\n\n", "\n", "。", "!", "?", ";", "...", ", ", ",", ". ", ".", " ", ""]
            ))

        if child_splitter is None:
            object.__setattr__(self, "_child_splitter", RecursiveCharacterTextSplitter(
                chunk_size=200,
                chunk_overlap=50,
                separators=["\n\n", "\n", "。", "!", "?", ";", "...", ", ", ",", ". ", ".", " ", ""]
            ))

        logger.info("ParentDocumentRetriever 初始化完成")

    def _embed_text(self, text: str) -> list:
        """
        生成文本的嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            嵌入向量
        """
        if self._embedding_model:
            return self._embedding_model.encode(text, convert_to_numpy=True).tolist()
        else:
            # 回退到 hash-based embedding
            return _hash_embedding(text)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """
        检索相关文档(核心方法)

        流程:
        1. 使用子块切分器将查询文本切分成小片段
        2. 对每个小片段进行向量检索
        3. 收集所有匹配到的子块的父块ID
        4. 从内存中获取完整的父块
        5. 返回父块列表
        """
        # 1. 将查询切分成小片段
        query_chunks = self._child_splitter.split_text(query)

        # 2. 对每个查询片段进行向量检索
        all_parent_ids = set()

        for query_chunk in query_chunks:
            # 向量检索匹配子块
            results = self._collection.query(
                query_embeddings=[self._embed_text(query_chunk)],
                n_results=3,  # 每个查询片段最多返回3个子块
                include=["metadatas"]
            )

            # 收集所有匹配到的子块的父块ID
            if results["ids"] and results["ids"][0]:
                for doc_id, metadata in zip(results["ids"][0], results["metadatas"][0]):
                    parent_id = metadata.get(self._parent_id_key)
                    if parent_id:
                        all_parent_ids.add(parent_id)

        # 3. 从内存中获取完整的父块
        parent_docs = []
        for parent_id in all_parent_ids:
            results = self._docstore.mget([parent_id])
            if results and results[0]:
                parent_docs.append(results[0])

        # 4. 去重(可能有多个查询片段匹配到同一个父块)
        unique_docs = []
        seen_ids = set()
        for doc in parent_docs:
            doc_id = doc.metadata.get("parent_id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_docs.append(doc)

        logger.info(f"检索到 {len(unique_docs)} 个父块")
        return unique_docs

    def add_documents(
        self,
        documents: List[Document],
        parent_ids: Optional[List[str]] = None
    ) -> int:
        """
        添加文档(需要按父块传入)

        Args:
            documents: 父块文档列表(如整章)
            parent_ids: 父块ID列表,如果不提供则自动生成

        Returns:
            添加的子块数量
        """
        if not documents:
            logger.warning("没有文档可添加")
            return 0

        if parent_ids is None:
            parent_ids = [f"parent_{i}" for i in range(len(documents))]

        # 1. 将父块存入内存
        for parent_doc, parent_id in zip(documents, parent_ids):
            parent_doc.metadata[self._parent_id_key] = parent_id
            self._docstore.mset([(parent_id, parent_doc)])

        # 2. 将父块切分成子块,存入向量库
        child_docs = self._parent_splitter.split_documents(documents)

        # 调试信息
        logger.info(f"父块数: {len(documents)}, 子块数: {len(child_docs)}")
        if child_docs:
            logger.info(f"第一个子块内容: {child_docs[0].page_content[:50]}")
            logger.info(f"第一个子块原始元数据: {child_docs[0].metadata}")

        # 3. 为每个子块添加元数据
        logger.info(f"父块数: {len(documents)}, parent_ids长度: {len(parent_ids)}, 子块数: {len(child_docs)}")

        for i, child_doc in enumerate(child_docs):
            if i >= len(parent_ids):
                logger.warning(f"子块索引 {i} 超出 parent_ids 范围 ({len(parent_ids)})")
                continue

            child_doc.metadata[self._chunk_key] = i
            child_doc.metadata[self._parent_id_key] = parent_ids[i]  # 修复:使用i而不是child_doc.metadata[self._chunk_key]

            # 调试信息
            if i == 0:
                logger.info(f"第一个子块更新后元数据: {child_doc.metadata}")

        # 4. 将子块存入向量库
        self._collection.add(
            documents=[d.page_content for d in child_docs],
            metadatas=[d.metadata for d in child_docs],
            ids=[f"child_{i}" for i in range(len(child_docs))]
        )

        # 5. 持久化
        try:
            self._collection.persist()
        except Exception:
            pass

        logger.info(f"添加了 {len(documents)} 个父块,切分成 {len(child_docs)} 个子块")
        return len(child_docs)

    def add_text(self, text: str, parent_id: str) -> int:
        """
        添加文本(便捷方法)

        Args:
            text: 文本内容
            parent_id: 父块ID

        Returns:
            添加的子块数量
        """
        doc = Document(
            page_content=text,
            metadata={"parent_id": parent_id}
        )
        return self.add_documents([doc], parent_ids=[parent_id])


class VectorStoreWithParentRetriever:
    """
    支持父子文档检索的向量存储管理器

    使用示例:
        vs = VectorStoreWithParentRetriever()

        # 添加小说(按章节传入)
        for chapter in chapters:
            vs.add_chapter(chapter_text, chapter_id)

        # 检索
        retriever = vs.get_parent_retriever()
        results = retriever.get_relevant_documents("主角为什么背叛?")
    """

    def __init__(self, persist_dir: Optional[Union[str, Path]] = None, 
                 embedding_model: str = "BAAI/bge-small-zh-v1.5",
                 embedding_device: str = "cpu"):
        self.persist_dir = Path(persist_dir) if persist_dir else Path("storage/knowledge_base_clean")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # ChromaDB 客户端
        self._vectorstore = chromadb.PersistentClient(path=str(self.persist_dir))

        # 创建或更新knowledge_base集合
        # ChromaDB 需要使用自定义 embedding 函数来支持不同维度
        try:
            # 删除旧集合（如果存在）
            collections = self._vectorstore.list_collections()
            for coll in collections:
                if coll.name == "knowledge_base":
                    logger.info(f"删除旧集合: {coll.name}")
                    self._vectorstore.delete_collection("knowledge_base")
                    break
            
            # 创建新集合，使用自定义 embedding 函数（延迟到 get_parent_retriever）
            self._vectorstore.get_or_create_collection(
                name="knowledge_base",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.warning(f"创建集合时出错: {e}")
            # 创建新集合
            self._vectorstore.get_or_create_collection(
                name="knowledge_base",
                metadata={"hnsw:space": "cosine"}
            )

        # 父子文档检索器
        self._parent_retriever: Optional[ParentDocumentRetriever] = None
        self.embedding_model = embedding_model
        self.embedding_device = embedding_device
        self._embedding_dim = 512  # 默认维度
        
        # 创建自定义 ChromaDB EmbeddingFunction（延迟到 ParentDocumentRetriever 初始化）
        self._embedding_function = None

        logger.info(f"VectorStoreWithParentRetriever 初始化完成: {self.persist_dir}")

    def add_chapter(
        self,
        text: str,
        chapter_id: str,
        chapter_num: Optional[int] = None
    ) -> int:
        """
        添加章节(便捷方法)

        Args:
            text: 章节文本
            chapter_id: 章节ID
            chapter_num: 章节号(可选,用于排序)

        Returns:
            添加的子块数量
        """
        doc = Document(
            page_content=text,
            metadata={
                "source": f"chapter_{chapter_num}",
                "chapter_id": chapter_id,
                "chapter_num": chapter_num
            }
        )

        retriever = self.get_parent_retriever()
        return retriever.add_text(text, parent_id=chapter_id)

    def get_parent_retriever(self) -> ParentDocumentRetriever:
        """
        获取父子文档检索器

        Returns:
            ParentDocumentRetriever 实例
        """
        if self._parent_retriever is None:
            # 创建自定义 embedding 函数
            class CustomEmbeddingFunction(chromadb.EmbeddingFunction):
                def __init__(self, model, dim):
                    self.model = model
                    self.dim = dim
                
                def __call__(self, input: list):
                    embeddings = self.model.encode(input, convert_to_numpy=True)
                    return embeddings.tolist()
            
            embedding_func = CustomEmbeddingFunction(
                SentenceTransformer(self.embedding_model, device=self.embedding_device),
                self._embedding_dim
            )
            
            # 创建集合，传入自定义 embedding 函数
            self._vectorstore.get_or_create_collection(
                name="knowledge_base",
                embedding_function=embedding_func,
                metadata={"hnsw:space": "cosine"}
            )
            
            # 创建检索器
            self._parent_retriever = ParentDocumentRetriever(
                vectorstore=self._vectorstore,
                embedding_model=self.embedding_model,
                embedding_device=self.embedding_device
            )
            # 设置 embedding_function
            self._embedding_function = embedding_func
        return self._parent_retriever

    def search_parent_mode(self, query: str, top_k: int = 5) -> List[Document]:
        """
        父子模式搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            父块文档列表
        """
        # 获取 parent retriever
        retriever = self.get_parent_retriever()
        
        # 执行检索
        docs = retriever.get_relevant_documents(query)
        
        logger.info(f"父子模式检索到 {len(docs)} 个父块")
        return docs
