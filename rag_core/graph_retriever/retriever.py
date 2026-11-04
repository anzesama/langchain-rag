"""
图检索：WikiDB 实体匹配 + 图库扩展

检索流程：
1. 实体名模糊匹配
2. 直接 SQL 查所有关系
3. 图扩展
4. Fact List
"""

import sqlite3
from pathlib import Path
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent.parent.parent / 'storage' / 'knowledge_base.db')


def _load_all() -> tuple:
    """从 SQL 加载所有实体和关系"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    entities = {}
    for row in conn.execute('SELECT id, name, type FROM entities').fetchall():
        entities[row[1]] = {'id': row[0], 'name': row[1], 'type': row[2]}

    relations = []
    for row in conn.execute('''
        SELECT r.rel_type, e1.name as source, e2.name as target
        FROM relationships r
        JOIN entities e1 ON r.source_id = e1.id
        JOIN entities e2 ON r.target_id = e2.id
    ''').fetchall():
        relations.append({'source': row['source'], 'target': row['target'], 'rel_type': row['rel_type']})
    conn.close()
    return list(entities.values()), relations


def _fuzzy_match(query: str, entities: List[Dict], top_k: int = 10) -> List[str]:
    matches = []
    q = query.lower()
    for e in entities:
        n = e['name'].lower()
        score = 0
        if q == n:
            score = 3
        elif q in n or n in q:
            score = 2
        elif any(w in n for w in q.split()):
            score = 1
        if score > 0:
            matches.append((e['name'], score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches[:top_k]]


def retrieve(query: str, top_k: int = 10, hops: int = 1) -> Dict:
    if not query or not query.strip():
        return {"seed_relations": [], "expanded_nodes": [], "expanded_edges": [], "fact_list": []}

    entities, all_rels = _load_all()

    # 1. 匹配
    seed_names = set(_fuzzy_match(query, entities, top_k))
    if not seed_names:
        return {"seed_relations": [], "expanded_nodes": [], "expanded_edges": [], "fact_list": []}

    # 2. 直接找关系
    seed_relations = [r for r in all_rels if r['source'] in seed_names or r['target'] in seed_names]

    # 3. 构建索引用于图扩展
    name_to_rels = {}
    for r in all_rels:
        name_to_rels.setdefault(r['source'], []).append(r)
        name_to_rels.setdefault(r['target'], []).append({'source': r['target'], 'target': r['source'], 'rel_type': r['rel_type']})

    expanded_nodes = {}
    expanded_edges = []
    visited = set(seed_names)
    frontier = set(seed_names)

    for _ in range(hops):
        next_frontier = set()
        for name in frontier:
            for rel in name_to_rels.get(name, []):
                neighbor = rel['source'] if rel['target'] == name else rel['target']
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    visited.add(neighbor)
                    expanded_nodes[neighbor] = {'name': neighbor, 'type': '未知'}
                expanded_edges.append({'source': rel['source'], 'target': rel['target'], 'rel_type': rel['rel_type']})
        frontier = next_frontier

    # 4. fact list
    fact_list = [f"{r['source']} --{r['rel_type']}--> {r['target']}" for r in seed_relations + expanded_edges]

    return {
        "seed_relations": seed_relations,
        "expanded_nodes": list(expanded_nodes.values()),
        "expanded_edges": expanded_edges,
        "fact_list": fact_list
    }


def to_prompt_context(result: Dict) -> str:
    if not result.get('fact_list'):
        return ""
    lines = ["【已知知识图谱事实】"]
    for f in result['fact_list'][:30]:
        lines.append(f"- {f}")
    return "\n".join(lines)