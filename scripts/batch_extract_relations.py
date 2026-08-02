"""
批量关系抽取脚本
遍历所有文档，使用 LLM 提取实体间关系并导入数据库

用法:
    python scripts/batch_extract_relations.py --source README.md
    python scripts/batch_extract_relations.py --all
"""
import argparse
import os
import sys
from typing import List, Dict

import requests

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag_config import logger, AGNES_API_KEY, AGNES_API_BASE
from rag_core.llm_refiner import LLMRefiner
from rag_core.wiki_db_libsql import WikiDB

# 如果 rag_config 中的 API 密钥有效，优先使用，否则尝试 Pi 配置中的智谱
import json as _json
_pi_config_path = os.path.expanduser("~/.pi/agent/models.json")
_BACKUP_API_KEY = AGNES_API_KEY
_BACKUP_API_BASE = AGNES_API_BASE
try:
    with open(_pi_config_path, 'r') as f:
        _pi_models = _json.load(f)
    _providers = _pi_models.get('providers', {})
    # 优先 AGNES，失效则用智谱
    _agn_cfg = _providers.get('agnes-custom', {})
    _zhipu_cfg = _providers.get('zhipu', {})
    AGNES_API_KEY = _agn_cfg.get('apiKey', AGNES_API_KEY)
    AGNES_API_BASE = _agn_cfg.get('baseUrl', AGNES_API_BASE)
except Exception:
    pass

DOMAIN_TYPE = os.getenv("DOMAIN_TYPE", "machine-learning")


def get_db_connection():
    """获取数据库连接"""
    from rag_core.wiki_db_libsql import WikiDB
    return WikiDB("storage/knowledge_base.db").connect()


