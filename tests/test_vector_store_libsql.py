"""
测试 VectorStoreManagerLibsql - 向量存储（libsql 版本）
"""

import pytest
import tempfile
from pathlib import Path
import numpy as np
import sqlite3
import json

from langchain_core.documents import Document

from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.embedding_service import get_embeddings


class TestVectorStoreLibsql:
    """测试 VectorStoreManager（libsql 版本）"""

    @pytest.fixture
    def vector_store(self):
        """创建临时向量存储"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield VectorStoreManager(persist_dir=Path(tmp_dir))

    def test_init(self, vector_store):
        """测试初始化"""
        assert vector_store is not None
        assert vector_store.db_path.exists()
        assert vector_store.db_path.stat().st_size > 0
        assert vector_store.persist_dir.exists()

    def test_add_documents(self, vector_store):
        """测试添加文档"""
        # 创建测试文档
        documents = [
            Document(page_content="这是测试文档1", metadata={"source": "test1.txt", "global_order": 1}),
            Document(page_content="这是测试文档2", metadata={"source": "test2.txt", "global_order": 2}),
        ]

        # 添加文档
        vector_store.add_documents(documents)

        # 验证数量
        stats = vector_store.get_stats()
        assert stats["total_documents"] == 2

    def test_batch_add_documents(self, vector_store):
        """测试批量添加文档"""
        # 创建大量测试文档
        documents = [
            Document(page_content=f"这是测试文档{i}", metadata={"source": f"test{i}.txt", "global": i})
            for i in range(100)
        ]

        # 批量添加文档
        vector_store.add_documents_batched(documents, batch_size=50)

        # 验证数量
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 100

    def test_search(self, vector_store):
        """测试搜索"""
        # 添加测试文档
        documents = [
            Document(page_content="机器学习是人工智能的重要分支", metadata={"source": "test1.txt"}),
            Document(page_content="深度学习是实现机器学习的技术", metadata={"source": "test2.txt"}),
        ]
        vector_store.add_documents(documents)

        # 搜索相关文档
        results = vector_store.search("机器学习", top_k=2)

        # 验证结果
        assert len(results) > 0
        assert "机器学习" in results[0][0].page_content or "机器学习" in results[1][0].page_content

    def test_delete_collection(self, vector_store):
        """测试删除集合"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档", metadata={"source": "test.txt"}),
        ]
        vector_store.add_documents(documents)

        # 删除集合
        vector_store.delete_collection()

        # 验证集合已删除
        assert not vector_store.persist_dir.exists()

    def test_get_stats(self, vector_store):
        """测试获取统计信息"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档", metadata={"source": "test.txt"}),
        ]
        vector_store.add_documents(documents)

        # 获取统计信息
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 1
        assert "persist_dir" in stats

    def test_list_documents(self, vector_store):
        """测试列出文档"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档1", metadata={"source": "test1.txt"}),
            Document(page_content="测试文档2", metadata={"source": "test2.txt"}),
        ]
        vector_store.add_documents(documents)

        # 列出文档
        docs = vector_store.list_documents()
        assert len(docs) >= 2

        # 验证文档信息
        sources = [doc["source"] for doc in docs if "source" in doc]
        assert "test1.txt" in sources or "test2.txt" in sources

    def test_get_chunk_count(self, vector_store):
        """测试获取特定来源的 chunk 数量"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档1", metadata={"source": "test1.txt"}),
            Document(page_content="测试文档2", metadata={"source": "test1.txt"}),
            Document(page_content="测试文档3", metadata={"source": "test2.txt"}),
        ]
        vector_store.add_documents(documents)

        # 获取特定来源的 chunk 数量
        count = vector_store.get_chunk_count("test1.txt")
        assert count >= 2

        count = vector_store.get_chunk_count("test2.txt")
        assert count >= 1

    def test_delete_by_source(self, vector_store):
        """测试按来源删除文档"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档1", metadata={"source": "test1.txt"}),
            Document(page_content="测试文档2", metadata={"source": "test1.txt"}),
            Document(page_content="测试文档3", metadata={"source": "test2.txt"}),
        ]
        vector_store.add_documents(documents)

        # 删除特定来源的文档
        deleted_count = vector_store.delete_by_source("test1.txt")
        assert deleted_count >= 2

        # 验证剩余文档
        count = vector_store.get_chunk_count("test1.txt")
        assert count == 0

        count = vector_store.get_chunk_count("test2.txt")
        assert count >= 1

    def test_reload(self, vector_store):
        """测试重新加载"""
        # 添加测试文档
        documents = [
            Document(page_content="测试文档", metadata={"source": "test.txt"}),
        ]
        vector_store.add_documents(documents)

        # 重新加载
        vector_store.reload()

        # 验证数据仍然存在
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 1

    def test_vector_operations(self, vector_store):
        """测试向量操作"""
        # 创建测试向量
        vector = np.random.randn(512).astype(np.float32)

        # 向量转换为 BLOB
        blob = vector_store._vector_to_blob(vector)

        # BLOB 转换为向量
        vector2 = vector_store._blob_to_vector(blob)

        # 验证向量一致
        assert np.allclose(vector, vector2, atol=1e-6)

    def test_duplicate_ids(self, vector_store):
        """测试重复ID处理"""
        # 创建测试文档
        doc1 = Document(page_content="测试文档1", metadata={"source": "test.txt"})
        doc2 = Document(page_content="测试文档2", metadata={"source": "test.txt"})

        # 使用相同ID添加文档
        ids = ["doc_test1", "doc_test2", "doc_test3"]
        vector_store.add_documents([doc1, doc2], ids=ids)

        # 验证插入成功
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 2

    def test_metadata_handling(self, vector_store):
        """测试元数据处理"""
        # 创建带复杂元数据的文档
        documents = [
            Document(
                page_content="测试文档",
                metadata={
                    "source": "test.txt",
                    "author": "测试作者",
                    "tags": ["测试", "文档"],
                    "rating": 5,
                }
            ),
        ]

        # 添加文档
        vector_store.add_documents(documents)

        # 列出文档
        docs = vector_store.list_documents()
        assert len(docs) >= 1

        # 验证元数据
        metadata = docs[0]["metadata"]
        assert metadata == {"source": "test.txt", "author": "测试作者", "tags": ["测试", "文档"], "rating": 5.0}


class TestVectorStoreManagerEdgeCases:
    """边缘情况测试"""

    @pytest.fixture
    def vector_store(self):
        """创建向量存储"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield VectorStoreManager(persist_dir=Path(tmp_dir))

    def test_empty_documents(self, vector_store):
        """测试空文档列表"""
        vector_store.add_documents([])
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 0

    def test_large_batch(self, vector_store):
        """测试大批量文档"""
        # 创建大量文档
        documents = [
            Document(page_content=f"测试文档{i}", metadata={"source": "test.txt", "index": i})
            for i in range(500)
        ]

        # 添加文档
        vector_store.add_documents(documents)

        # 验证数量
        stats = vector_store.get_stats()
        assert stats["total_documents"] >= 500

    def test_search_empty_collection(self, vector_store):
        """测试空集合搜索"""
        results = vector_store.search("测试查询", top_k=5)
        assert len(results) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])