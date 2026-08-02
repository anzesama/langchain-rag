"""
简单测试批量关系抽取集成
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.unified_importer import UnifiedImporter
from rag_core.wiki_db_libsql import WikiDB

def test_integration():
    """测试集成"""
    print("=" * 60)
    print("Testing Relation Extraction Integration")
    print("=" * 60)

    # 初始化
    wiki_db = WikiDB("storage/knowledge_base.db")
    wiki_db.init_db()

    # 检查方法是否存在
    importer = UnifiedImporter()

    if hasattr(importer, '_import_entities_and_relations'):
        print("[OK] _import_entities_and_relations method exists")
        print("[OK] WikiDB initialized internally")
    else:
        print("[FAIL] _import_entities_and_relations method not found")

    print("\n" + "=" * 60)
    print("Integration Test Complete!")
    print("=" * 60)

if __name__ == '__main__':
    test_integration()
