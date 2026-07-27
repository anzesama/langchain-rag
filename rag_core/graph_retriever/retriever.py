"""
图检索：向量召回 + 图库扩展

检索流程：
1. 向量检索关系句
2. 解析实体
3. 2-hop 图库扩展
4. 生成 Fact List
"""

from typing import List, Dict, Set
import logging
from langchain_core.documents import Document

from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.wiki_db_libsql import WikiDB
from .utils import decode_relation

logger = logging.getLogger(__name__)


def retrieve(query: str, top_k: int = 10, hops: int = 2) -> Dict:
    """
    图检索主入口

    Args:
        query: 用户查询
        top_k: 向量召回的候选数
        hops: 图扩展跳数

    Returns:
        {
            "seed_relations": [{"source": "...", "target": "...", "rel_type": "..."}],
            "expanded_nodes": [{"name": "...", "type": "..."}],
            "expanded_edges": [{"source": "...", "target": "...", "rel_type": "..."}],
            "fact_list": ["CatBoost 属于 Yandex 公司", ...]
        }
    """
    vector_store = VectorStoreManager()
    wiki_db = WikiDB()

    # 1. 向量检索关系句
    results = vector_store.search(query, top_k=top_k)

    seed_relations = []
    seed_entity_names = set()

    for r in results:
        decoded = decode_relation(r.page_content)
        if decoded:
            seed_relations.append(decoded)
            seed_entity_names.add(decoded['source'])
            seed_entity_names.add(decoded['target'])

    logger.info(f"向量召回 {len(seed_relations)} 条关系，涉及 {len(seed_entity_names)} 个实体")

    # 2. 图库扩展（2-hop）
    expanded_nodes = {}
    expanded_edges = []
    visited = set(seed_entity_names)
    frontier = set(seed_entity_names)

    for _ in range(hops):
        next_frontier = set()
        for entity_name in frontier:
            rels = wiki_db.get_relations(entity_name)
            for rel in rels:
                neighbor = rel['target'] if rel['source'] == entity_name else rel['source']
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
                    expanded_nodes[neighbor] = {
                        'name': neighbor,
                        'type': rel.get('target_type', '未知')
                    }
                expanded_edges.append({
                    'source': rel['source'],
                    'target': rel['target'],
                    'rel_type': rel['rel_type']
                })
        frontier = next_frontier

    logger.info(f"图扩展完成: {len(expanded_nodes)} 个新节点, {len(expanded_edges)} 条边")

    # 3. 生成 Fact List（用于 LLM Prompt）
    fact_list = []
    for rel in seed_relations + expanded_edges:
        fact_list.append(f"{rel['source']} --{rel['rel_type']}--> {rel['target']}")

    return {
        "seed_relations": seed_relations,
        "expanded_nodes": list(expanded_nodes.values()),
        "expanded_edges": expanded_edges,
        "fact_list": fact_list
    }


def to_prompt_context(result: Dict) -> str:
    """
    将检索结果转换为 Prompt 上下文（Fact List 格式）

    Args:
        result: retrieve() 返回的结果

    Returns:
        Prompt 上下文文本
    """
    if not result['fact_list']:
        return ""

    lines = ["【已知知识图谱事实】"]
    for fact in result['fact_list'][:30]:  # 限制数量防止 token 爆炸
        lines.append(f"- {fact}")
    return "\n".join(lines)