def extract_relations_for_source(source: str, domain: str = DOMAIN_TYPE, chunks: List[Dict] = None) -> Dict:
    """
    为指定来源提取关系

    Args:
        source: 文档来源（chunks.source）
        domain: 领域类型
        chunks: chunks 列表（可选，如果提供则直接使用，否则从数据库查询）

    Returns:
        {
            "source": str,
            "entities_count": int,
            "relations_extracted": int,
            "relations_imported": int,
            "error": str | None
        }
    """
    logger.info(f"========== 开始处理来源: {source} ==========")

    conn = get_db_connection()
    try:
        # 提取文件名（用于匹配 entities.source_chapter）
        source_basename = os.path.basename(source)

        # 查询实体
        entity_rows = conn.execute(
            "SELECT id, name, type FROM entities WHERE source_chapter = ? OR source_chapter = ?",
            (source, source_basename)
        ).fetchall()

        entities = [dict(row) for row in entity_rows]
        logger.info(f"找到 {len(entities)} 个实体")

        if not entities:
            logger.warning(f"来源 {source} 无实体，跳过")
            return {
                "source": source,
                "entities_count": 0,
                "relations_extracted": 0,
                "relations_imported": 0,
                "error": "No entities found"
            }

        # 获取 chunks
        if chunks is None:
            chunk_rows = conn.execute(
                "SELECT text_content FROM chunks WHERE source = ?",
                (source,)
            ).fetchall()
            chunks_text_list = [row[0] for row in chunk_rows]
        else:
            chunks_text_list = [c.get('chunk_text') or c.get('page_content', '') for c in chunks]

        chunks_for_llm = [{'page_content': t, 'chunk_text': t} for t in chunks_text_list]
        chunks_text = "\n\n".join(chunks_text_list)
        logger.info(f"找到 {len(chunks_text_list)} 个 chunks，总字符数: {len(chunks_text)}")

        # 初始化 LLM refiner（优先 AGNES，密钥无效则回退智谱）
        use_agnes = AGNES_API_KEY and 'xxxxxxxx' not in AGNES_API_KEY
        if use_agnes:
            refiner = LLMRefiner(
                endpoint=AGNES_API_BASE,
                api_key=AGNES_API_KEY,
                model="agnes-2.0-flash",
                domain=domain
            )
        else:
            try:
                with open(os.path.expanduser("~/.pi/agent/models.json"), 'r') as f:
                    _cfg = __import__('json').load(f)
                _zp = _cfg['providers']['zhipu']
                refiner = LLMRefiner(
                    endpoint=_zp['baseUrl'],
                    api_key=_zp['apiKey'],
                    model="glm-4.7-flash",
                    domain=domain
                )
                logger.info("使用智谱 GLM-4.7-Flash 替代 AGNES")
            except Exception:
                refiner = LLMRefiner(
                    endpoint=AGNES_API_BASE,
                    api_key=AGNES_API_KEY,
                    model="agnes-2.0-flash",
                    domain=domain
                )

        # 提取关系（传入字典列表，_build_relation_prompt 需要 chunk_text/page_content 键）
        result = refiner.extract_relations(chunks_for_llm, entities)
        relations = result.get('relations', [])
        logger.info(f"提取到 {len(relations)} 条关系")

        if not relations:
            return {
                "source": source,
                "entities_count": len(entities),
                "relations_extracted": 0,
                "relations_imported": 0,
                "error": "No relations extracted"
            }

        # 导入关系
        wiki_db = WikiDB("storage/knowledge_base.db")
        wiki_db.init_db()
        imported = 0
        duplicates = 0

        for rel in relations:
            src = rel.get('source', '').strip()
            tgt = rel.get('target', '').strip()
            rel_type = rel.get('type', '关联')

            try:
                # 如果实体不存在，先创建
                for name in [src, tgt]:
                    if not wiki_db.get_entity_id(name):
                        wiki_db.add_entity(name, '未知', source_chapter=source_basename)

                # 添加关系
                wiki_db.add_relationship(src, tgt, rel_type, source_chapter=source_basename)
                imported += 1
            except Exception as e:
                logger.warning(f"导入失败 ({src} -> {tgt}): {e}")
                duplicates += 1

        logger.info(f"成功导入 {imported} 条关系")

        return {
            "source": source,
            "entities_count": len(entities),
            "relations_extracted": len(relations),
            "relations_imported": imported,
            "error": None
        }

    except Exception as e:
        logger.error(f"处理来源 {source} 时出错: {e}")
        import traceback
        traceback.print_exc()
        return {
            "source": source,
            "entities_count": 0,
            "relations_extracted": 0,
            "relations_imported": 0,
            "error": str(e)
        }
    finally:
        conn.close()

        # 初始化 LLM refiner（优先 AGNES，密钥无效则回退智谱）
        use_agnes = AGNES_API_KEY and 'xxxxxxxx' not in AGNES_API_KEY
        if use_agnes:
            refiner = LLMRefiner(
                endpoint=AGNES_API_BASE,
                api_key=AGNES_API_KEY,
                model="agnes-2.0-flash",
                domain=domain
            )
        else:
            try:
                with open(os.path.expanduser("~/.pi/agent/models.json"), 'r') as f:
                    _cfg = __import__('json').load(f)
                _zp = _cfg['providers']['zhipu']
                refiner = LLMRefiner(
                    endpoint=_zp['baseUrl'],
                    api_key=_zp['apiKey'],
                    model="glm-4.7-flash",
                    domain=domain
                )
                logger.info("使用智谱 GLM-4.7-Flash 替代 AGNES")
            except Exception:
                refiner = LLMRefiner(
                    endpoint=AGNES_API_BASE,
                    api_key=AGNES_API_KEY,
                    model="agnes-2.0-flash",
                    domain=domain
                )

        # 提取关系（传入字典列表，_build_relation_prompt 需要 chunk_text/page_content 键）
        result = refiner.extract_relations(chunks_for_llm, entities)
        relations = result.get('relations', [])
        logger.info(f"提取到 {len(relations)} 条关系")

        if not relations:
            return {
                "source": source,
                "entities_count": len(entities),
                "relations_extracted": 0,
                "relations_imported": 0,
                "error": "No relations extracted"
            }

        # Imported
        wiki_db = WikiDB("storage/knowledge_base.db")
        wiki_db.init_db()
        imported = 0
        duplicates = 0

        for rel in relations:
            src = rel.get('source', '').strip()
            tgt = rel.get('target', '').strip()
            rel_type = rel.get('type', '关联')

            try:
                # 如果实体不存在，先创建
                for name in [src, tgt]:
                    if not wiki_db.get_entity_id(name):
                        wiki_db.add_entity(name, '未知', source_chapter=source_basename)

                # 添加关系
                wiki_db.add_relationship(src, tgt, rel_type, source_chapter=source_basename)
                imported += 1
            except Exception as e:
                logger.warning(f"Imported失败 ({src} -> {tgt}): {e}")
                duplicates += 1

        logger.info(f"成功导入 {imported} 条关系")

        return {
            "source": source,
            "entities_count": len(entities),
            "relations_extracted": len(relations),
            "relations_imported": imported,
            "error": None
        }

    except Exception as e:
        logger.error(f"处理来源 {source} 时出错: {e}")
        import traceback
        traceback.print_exc()
        return {
            "source": source,
            "entities_count": 0,
            "relations_extracted": 0,
            "relations_imported": 0,
            "error": str(e)
        }
    finally:
        conn.close()


