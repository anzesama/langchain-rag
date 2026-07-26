import json, urllib.request, sys

def api(path, method='GET', data=None):
    url = f'http://127.0.0.1:5000{path}'
    req = urllib.request.Request(url, method=method)
    req.add_header('Content-Type', 'application/json')
    if data:
        req.data = json.dumps(data).encode('utf-8')
    try:
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read().decode('utf-8'))
        print(f'  {method} {path} -> OK: {json.dumps(body, ensure_ascii=False)[:200]}')
        return body
    except Exception as e:
        print(f'  {method} {path} -> ERROR: {e}')
        return None

print('1. Get entities...')
ents = api('/api/entities')
e1 = ents['entities'][0]
e2 = ents['entities'][1]
print(f'   e1={e1["name"]}({e1["id"]})')
print(f'   e2={e2["name"]}({e2["id"]})')

print('2. Create relation via API...')
result = api('/api/relations', 'POST', {
    'source_name': e1['name'],
    'target_name': e2['name'],
    'rel_type': '测试关系', 
    'source_chapter': '测试'
})

print('\n3. Get relations after create...')
rels = api('/api/relations')
print(f'   total: {rels["total"]}')
for r in rels['relations']:
    print(f'   {r.get("source_name","?")} --[{r.get("rel_type","?")}]--> {r.get("target_name","?")}')