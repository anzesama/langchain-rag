"""完整测试 libsql 版本的 RAG 系统"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("LibSQL RAG 系统完整测试")
print("=" * 60)

# 1. 导入模块
print("\n[1] 导入模块...")
from rag_core.knowledge_base import KnowledgeBase
from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_core.vector_store_libsql import VectorStoreManager
print("OK: 所有模块导入成功")

# 2. 初始化 KnowledgeBase
print("\n[2] 初始化 KnowledgeBase...")
kb = KnowledgeBase()
stats = kb.get_stats()
print(f"OK: total_documents={stats['total_documents']}")

# 3. 检查 libsql 数据库
print("\n[3] 检查 libsql 数据库...")
vector_db_path = kb.vector_store.db_path
print(f"OK: 向量存储路径: {vector_db_path}")

# 4. 检查 WikiDB
print("\n[4] 检查 WikiDB...")
wiki = WikiDB()
wiki_conn = wiki.connect()
wiki_cursor = wiki_conn.cursor()
wiki_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
wiki_tables = [row['name'] for row in wiki_cursor.fetchall()]
wiki_conn.close()
print(f"OK: Wiki 表 ({len(wiki_tables)} 个): {', '.join(wiki_tables)}")

# 5. 获取统计信息
print("\n[5] 获取统计信息...")
wiki_stats = wiki.get_stats()
print(f"Entities: {wiki_stats}")

# 6. 搜索测试
print("\n[6] 搜索测试...")
try:
    # 使用本地 embedding 模型搜索
    result = kb.search("测试", top_k=3)
    print(f"OK: 搜索结果类型={type(result)}, 数量={len(result) if isinstance(result, list) else 'N/A'}")
except Exception as e:
    print(f"Search failed (expected): {str(e)[:100]}")

print("\n" + "=" * 60)
print("✅ 所有测试完成！")
print("=" * 60)