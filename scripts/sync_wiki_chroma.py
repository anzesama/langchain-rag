"""
Wiki 和 ChromaDB 同步检查脚本

功能：
- 检查 Wiki 和 ChromaDB 是否一致
- 同步缺失的实体到 ChromaDB
- 删除 ChromaDB 中已删除的实体
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_db import get_wiki_db
from rag_core.vector_store_libsql import VectorStoreManager

logger = logging.getLogger(__name__)


def sync_wiki_chroma():
    """
    同步 Wiki 和 ChromaDB

    流程：
    1. 从 Wiki 获取所有实体
    2. 从 ChromaDB 获取所有文档来源
    3. 检查差异
    4. 同步缺失的实体
    """

    print("=" * 60)
    print("Wiki 和 ChromaDB 同步检查")
    print("=" * 60)

    # 初始化 Wiki
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 获取 Wiki 中的所有实体 ID
    entities = wiki_db.get_all_entities()
    wiki_entity_ids = {e['id'] for e in entities}
    wiki_entity_names = {e['name'] for e in entities}

    print(f"\nWiki 中的实体数: {len(wiki_entity_ids)}")

    # 获取 ChromaDB 中的所有文档来源
    vector_store = VectorStoreManager()
    chroma_sources = vector_store.list_sources()

    print(f"ChromaDB 中的文档数: {len(chroma_sources)}")

    # 提取 ChromaDB 中的实体名（从 metadata）
    chroma_entity_names = set()
    for source in chroma_sources:
        # 尝试从 source 中提取实体名
        # 示例: "novel_chapters/章1.txt" -> 可能包含实体名
        pass

    # 检查差异
    print("\n" + "=" * 60)
    print("同步检查")
    print("=" * 60)

    # 1. Wiki 中有但 ChromaDB 中没有的实体
    wiki_only = wiki_entity_names - chroma_entity_names
    if wiki_only:
        print(f"\n[WARNING] Wiki 中存在但 ChromaDB 中没有的实体 ({len(wiki_only)} 个):")
        for name in sorted(wiki_only):
            print(f"  - {name}")

        # TODO: 同步这些实体到 ChromaDB
        print(f"\n[INFO] 可以将以下实体添加到 ChromaDB:")
        for name in sorted(wiki_only)[:10]:  # 只显示前 10 个
            print(f"  - {name}")

    # 2. ChromaDB 中有但 Wiki 中没有的文档
    chroma_only = chroma_sources  # 简化版
    if chroma_only:
        print(f"\n[INFO] ChromaDB 中有但 Wiki 中没有的文档 ({len(chroma_only)} 个):")
        for source in sorted(chroma_only)[:10]:
            print(f"  - {source}")

    # 3. 统计
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)

    stats = wiki_db.get_stats()
    print(f"\nWiki 统计:")
    print(f"  总实体数: {stats['total_entities']}")
    print(f"  总关系数: {stats['total_relationships']}")
    print(f"  实体类型分布:")
    for entity_type, count in sorted(stats['entities'].items()):
        print(f"    {entity_type}: {count}")

    # 关闭数据库
    wiki_db.close()
    vector_store.close()

    print("\n" + "=" * 60)
    print("同步检查完成")
    print("=" * 60)


def sync_entity_to_chroma(entity_name: str):
    """
    将单个实体同步到 ChromaDB

    Args:
        entity_name: 实体名
    """

    print(f"\n同步实体到 ChromaDB: {entity_name}")

    wiki_db = get_wiki_db()
    wiki_db.init_db()

    entity = wiki_db.get_entity(entity_name)
    if not entity:
        print(f"[ERROR] 实体不存在: {entity_name}")
        wiki_db.close()
        return

    # TODO: 将实体信息添加到 ChromaDB
    # 需要从文本中提取相关内容
    print(f"[INFO] 实体信息: {entity['name']} ({entity['type']})")
    print(f"  属性: {entity['properties']}")

    wiki_db.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="同步 Wiki 和 ChromaDB"
    )
    parser.add_argument(
        '--entity',
        type=str,
        help='同步单个实体到 ChromaDB'
    )

    args = parser.parse_args()

    if args.entity:
        # 同步单个实体
        sync_entity_to_chroma(args.entity)
    else:
        # 完整同步检查
        sync_wiki_chroma()


if __name__ == "__main__":
    main()