def batch_extract_all(domain: str = DOMAIN_TYPE, limit: int = None) -> Dict[str, Dict]:
    """
    批量提取所有来源的关系

    Args:
        domain: 领域类型
        limit: 限制处理的来源数量（None = 全部）

    Returns:
        {source: result_dict}
    """
    conn = get_db_connection()
    try:
        # 查询所有来源
        rows = conn.execute(
            "SELECT DISTINCT source FROM chunks ORDER BY source"
        ).fetchall()

        sources = [row['source'] for row in rows]

        if limit:
            sources = sources[:limit]

        logger.info(f"找到 {len(sources)} 个来源，准备批量Extracted")

        results = {}
        for i, source in enumerate(sources, 1):
            logger.info(f"\n进度: {i}/{len(sources)}")
            results[source] = extract_relations_for_source(source, domain)

        return results

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="批量关系抽取")
    parser.add_argument("--source", type=str, help="指定来源文件（chunks.source）")
    parser.add_argument("--all", action="store_true", help="处理所有来源")
    parser.add_argument("--limit", type=int, help="限制处理的来源数量")
    parser.add_argument("--domain", type=str, default=DOMAIN_TYPE, help="领域类型")

    args = parser.parse_args()

    if not args.source and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.source:
        results = {args.source: extract_relations_for_source(args.source, args.domain)}
    else:
        results = batch_extract_all(args.domain, args.limit)

    # 打印汇总
    print("\n" + "=" * 60)
    print("批量关系抽取汇总")
    print("=" * 60)

    total_entities = 0
    total_extracted = 0
    total_imported = 0
    failed = 0

    for source, result in results.items():
        status = "OK" if not result.get('error') else "FAIL"
        print(f"\n{status} {source}")
        print(f"   Entities: {result['entities_count']}")
        print(f"   Extracted: {result['relations_extracted']}")
        print(f"   Imported: {result['relations_imported']}")

        if result.get('error'):
            print(f"   Error: {result['error']}")

        total_entities += result['entities_count']
        total_extracted += result['relations_extracted']
        total_imported += result['relations_imported']
        if result.get('error'):
            failed += 1

    print("\n" + "-" * 60)
    print(f"总计: {len(results)} 个来源")
    print(f"Entities: {total_entities}")
    print(f"Extracted: {total_extracted}")
    print(f"Imported: {total_imported}")
    if failed > 0:
        print(f"失败: {failed}")


if __name__ == "__main__":
    main()
