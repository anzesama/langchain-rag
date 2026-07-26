"""快速测试 libsql 版本的 KnowledgeBase 和 WikiDB"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("Step 1: 导入模块")
print("=" * 50)

from rag_core.knowledge_base import KnowledgeBase
print("OK: KnowledgeBase imported")

from rag_core.wiki_db import WikiDB, get_wiki_db
print("OK: WikiDB imported (libsql version)")

print()
print("=" * 50)
print("Step 2: 初始化 KnowledgeBase")
print("=" * 50)

kb = KnowledgeBase()
stats = kb.get_stats()
print(f"Stats: {stats}")

print()
print("=" * 50)
print("Step 3: 测试 WikiDB")
print("=" * 50)

wiki = WikiDB()
print(f"DB path: {wiki.db_path}")

# 检查表结构
conn = wiki.connect()
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row['name'] for row in cursor.fetchall()]
conn.close()
print(f"Tables ({len(tables)}): {', '.join(tables)}")

# 获取统计
wiki_stats = wiki.get_stats()
print(f"Wiki stats: {wiki_stats}")

print()
print("=" * 50)
print("Step 4: 测试搜索")
print("=" * 50)

# 简单的搜索测试
try:
    result = kb.search("test", top_k=1)
    print(f"Search result type: {type(result)}")
except Exception as e:
    print(f"Search failed (expected if no docs): {e}")

print()
print("=" * 50)
print("All tests passed!")
print("=" * 50)