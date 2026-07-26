import sys, json, sqlite3
from pathlib import Path

project_root = Path('D:/class/project-config/langchain-rag')
sys.path.insert(0, str(project_root))

conn = sqlite3.connect(str(project_root / 'storage/knowledge_base.db'))
conn.row_factory = sqlite3.Row

# Get entities
cur = conn.execute("SELECT * FROM entities")
entities = [dict(r) for r in cur.fetchall()]

# Get relations with joined names
cur = conn.execute('''
    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
           src.name as source_name, tgt.name as target_name
    FROM relationships r
    LEFT JOIN entities src ON r.source_id = src.id
    LEFT JOIN entities tgt ON r.target_id = tgt.id
''')
relations = [dict(r) for r in cur.fetchall()]

print(f"Entities: {len(entities)}")
for e in entities[:3]:
    print(f"  id={e['id']} name={e['name']} type={e.get('type','?')}")
print(f"Relations: {len(relations)}")
for r in relations:
    print(f"  {r['source_name']} --[{r['rel_type']}]--> {r['target_name']} (source_id={r['source_id']}, target_id={r['target_id']})")

conn.close()