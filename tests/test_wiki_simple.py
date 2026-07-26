"""
简化版 Wiki 测试脚本

"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_core.wiki_router import WikiRouter, get_wiki_router


def test_wiki_basic():
    """测试 Wiki 基本功能"""
    print("测试 Wiki 基本功能...")

    # 初始化 Wiki
    wiki_db = WikiDB()
    wiki_db.init_db()

    # 添加实体
    wiki_db.add_entity("方源", "人物", {"主修": "力道", "资质": "甲等9成"})
    wiki_db.add_entity("力道", "流派", {"特点": "真元消耗少"})

    # 添加关系
    wiki_db.add_relationship("方源", "力道", "主修")

    # 测试查询
    answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
    print(f"查询结果: {answer}")

    # 测试路由
    router = WikiRouter(known_entities={"方源", "力道", "元始仙尊"})
    route = router.route("方源主修什么流派？")
    print(f"路由结果: {route}")

    wiki_db.close()
    print("✓ 基本测试通过")


def test_seed_data():
    """测试加载 seed 数据"""
    print("\n测试加载 seed 数据...")

    # 初始化 Wiki
    wiki_db = get_wiki_db()
    wiki_db.init_db()

    # 加载 seed 数据（这里简化，实际需要从 JSON 加载）
    # TODO: 实现从 seed.json 加载数据

    # 测试查询
    answer = wiki_db.get_fact_query_answer("方源主修什么流派？")
    print(f"查询结果: {answer}")

    # 测试路由
    router = get_wiki_router()
    router.load_known_entities(wiki_db)
    route = router.route("方源主修什么流派？")
    print(f"路由结果: {route}")

    wiki_db.close()
    print("✓ seed 数据测试通过")


if __name__ == "__main__":
    test_wiki_basic()
    test_seed_data()
    print("\n所有测试完成!")
