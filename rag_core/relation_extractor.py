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


def _result(source: str, **over) -> Dict:
    """统一的返回结构（键名沿用既有契约，不新增同义键）"""
    base = {
        "source": source,
        "entities_count": 0,
        "relations_extracted": 0,
        "relations_imported": 0,
        "error": None,
        "skipped": False,
    }
    base.update(over)
    return base


def _skip_llm() -> bool:
    """导入阶段跳过 LLM（导入脚本会设置 SKIP_LLM=1）"""
    return os.environ.get("SKIP_LLM", "0") == "1"


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

    return _result(source)
