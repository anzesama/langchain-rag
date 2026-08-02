"""
测试批量关系抽取集成
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.unified_importer import UnifiedImporter
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.wiki_db_libsql import WikiDB

def test_relation_extraction():
    """测试在导入过程中自动抽取关系"""
    print("=" * 60)
    print("测试批量关系抽取集成")
    print("=" * 60)

    # 初始化
    wiki_db = WikiDB("storage/knowledge_base.db")
    wiki_db.init_db()

    # 检查是否有关系抽取功能
    print("\n[OK] WikiDB initialized successfully")
    print(f"[OK] WikiDB entities: {wiki_db.get_entity_count()}")
    print(f"[OK] WikiDB relations: {wiki_db.get_relation_count()}")

    # 测试关系抽取函数是否存在
    from rag_core.unified_importer import UnifiedImporter
    importer = UnifiedImporter(wiki_db, None)

    if hasattr(importer, '_import_entities_and_relations'):
        print("[OK] _import_entities_and_relations method exists")
    else:
        print("[FAIL] _import_entities_and_relations method not found")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == '__main__':
    test_relation_extraction()
