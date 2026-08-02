import sqlite3
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
conn = sqlite3.connect('D:/class/project-config/langchain-rag/storage/knowledge_base.db')
conn.row_factory = sqlite3.Row

# 检查 source_chapter 为空的情况
cursor = conn.execute("SELECT id, name, type, source_chapter FROM entities WHERE source_chapter IS NULL OR source_chapter = ''")
rows = cursor.fetchall()
print(f"没有 source_chapter 的实体数: {len(rows)}")
for r in rows[:10]:
    d = dict(r)
    print(f"  {d['id']}: {d['name'][:30]}... type={d['type']}")

# 检查单字实体
cursor = conn.execute("SELECT id, name, type FROM entities WHERE length(name) <= 2")
rows = cursor.fetchall()
print(f"\n2字及以下的实体数: {len(rows)}")
for r in rows[:10]:
    d = dict(r)
    print(f"  {d['id']}: {d['name']} type={d['type']}")

# 检查包含标点的实体
import re
cursor = conn.execute("SELECT id, name, type FROM entities")
rows = cursor.fetchall()
punctuated = []
for r in rows:
    d = dict(r)
    if re.search(r'[，。！？、；：""''（）【】《》\-\*]', d['name']):
        punctuated.append(d)
print(f"\n包含标点的实体数: {len(punctuated)}")
for e in punctuated[:10]:
    print(f"  {e['id']}: {e['name']}")

conn.close()
