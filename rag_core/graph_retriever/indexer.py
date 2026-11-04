"""
将 WikiDB 中的关系存入向量库

关系格式：source --[rel_type]--> target | description
"""

from typing import List
import logging
from langchain_core.documents import Document

from rag_core.wiki_db_libsql import WikiDB
from rag_core.vector_store_libsql import VectorStoreManager
from .utils import encode_relation

logger = logging.getLogger(__name__)


def index_all_relations():
    """
    从 WikiDB 读取所有关系，写入向量库

    流程：
    1. 从 WikiDB 获取所有实体和关系
    2. 对每个关系编码为文本格式
    3. 写入向量库（libsql）
    4. 记录索引统计信息
    """
    wiki_db = WikiDB()
    vector_store = VectorStoreManager()

    # 获取所有实体（用于查类型）
    entities = {e['name']: e['type'] for e in wiki_db.get_all_entities()}
    logger.info(f"获取到 {len(entities)} 个实体")

    # 获取所有关系
    relations = wiki_db.get_all_relationships()
    logger.info(f"获取到 {len(relations)} 条关系")

    indexed_count = 0
    for rel in relations:
        source = rel['source_name']
        target = rel['target_name']
        rel_type = rel['rel_type']

        # 构建描述（如果有 properties 里的描述则用，否则组合）
        desc = rel.get('properties', {}).get('description', f"{source} 与 {target} 存在 {rel_type} 关系")

        # 编码为文本
        content = encode_relation(source, target, rel_type, desc)

        # 写入向量库
        try:
            vector_store.add_documents([
                Document(
                    page_content=content,
                    metadata={
                        "type": "relation",
                        "source": source,
                        "target": target,
                        "rel_type": rel_type,
                        "description": desc,
                        "source_type": entities.get(source, "未知"),
                        "target_type": entities.get(target, "未知")
                    }
                )
            ])
            indexed_count += 1
        except Exception as e:
            logger.error(f"索引关系失败 {source} --[{rel_type}]--> {target}: {e}")

    logger.info(f"索引完成: {indexed_count}/{len(relations)} 条关系已写入向量库")

    return indexed_count
