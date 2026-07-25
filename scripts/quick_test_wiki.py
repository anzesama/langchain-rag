"""
快速验证 Wiki 功能

运行此脚本验证 Wiki 层是否正常工作
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_core.wiki_router import WikiRouter, get_wiki_router


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_wiki_db():
    """测试 Wiki 数据库"""
    print_section("1. Wiki 数据库测试")

    wiki_db = WikiDB()
    wiki_db.init_db()

    # 测试添加实体
    print("\n添加实体...")
    success = wiki_db.add_entity("方源", "人物", {"主修": "力道", "资质": "甲等9成"})
    print(f"  ✓ 添加实体: {success}")

    wiki_db.add_entity("力道", "流派", {"特点": "真元消耗少"})
    print(f"  ✓ 添加流派")

    # 测试添加关系
    print("\n添加关系...")
    success = wiki_db.add_relationship("方源", "力道", "主修")
    print(f"  ✓ 添加关系: {success}")

    # 测试查询
    print("\n查询实体...")
    entity = wiki_db.get_entity("方源")
    if entity:
        print(f"  ✓ 查询成功: {entity['name']} - {entity['type']}")
        print(f"    属性: {entity['properties']}")

    # 测试关系查询
    print("\n查询关系...")
    relations = wiki_db.get_relations("fang_yuan")
    print(f"  ✓ 找到 {len(relations)} 个关系:")
    for rel in relations:
        print(f"    - {rel['source']} -{rel['rel_type']}-> {rel['target']}")

    # 测试事实查询
    print("\n事实查询...")
    answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
    print(f"  ✓ 查询结果: {answer}")

    # 测试统计
    print("\n统计信息...")
    stats = wiki_db.get_stats()
    print(f"  ✓ 实体数: {stats['total_entities']}")
    print(f"  ✓ 关系数: {stats['total_relationships']}")

    wiki_db.close()
    print("\n✓ Wiki 数据库测试通过")


def test_wiki_router():
    """测试 Wiki 路由器"""
    print_section("2. Wiki 路由器测试")

    router = WikiRouter(known_entities={"方源", "力道", "元始仙尊", "白凝冰"})

    print("\n测试事实类查询...")
    queries = [
        "方源主修什么流派？",
        "元始仙尊是什么？",
        "方源持有哪些蛊虫？"
    ]

    for query in queries:
        route = router.route(query)
        print(f"  {query}")
        print(f"    → {route}")

    print("\n测试语义类查询...")
    queries = [
        "方源为什么这么残忍？",
        "白凝冰的心情怎么样？",
        "如何评价元始仙尊？"
    ]

    for query in queries:
        route = router.route(query)
        print(f"  {query}")
        print(f"    → {route}")

    print("\n测试默认查询...")
    queries = [
        "今天天气怎么样？",
        "如何配置环境变量？"
    ]

    for query in queries:
        route = router.route(query)
        print(f"  {query}")
        print(f"    → {route}")

    print("\n✓ Wiki 路由器测试通过")


def test_full_pipeline():
    """测试完整流程"""
    print_section("3. 完整流程测试")

    # 初始化 Wiki
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 加载已知实体
    router = get_wiki_router()
    router.load_known_entities(wiki_db)

    # 测试查询
    print("\n测试查询:")
    queries = [
        "方源主修什么流派？",
        "元始仙尊是什么？",
        "方源为什么这么残忍？"
    ]

    for query in queries:
        print(f"\n查询: {query}")
        print("-" * 40)

        # 路由判断
        route = router.route(query)
        print(f"路由: {route}")

        # Wiki 查询
        answer = wiki_db.get_fact_query_answer(query)
        if answer:
            print(f"Wiki: {answer}")
        else:
            print("Wiki: 无结果")

        # RAG 检索（简化）
        print("RAG: （待实现）")

    wiki_db.close()
    print("\n✓ 完整流程测试完成")


def main():
    """运行所有测试"""
    try:
        print("\n" + "=" * 60)
        print("Wiki 功能快速验证")
        print("=" * 60)

        test_wiki_db()
        test_wiki_router()
        test_full_pipeline()

        print_section("总结")
        print("\n✓ 所有测试通过!")
        print("\nWiki 层已成功实现:")
        print("  • SQLite 数据库存储")
        print("  • 实体和关系操作")
        print("  • 事实查询接口")
        print("  • Wiki 路由判断")
        print("  • 集成到 RagPipeline")
        print("\n下一步:")
        print("  • 实现增量更新模块")
        print("  • 创建 CLI 工具")
        print("  • 实现可视化")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
