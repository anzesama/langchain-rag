"""
LSH 索引管理器 — 基于 FAISS LSH 的高速检索

使用 LSH（Locality Sensitive Hashing）实现近似最近邻搜索，
相比 HNSW 图索引，LSH 在大规模数据集上检索速度更快（~0.1ms），
但召回率略低。

技术特点：
- 使用 FAISS.IndexLSH 进行 LSH 哈希
- 支持 int8 动态量化（减少内存占用）
- 维护 id_map 映射内部 ID 到 Document 对象
- 支持进度保存/加载
"""

import pickle
from typing import List, Optional, Dict, Any
import numpy as np
import logging
from pathlib import Path
import faiss

from langchain_core.documents import Document

from rag_config import (
    LSH_INDEX_PATH,
    ID_MAP_PATH,
    LSH_DIM,
    LSH_NBITS,
    logger,
)

logger = logging.getLogger("rag.lsh_index")


class LSHIndexManager:
    """
    LSH 索引管理器

    核心功能：
    - 构建 FAISS LSH 索引
    - 添加向量（支持 int8 量化）
    - 高速检索（返回内部 ID）
    - 保存/加载索引和 id_map

    使用示例：
        >>> manager = LSHIndexManager(dim=384, nbits=1536)
        >>> manager.add_vectors(vectors, documents)
        >>> manager.save_index()
        >>> manager.load_index()
        >>> ids = manager.search(query_vector, k=10)
    """

    def __init__(
        self,
        dim: int = LSH_DIM,
        nbits: int = LSH_NBITS,
        use_int8_quantization: bool = True,
    ):
        """
        初始化 LSH 索引

        Args:
            dim: 向量维度（gte-small 模型输出 384）
            nbits: LSH 位数（建议 dim × 4）
            use_int8_quantization: 是否使用 int8 量化（减少内存）
        """
        self.dim = dim
        self.nbits = nbits
        self.use_int8_quantization = use_int8_quantization

        # 内部 ID 到 Document 的映射
        self.id_map: Dict[int, Document] = {}

        # FAISS 索引
        self._index = None

        # 统计信息
        self._total_vectors = 0
        self._total_bytes = 0

    @property
    def index(self):
        """获取 FAISS 索引对象"""
        if self._index is None:
            self._index = faiss.IndexLSH(self.dim, self.nbits)
        return self._index

    def add_documents(self, documents: List[Document], embeddings: np.ndarray) -> int:
        """
        添加文档到 LSH 索引（新接口）
        
        Args:
            documents: Document 列表（含 metadata）
            embeddings: 对应的向量数组 (N, dim)
        
        Returns:
            成功添加的文档数
        """
        if len(documents) != len(embeddings):
            raise ValueError(f"文档数量 ({len(documents)}) 与向量数量 ({len(embeddings)}) 不匹配")
        
        if embeddings.shape[1] != self.dim:
            raise ValueError(f"向量维度 ({embeddings.shape[1]}) 与索引维度 ({self.dim}) 不匹配")
        
        # 量化向量
        vectors_quantized = self._quantize_vector(embeddings)
        
        # 添加到 FAISS 索引
        self.index.add(vectors_quantized)
        
        # 更新 id_map
        start_idx = self._total_vectors
        for i, doc in enumerate(documents):
            self.id_map[start_idx + i] = doc
        
        self._total_vectors += len(documents)
        
        # 更新内存占用估计
        if self.use_int8_quantization:
            self._total_bytes = vectors_quantized.nbytes + len(self.id_map) * 100
        else:
            self._total_bytes = vectors_quantized.nbytes + len(self.id_map) * 100
        
        logger.info(f"添加 {len(documents)} 个文档到 LSH 索引（当前总计 {self._total_vectors} 个）")
        
        return len(documents)
    
    def _quantize_vector(self, vectors: np.ndarray) -> np.ndarray:
        """
        向量子量化
        
        Args:
            vectors: 原始向量数组
        
        Returns:
            量化后的向量数组
        """
        if self.use_int8_quantization:
            return (vectors * 255).astype(np.uint8)
        return vectors.astype(np.float32)
    
    def get_scores(self, query_vec: np.ndarray, k: int = 20) -> List[float]:
        """
        获取检索结果的相似度分数
        
        Args:
            query_vec: 查询向量
            k: 返回数量
        
        Returns:
            相似度分数列表（1 / (1 + hamming_distance)）
        """
        query_quantized = self._quantize_vector(query_vec.reshape(1, -1))
        distances, ids = self.index.search(query_quantized, k)
        scores = [1.0 / (1.0 + d) for d in distances[0]]
        return scores
    
    def add_vectors(
        self,
        vectors: np.ndarray,
        documents: List[Document],
        progress_file: Optional[Path] = None,
    ):
        """
        添加向量到 LSH 索引

        Args:
            vectors: 向量数组，shape (N, dim)
            documents: 对应的 Document 列表
            progress_file: 进度文件路径（用于断点续传）
        """
        if len(vectors) != len(documents):
            raise ValueError(f"向量数量 ({len(vectors)}) 与文档数量 ({len(documents)}) 不匹配")

        if len(vectors) == 0:
            logger.warning("没有向量可添加")
            return

        # int8 量化
        if self.use_int8_quantization:
            # 归一化到 [0, 255]
            vectors_norm = (vectors * 255).astype(np.uint8)
            vectors_quantized = vectors_norm
        else:
            vectors_quantized = vectors.astype(np.float32)

        # 添加到 FAISS 索引
        self.index.add(vectors_quantized)

        # 更新 id_map
        for i, doc in enumerate(documents):
            self.id_map[self._total_vectors + i] = doc

        self._total_vectors += len(documents)

        # 更新内存占用估计
        if self.use_int8_quantization:
            self._total_bytes = vectors_quantized.nbytes + len(self.id_map) * 100
        else:
            self._total_bytes = vectors_quantized.nbytes + len(self.id_map) * 100

        # 保存进度
        if progress_file:
            self._save_progress(progress_file)

        logger.info(f"添加 {len(documents)} 个向量到 LSH 索引，当前总计 {self._total_vectors} 个")

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        return_distances: bool = False,
    ) -> List[int]:
        """
        搜索最相似的 k 个向量

        Args:
            query_vector: 查询向量
            k: 返回数量
            return_distances: 是否返回距离

        Returns:
            内部 ID 列表（如果 return_distances=True，则返回 (ids, distances) 元组）
        """
        if self._index is None:
            raise RuntimeError("索引未初始化，请先调用 add_vectors")

        if k > self._total_vectors:
            k = self._total_vectors

        # 归一化查询向量
        query_norm = query_vector / np.linalg.norm(query_vector)

        # int8 量化
        if self.use_int8_quantization:
            query_quantized = (query_norm * 255).astype(np.uint8)
        else:
            query_quantized = query_norm.astype(np.float32)

        # 搜索
        distances, ids = self.index.search(query_quantized.reshape(1, -1), k)

        if return_distances:
            return ids[0].tolist(), distances[0].tolist()
        else:
            return ids[0].tolist()

    def get_document(self, internal_id: int) -> Optional[Document]:
        """
        根据 internal_id 获取 Document 对象

        Args:
            internal_id: 内部 ID

        Returns:
            Document 对象，如果不存在返回 None
        """
        return self.id_map.get(internal_id)

    def get_documents(self, internal_ids: List[int]) -> List[Document]:
        """
        根据 internal_id 列表获取 Document 对象列表

        Args:
            internal_ids: 内部 ID 列表

        Returns:
            Document 对象列表（保持顺序）
        """
        return [self.id_map.get(uid) for uid in internal_ids if uid in self.id_map]

    def save_index(self, index_path: Optional[Path] = None):
        """
        保存索引和 id_map 到文件

        Args:
            index_path: 索引文件路径（默认使用 LSH_INDEX_PATH）
        """
        if index_path is None:
            index_path = LSH_INDEX_PATH

        index_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存 FAISS 索引
        faiss.write_index(self.index, str(index_path))

        # 保存 id_map
        with open(ID_MAP_PATH, "wb") as f:
            pickle.dump(self.id_map, f)

        logger.info(f"LSH 索引已保存到 {index_path}")

    def load_index(self, index_path: Optional[Path] = None) -> bool:
        """
        从文件加载索引和 id_map

        Args:
            index_path: 索引文件路径（默认使用 LSH_INDEX_PATH）

        Returns:
            加载成功返回 True，否则 False
        """
        if index_path is None:
            index_path = LSH_INDEX_PATH

        if not index_path.exists():
            logger.warning(f"索引文件不存在: {index_path}")
            return False

        # 加载 FAISS 索引
        self._index = faiss.read_index(str(index_path))

        # 加载 id_map
        try:
            with open(ID_MAP_PATH, "rb") as f:
                self.id_map = pickle.load(f)
            self._total_vectors = len(self.id_map)
            logger.info(f"LSH 索引已从 {index_path} 加载，共 {self._total_vectors} 个向量")
            return True
        except Exception as e:
            logger.error(f"加载 id_map 失败: {e}")
            return False

    def _save_progress(self, progress_file: Path):
        """
        保存进度到文件

        Args:
            progress_file: 进度文件路径
        """
        progress_file.parent.mkdir(parents=True, exist_ok=True)

        progress_data = {
            "total_vectors": self._total_vectors,
            "total_bytes": self._total_bytes,
            "id_map_size": len(self.id_map),
        }

        with open(progress_file, "w", encoding="utf-8") as f:
            import json
            json.dump(progress_data, f, indent=2)

    def clear(self):
        """清空索引和 id_map"""
        self._index = None
        self.id_map = {}
        self._total_vectors = 0
        self._total_bytes = 0
        logger.info("LSH 索引已清空")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取索引统计信息

        Returns:
            统计信息字典
        """
        return {
            "dim": self.dim,
            "nbits": self.nbits,
            "total_vectors": self._total_vectors,
            "total_bytes": self._total_bytes,
            "id_map_size": len(self.id_map),
        }


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    import faiss
    from rag_config import LSH_DIM, LSH_NBITS

    # 创建测试数据
    np.random.seed(42)
    dim = 384
    nbits = 1536
    n_vectors = 1000

    vectors = np.random.randn(n_vectors, dim).astype(np.float32)
    documents = [
        Document(
            page_content=f"这是文档 {i}",
            metadata={"source": f"doc_{i}.txt", "global_order": i}
        )
        for i in range(n_vectors)
    ]

    print("=" * 60)
    print("LSH 索引管理器测试")
    print("=" * 60)

    # 创建管理器
    manager = LSHIndexManager(dim=dim, nbits=nbits)

    # 添加向量
    print(f"\n添加 {n_vectors} 个向量...")
    manager.add_vectors(vectors, documents)
    print(f"统计信息: {manager.get_stats()}")

    # 保存索引
    test_index_path = Path(__file__).parent.parent / "storage" / "test_lsh.index"
    manager.save_index(test_index_path)

    # 加载索引
    print("\n加载索引...")
    manager2 = LSHIndexManager(dim=dim, nbits=nbits)
    success = manager2.load_index(test_index_path)
    print(f"加载成功: {success}")

    # 搜索
    print("\n测试搜索...")
    query_vector = np.random.randn(dim).astype(np.float32)
    ids = manager.search(query_vector, k=5)
    print(f"搜索结果 (前5个 ID): {ids}")

    # 获取文档
    docs = manager.get_documents(ids[:5])
    print(f"\n获取文档:")
    for i, doc in enumerate(docs):
        print(f"  [{i}] global_order={doc.metadata['global_order']}, "
              f"source={doc.metadata['source']}, "
              f"content={doc.page_content}")

    # 清理测试文件
    test_index_path.unlink(missing_ok=True)
    (ID_MAP_PATH).unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
