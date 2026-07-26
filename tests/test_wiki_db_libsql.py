"""
测试 WikiDB（libsql 版本）
"""

import pytest
import tempfile
from pathlib import Path
import sqlite3
import json

from rag_core.wiki_db_libsql import WikiDB


class TestWikiDB:
    """测试 WikiDB 基本操作"""

    @pytest.fixture
    def wiki_db(self):
        """创建临时数据库"""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test_wiki.db"
        wiki = WikiDB(db_path=str(db_path))
        yield wiki
        # 清理
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init(self, wiki_db):
        """测试初始化"""
        assert wiki_db is not None
        assert Path(wiki_db.db_path).exists()

    def test_add_entity(self, wiki_db):
        """测试添加实体"""
        # 添加实体
        result = wiki_db.add_entity(
            name="方源",
            entity_type="人物",
            properties={"主修": "力道", "资质": "甲等9成"}
        )

        assert result is True

        # 检查实体是否存在
        entity = wiki_db.get_entity("方源")
        assert entity is not None
        assert entity["name"] == "方源"
        assert entity["type"] == "人物"
        assert entity["properties"]["主修"] == "力道"

    def test_duplicate_entity(self, wiki_db):
        """测试重复实体"""
        # 添加第一个实体
        wiki_db.add_entity(name="方源", entity_type="人物")

        # 添加重复实体
        result = wiki_db.add_entity(name="方源", entity_type="人物")
        assert result is False

    def test_add_relationship(self, wiki_db):
        """测试添加关系"""
        # 添加两个实体
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_entity(name="全力以赴蛊", entity_type="蛊虫")

        # 添加关系
        result = wiki_db.add_relationship(
            source_name="方源",
            target_name="全力以赴蛊",
            rel_type="持有"
        )

        assert result is True

        # 获取关系
        entity_id = wiki_db.get_entity_id("方源")
        relations = wiki_db.get_relations(entity_id)
        assert len(relations) > 0
        assert relations[0]["rel_type"] == "持有"
        assert "全力以赴蛊" in relations[0]["target_name"]

    def test_get_entity_id(self, wiki_db):
        """测试获取实体 ID"""
        wiki_db.add_entity(name="方源", entity_type="人物")

        entity_id = wiki_db.get_entity_id("方源")
        assert entity_id is not None
        assert entity_id.startswith("entity_")

    def test_entity_not_found(self, wiki_db):
        """测试实体不存在"""
        entity = wiki_db.get_entity("不存在的实体")
        assert entity is None

    def test_add_fact(self, wiki_db):
        """测试添加事实"""
        # 添加实体
        wiki_db.add_entity(name="方源", entity_type="人物")

        # 添加事实
        result = wiki_db.add_fact(
            entity_name="方源",
            fact_type="主修",
            fact_value="力道"
        )

        assert result is True

        # 获取事实
        entity_id = wiki_db.get_entity_id("方源")
        facts = wiki_db.get_facts_for_entity(entity_id)
        assert len(facts) > 0
        assert facts[0]["fact_value"] == "力道"

    def test_get_entity_history(self, wiki_db):
        """测试获取实体历史"""
        wiki_db.add_entity(name="方源", entity_type="人物")

        # 添加历史版本
        entity_id = wiki_db.get_entity_id("方源")

        # 通过修正实体属性来添加历史版本
        wiki_db.add_entity(
            name="方源",
            entity_type="人物",
            properties={"主修": "力道", "境界": "炼气一层"}
        )

        history = wiki_db.get_entity_history("方源")
        assert isinstance(history, list)

    def test_get_stats(self, wiki_db):
        """测试获取统计信息"""
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_entity(name="白凝冰", entity_type="人物")
        wiki_db.add_entity(name="全力以赴蛊", entity_type="蛊虫")

        stats = wiki_db.get_stats()
        assert stats["total_entities"] >= 3
        assert "人物" in stats["entities"]
        assert "蛊虫" in stats["entities"]

    def test_approve_entity(self, wiki_db):
        """测试批准实体"""
        wiki_db.add_entity(name="方源", entity_type="人物")

        entity_id = wiki_db.get_entity_id("方源")
        result = wiki_db.approve_entity(entity_id)
        assert result is True

    def test_approve_relation(self, wiki_db):
        """测试批准关系"""
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_entity(name="全力以赴蛊", entity_type="蛊虫")
        wiki_db.add_relationship("方源", "全力以赴蛊", "持有")

        entity_id = wiki_db.get_entity_id("方源")
        relations = wiki_db.get_relations(entity_id)
        assert len(relations) > 0

        result = wiki_db.approve_relation(str(relations[0]["id"]))
        assert result is True

    def test_delete_relation(self, wiki_db):
        """测试删除关系"""
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_entity(name="全力以赴蛊", entity_type="蛊虫")
        wiki_db.add_relationship("方源", "全力以赴蛊", "持有")

        entity_id = wiki_db.get_entity_id("方源")
        relations = wiki_db.get_relations(entity_id)

        if relations:
            result = wiki_db.delete_relation(relations[0]["id"])
            assert result is True

        # 验证关系已删除
        relations_after = wiki_db.get_relations(entity_id)
        assert len(relations_after) == 0

    def test_remove_fact(self, wiki_db):
        """测试删除事实"""
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_fact("方源", "主修", "力道")

        entity_id = wiki_db.get_entity_id("方源")
        facts = wiki_db.get_facts_for_entity(entity_id)

        if facts:
            result = wiki_db.remove_fact(facts[0]["id"])
            assert result is True

        # 验证事实已删除
        facts_after = wiki_db.get_facts_for_entity(entity_id)
        assert len(facts_after) == 0

    def test_get_entity_relations(self, wiki_db):
        """测试获取实体关系网络"""
        wiki_db.add_entity(name="方源", entity_type="人物")
        wiki_db.add_entity(name="白凝冰", entity_type="人物")
        wiki_db.add_relationship("方源", "白凝冰", "盟友")

        entity_id = wiki_db.get_entity_id("方源")
        relations = wiki_db.get_entity_relations(entity_id)

        assert "relations" in relations
        assert len(relations["relations"]) > 0
        assert relations["relations"][0]["rel_type"] == "盟友"


class TestWikiDBEdgeCases:
    """边缘情况测试"""

    @pytest.fixture
    def wiki_db(self):
        """创建 Wiki 数据库"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "wiki.db"
            wiki = WikiDB(db_path=str(db_path))
            yield wiki

    def test_empty_database(self, wiki_db):
        """测试空数据库"""
        id = wiki_db.get_entity_id("方源")
        assert id is None

        entity = wiki_db.get_entity("方源")
        assert entity is None

    def test_relationship_with_nonexistent_entities(self, wiki_db):
        """测试不存在的实体的关系"""
        result = wiki_db.add_relationship("不存在的实体1", "不存在的实体2", "持有")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])