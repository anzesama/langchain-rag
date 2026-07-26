"""检查实体数据"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from rag_core.wiki_db import WikiDB

wiki = WikiDB()

entities = wiki.get_all_entities()
print(f"Total entities: {len(entities)}")
for e in entities[:5]:
    print(f"  ID={e['id']} | Name={e['name']} | Type={e['type']}")

print(f"... and {len(entities)-5} more")

wiki.close()