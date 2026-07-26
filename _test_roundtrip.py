"""
模拟完整前端的 saveRelation 流程：
1. 获取两个实体名
2. 创建关系 (like saveRelation does)
3. 立即读取关系确认创建
4. 再读一次确认持久化
"""
import json, urllib.request

BASE = 'http://127.0.0.1:5000'

def api(method, path, data=None):
    url = f'{BASE}{path}'
    req = urllib.request.Request(url, method=method)
    req.add_header('Content-Type', 'application/json')
    if data:
        req.data = json.dumps(data, ensure_ascii=False).encode('utf-8')
    resp = urllib.request.urlopen(req)
    body = json.loads(resp.read().decode('utf-8'))
    return body

# 1. Get entities
ents = api('GET', '/api/entities')
e1 = ents['entities'][0]
e2 = ents['entities'][1]
print(f'entities: {e1["name"]} (id={e1["id"]}), {e2["name"]} (id={e2["id"]})')

# 2. Get current relations
rels_before = api('GET', '/api/relations')
cnt_before = rels_before['total']
print(f'relations before: {cnt_before}')

# 3. Create: exactly like saveRelation() JS
create_data = {
    'source_name': e1['name'],
    'target_name': e2['name'],
    'rel_type': '朋友',
    'source_chapter': '',
}
print(f'creating relation: {json.dumps(create_data, ensure_ascii=False)}')
result = api('POST', '/api/relations', create_data)
print(f'result: {result}')

# 4. Check after
rels_after = api('GET', '/api/relations')
cnt_after = rels_after['total']
print(f'relations after: {cnt_after}')

# 5. List all
for r in rels_after['relations']:
    print(f'  id={r["id"]:2d}  {r["source_name"]} -({r["rel_type"]})-> {r["target_name"]}')

# 6. Check that entities still load same count
ents_after = api('GET', '/api/entities')
print(f'\nentities after: {len(ents_after["entities"])}')

# 7. Also delete a relation then check it's gone
old_id = rels_after['relations'][-1]['id']
print(f'\ndeleting relation id={old_id}')
del_result = api('DELETE', f'/api/relations/{old_id}')
print(f'delete result: {del_result}')
rels_final = api('GET', '/api/relations')
print(f'relations final: {rels_final["total"]}')