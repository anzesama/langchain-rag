"""关系抽取唯一入口

设计与边界：
- 本模块是「取 chunks → LLM 抽关系 → 写入 WikiDB」的**唯一**实现
  （此前该逻辑在 scripts/batch_extract_relations.py 中出现两份，
   其一被错误地塞进 finally:，导致 LLM 跑两遍 + 吞异常；已收敛到此处）。
- **所有 DB 访问**都经 VectorStoreManager / get_wiki_db()，
  二者已被 tests/conftest.py 隔离，故本模块**不**自行拼接 DB 路径。
- SKIP_LLM=1 时完全不构造 LLMRefiner（导入阶段不打 LLM）。
"""
import os
from typing import Dict, List, Optional

from rag_config import logger
from rag_core.llm_refiner import LLMRefiner
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.wiki_db_libsql import get_wiki_db

#: 领域类型（可用 DOMAIN_TYPE 环境变量覆盖）
DEFAULT_DOMAIN = os.getenv("DOMAIN_TYPE", "machine-learning")

#: AGNES 占位密钥判定片段（沿用既有逻辑）
_PLACEHOLDER = "xxxxxxxx"


def _result(
    source: str,
    entities_count: int = 0,
    relations_extracted: int = 0,
    relations_imported: int = 0,
    error: Optional[str] = None,
    skipped: bool = False,
) -> Dict:
    """统一的返回结构（键名沿用既有契约，不新增同义键）"""
    return {
        "source": source,
        "entities_count": entities_count,
        "relations_extracted": relations_extracted,
        "relations_imported": relations_imported,
        "error": error,
        "skipped": skipped,
    }


def _skip_llm() -> bool:
    """导入阶段跳过 LLM（导入脚本会设置 SKIP_LLM=1）"""
    return os.environ.get("SKIP_LLM", "0").strip() == "1"


def _normalize_chunks(chunks: Optional[List]) -> List[Dict]:
    """把 dict / langchain Document 统一成 [{'chunk_text': …}]"""
    out: List[Dict] = []
    for c in chunks or []:
        if isinstance(c, dict):
            text = c.get("chunk_text") or c.get("text_content") or c.get("page_content") or ""
        else:
            text = getattr(c, "page_content", "") or ""
        if text:
            out.append({"chunk_text": text, "page_content": text})
    return out


def extract_relations_for_source(
    source: str, domain: Optional[str] = None, chunks: Optional[List] = None
) -> Dict:
    """为指定来源抽取并写入关系（唯一入口）

    Args:
        source: 精确来源（chunks.source）
        domain: 领域类型，None 时用 DEFAULT_DOMAIN
        chunks: 可选，已取好的 chunks；None 时内部按 source 查询

    Returns:
        {source, entities_count, relations_extracted, relations_imported, error, skipped}
    """
    domain = domain or DEFAULT_DOMAIN

    if _skip_llm():
        logger.info(f"SKIP_LLM=1，跳过关系抽取: {source}")
        return _result(source, skipped=True)

    try:
        if chunks is None:
            chunks = VectorStoreManager().get_chunks_by_source(source)
        chunks_for_llm = _normalize_chunks(chunks)

        entities = _load_entities(source)
        if not entities:
            logger.warning(f"来源 {source} 无实体，跳过关系抽取")
            return _result(source, error="No entities found")

        if not chunks_for_llm:
            logger.warning(f"来源 {source} 无 chunks，跳过关系抽取")
            return _result(source, entities_count=len(entities), error="No chunks found")

        refiner = _build_refiner(domain)
        result = refiner.extract_relations(chunks_for_llm, entities)
        relations = result.get("relations", [])
        logger.info(f"提取到 {len(relations)} 条关系")

        wiki_db = get_wiki_db()
        imported = _import_relations(wiki_db, relations, os.path.basename(source))
        logger.info(f"成功导入 {imported} 条关系")

        return _result(
            source,
            entities_count=len(entities),
            relations_extracted=len(relations),
            relations_imported=imported,
        )
    except Exception as e:
        logger.warning(f"关系抽取失败(source={source}): {type(e).__name__}: {e}")
        return _result(source, error=f"{type(e).__name__}: {e}")


def _load_entities(source: str) -> List[Dict]:
    """查询该来源的实体（source 与 basename 双匹配，沿用既有语义）"""
    wiki_db = get_wiki_db()
    conn = wiki_db.connect()
    try:
        rows = conn.execute(
            "SELECT id, name, type FROM entities WHERE source_chapter = ? OR source_chapter = ?",
            (source, os.path.basename(source)),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _build_refiner(domain: str) -> LLMRefiner:
    """构造 refiner：AGNES 优先，密钥无效则回退智谱，再回退 AGNES（策略单点）"""
    from rag_config import AGNES_API_BASE, AGNES_API_KEY

    if AGNES_API_KEY and _PLACEHOLDER not in AGNES_API_KEY:
        return LLMRefiner(
            endpoint=AGNES_API_BASE, api_key=AGNES_API_KEY, model="agnes-2.0-flash", domain=domain
        )
    try:
        import json

        cfg_path = os.path.expanduser("~/.pi/agent/models.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            zp = json.load(f)["providers"]["zhipu"]
        logger.info("使用智谱 GLM-4.7-Flash 替代 AGNES")
        return LLMRefiner(
            endpoint=zp["baseUrl"], api_key=zp["apiKey"], model="glm-4.7-flash", domain=domain
        )
    except Exception as e:
        logger.warning(f"读取智谱配置失败，回退 AGNES: {type(e).__name__}: {e}")
        return LLMRefiner(
            endpoint=AGNES_API_BASE, api_key=AGNES_API_KEY, model="agnes-2.0-flash", domain=domain
        )


def _import_relations(wiki_db, relations: List[Dict], source_basename: str) -> int:
    """把关系写入 WikiDB（实体不存在时自动创建），返回成功条数"""
    imported = 0
    failed = 0
    for rel in relations:
        src = (rel.get("source") or "").strip()
        tgt = (rel.get("target") or "").strip()
        rel_type = rel.get("type") or "关联"
        if not src or not tgt:
            continue
        try:
            for name in (src, tgt):
                if not wiki_db.get_entity_id(name):
                    wiki_db.add_entity(name, "未知", source_chapter=source_basename)
            wiki_db.add_relationship(src, tgt, rel_type, source_chapter=source_basename)
            imported += 1
        except Exception as e:
            failed += 1
            logger.warning(f"导入失败 ({src} -> {tgt}): {type(e).__name__}: {e}")
    if failed:
        logger.warning(f"关系导入部分失败: 成功 {imported} / 失败 {failed}（共 {imported + failed} 条有效）")
    return imported


def extract_all_sources(domain: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Dict]:
    """对所有已入库来源批量抽取关系

    Args:
        domain: 领域类型
        limit: 限制处理的来源数量（None = 全部；0 = 一个都不处理）
    """
    try:
        sources = VectorStoreManager().list_sources()
    except Exception as e:
        logger.error(f"列出来源失败: {type(e).__name__}: {e}")
        return {}

    if limit is not None:
        sources = sources[:limit]

    logger.info(f"找到 {len(sources)} 个来源，准备批量抽取")
    results: Dict[str, Dict] = {}
    for i, source in enumerate(sources, 1):
        logger.info(f"\n进度: {i}/{len(sources)}")
        results[source] = extract_relations_for_source(source, domain)
    return results
