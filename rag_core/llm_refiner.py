"""
LLM 精炼模块 — 精筛 jieba 实体 + 关系提取 + 领域分类系统

用法:
    refiner = LLMRefiner(endpoint, api_key, model, domain='machine-learning')
    result = refiner.refine_entities(entities, chunks)   # 精筛实体
    result = refiner.extract_relations(chunks, entities)  # 提取关系
"""
import json
import re
import time
from typing import Dict, List, Any

import requests

from rag_config import logger


DOMAIN_CONFIGS = {
    'machine-learning': {
        'label': '机器学习/数据科学',
        'entity_types': ['算法', '模型', '方法', '概念', '指标', '工具', '框架', '数据集'],
        'rel_types': ['使用', '基于', '对比', '包含', '实现', '改进', '防止', '优化', '定义', '关联'],
        'entity_review_rules': '关键词型术语，2-20字，不能是描述句或句子片段',
        'relation_check': 'source/target 在实体列表中，关系在上下文中明确出现',
    },
    'novel': {
        'label': '小说/剧情',
        'entity_types': ['人物', '蛊虫', '势力', '流派', '地点', '境界', '法宝'],
        'rel_types': ['持有', '属于', '主修', '师承', '盟友', '敌对', '击杀', '使用', '控制'],
        'entity_review_rules': '小说命名实体，2-8汉字，不能含英文/数字，必须是有意义的角色或概念',
        'rel_check': 'source/target 在实体列表中，关系在剧情中明确出现',
    },
    'ontology': {
        'label': '技术概念本体',
        'entity_types': ['概念', '属性', '实例', '关系', '约束', '公理'],
        'rel_types': ['is-a', 'has-part', 'instance-of', 'related-to', 'constrained-by'],
        'entity_review_rules': '概念型术语，不应含数字或特例，必须抽象',
        'rel_check': 'source/target 在实体列表中，本体论约束',
    },
}


class LLMRefiner:
    """LLM 精炼实体 + 提取关系"""

    def __init__(self, endpoint: str, api_key: str, model: str, domain: str = 'machine-learning'):
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.domain = domain
        self.config = DOMAIN_CONFIGS.get(domain, DOMAIN_CONFIGS['machine-learning'])

    # 预处理：规则过滤明显垃圾实体（减少 LLM 负担）
    NOISE_PATTERNS = [
        (r'^.{0,1}$', '单字'),  # 零字或单字
        (r'^[0-9\s\.\-_]+$', '纯数字符号'),
        (r'^get$|^set$|^the$|^and$|^for$|^not$|^has$|^new$|^int$|^def$|^let$|^var$|^try$|^end$|^nil$|^use$|^add$', '无意义英文单词'),
        (r'^df$|^pd$|^np$|^os$|^id$', 'Python 缩写'),
        (r'^col$|^ord$|^fold$|^Hot$|^train$|^import$', '代码片段 / 英文碎片'),
        (r'^import|^from\s|^print\(', '代码行'),
        (r'^[a-zA-Z]{1,3}$', '极短英文'),
        (r'^[:,：，\-\{\}\[\]\|\\/#&*+~^@%!=<>]+$', '纯符号'),
    ]
    WEAK_NAMES = {'time', 'day', 'year', 'data', 'text', 'file', 'key', 'sum', 'val', 'num',
                  'idx', 'sql', 'csv', 'http', 'url', 'img', 'img', 'usr', 'dev','db',
                  'config', 'test', 'case', 'max', 'min', 'set', 'get', 'opt', 'item',
                  'list', 'dict', 'cat', 'dog', 'type', 'model', 'method', 'calc',
                  'score', 'valid', 'step'}

    def _prefilter(self, entities: list) -> tuple:
        """返回 (valid_entities, removed_entities)"""
        import re
        valid, removed = [], []
        for e in entities:
            name = e.get('name', '').strip()
            # 过短/过长
            if len(name) < 2 or len(name) > 20:
                removed.append(e); continue
            # 纯符号/数字
            if re.match(r'^[0-9\W_]+$', name):
                removed.append(e); continue
            # 包含标点（除非是合理的书名/术语）
            if re.search(r'[，。、；：！？【】《》（）\-\*]', name):
                removed.append(e); continue
            # 英文弱词
            if len(name) <= 3 and name.lower() in self.WEAK_NAMES:
                removed.append(e); continue
            # 规则匹配
            matched = False
            for pat, _reason in self.NOISE_PATTERNS:
                if re.search(pat, name):
                    removed.append(e); matched = True; break
            if matched: continue
            # 包含虚词（大多数句子）
            if len(name) > 8 and re.search('[\u7684\u4e86\u5728\u662f\u8457\u300d\u300f]', name):
                removed.append(e); continue
            valid.append(e)
        return valid, removed

    def _build_refine_prompt(self, entities: list, chunks: list) -> str:
        """构建精筛实体 prompt（含 id + name + 类型 + 严格标准 + few-shot）"""
        import json as _json
        entity_items = [
            {"id": e.get('id', ''), "name": e.get('name', ''),
             "type": e.get('type', '未分类')}
            for e in entities
        ]
        entity_json = _json.dumps(entity_items, ensure_ascii=False, indent=2)

        chunk_text = '\n'.join(
            f"[Chunk {i}] {c.get('chunk_text', c.get('page_content', ''))[:300]}"
            for i, c in enumerate(chunks[:3])
        ) if chunks else '(无上下文)'

        config = self.config
        return f"""你是一个知识图谱实体清洗专家。对给定的候选实体进行筛选和分类。

## 输入说明
每个实体包含：id（唯一标识）、name（名称）、type（当前类型）。
同时附原文片段供参考。

## 判断规则
1. **删除（标为 removed）** 如果实体：
   - 是完整句子（长度>20字且含"的/了/在/是/和/与"等虚词）
   - 单字或无意义词（如"机""文""本"）
   - 包含中文/英文标点
   - 纯数字/纯符号
   - 指代性泛词（"本文""该书""我们""它们"）
   - 代码片段（含 `。`/`。py`/`def。`/`class。`）
   - 2-3 字无意义英文缩写（df/pd/np/os/id/col/val/max/min/Hot/train/import/valid/fold）
   - 在原文末出现或原文中仅作为普通词语

2. **保留并分类（valid）** 如果实体：
   - 是专有名词（算法名/工具名/指标名/概念名等）
   - 在原文中出现并有独立语义
   - 长度 2-20 字

3. **分类标签（recommended_type 之一）**：
   {', '.join(config['entity_types'])}

## 示例
输入：[{{"id":"e1","name":"随机森林"}},{{"id":"e2","name":"本文对机器学习进行了介绍"}},{{"id":"e3","name":"机"}}]
输出：{{"valid":[{{"id":"e1","name":"随机森林","recommended_type":"算法"}}],"removed":[{{"id":"e2","name":"本文对机器学习进行了介绍"}},{{"id":"e3","name":"机"}}]}}

## 实体列表
{entity_json}

## 上下文
{chunk_text}

只返回 JSON，格式：{{"valid":[{{"id":"...","name":"...","recommended_type":"..."}}],"removed":[{{"id":"...","name":"..."}}]}}"""

    def _build_relation_prompt(self, chunks: list, entities: list) -> str:
        """构建关系提取 prompt — 限制 chunk 数量防止超 token"""
        # 限制 chunk 数量避免 prompt 太大
        MAX_CHUNKS = 15
        selected = chunks[:MAX_CHUNKS] if len(chunks) > MAX_CHUNKS else chunks
        chunk_text = '\n\n'.join(
            f"[chunk {i}] {c.get('chunk_text', c.get('page_content', ''))[:300]}"
            for i, c in enumerate(selected)
        )
        entity_names = [e['name'] for e in entities if e.get('name') and len(e['name'].strip()) >= 2]
        entity_list = ', '.join(entity_names[:80])

        config = self.config
        return f"""你是知识图谱关系提取专家。从以下 [{config['label']}] 领域的技术文本中提取实体和关系。

【文本 chunks】
{chunk_text}

【参考实体（供参考，可忽略）】
{entity_list}

要求：
1. 从文本中提取真正的技术概念实体（中文优先，长度 2-15字）
2. 关系类型：{', '.join(config['rel_types'])}
3. 只提取文本中明确出现的关系，不要臆测
4. 每个 source/target 必须是你提取的实体名

返回 JSON（只返回 JSON）：{{
  "relations": [
    {{"source": "entity1", "target": "entity2", "type": "关系类型", "description": "简要说明"}}
  ],
  "count": N
}}"""

    def _call_api(self, messages: list, temperature: float = 0.1, max_tokens: int = 1500) -> str:
        """调用 OpenAI-compatible API"""
        url = f"{self.endpoint}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        for attempt in range(3):
            try:
                resp = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except requests.exceptions.Timeout:
                if attempt == 2:
                    raise
                time.sleep(2)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)
        raise RuntimeError("LLM API 调用失败: 三次重试均已用完")

    def _parse_json(self, text: str) -> dict:
        """解析 LLM 返回的 JSON"""
        content = text
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())

    def refine_entities(self, entities: list, chunks: list) -> dict:
        """
        精筛实体列表 — 规则预过滤 + LLM 审核（分批，每批最多 60 个）

        Returns:
            {entities: [...], removed: [...], suggestions: [...]}
        """
        if not entities:
            return {"entities": entities, "removed": [], "suggestions": []}

        # 规则预过滤：先删明显垃圾
        valid_entities, pre_removed = self._prefilter(entities)
        logger.info(f"规则预过滤: {len(entities)}→{len(valid_entities)} (删除{len(pre_removed)})")

        BATCH_SIZE = 40  # 减少每批数量让 LLM 更精准
        all_refined = []
        all_removed = list(pre_removed)  # 规则过滤的算删除
        all_suggestions = []

        for batch_start in range(0, len(valid_entities), BATCH_SIZE):
            batch = valid_entities[batch_start:batch_start + BATCH_SIZE]
            # 建立 id→entity 索引
            id_entity = {e.get('id', ''): e for e in batch if e.get('id')}
            try:
                prompt = self._build_refine_prompt(batch, chunks)
                raw = self._call_api([
                    {"role": "system", "content": "你是知识图谱审核专家，只返回 JSON 格式的结果，不包含解释文字。"},
                    {"role": "user", "content": prompt},
                ])
                result = self._parse_json(raw)

                # LLM 返回 valid/removed（可能用 valid/removed 或 valid/invalid）
                valid_items = result.get('valid', result.get('valid_items', []))
                removed_items = result.get('removed', result.get('removed_items', result.get('invalid', [])))

                removed_ids = set()
                type_updates = {}  # id → type
                for item in removed_items:
                    eid = item.get('id', '').strip()
                    ename = item.get('name', '').strip()
                    if eid:
                        removed_ids.add(eid)
                    elif ename:
                        # fallback: name → find id
                        for e in batch:
                            if e.get('name') == ename:
                                removed_ids.add(e.get('id', ''))
                                break

                for item in valid_items:
                    eid = item.get('id', '').strip()
                    rtype = item.get('recommended_type', '').strip()
                    if eid and rtype:
                        type_updates[eid] = rtype
                    elif item.get('name') and rtype:
                        for e in batch:
                            if e.get('name') == item.get('name'):
                                type_updates[e.get('id', '')] = rtype
                                break

                for e in batch:
                    eid = e.get('id', '')
                    if eid in removed_ids:
                        all_removed.append(e)
                    else:
                        if eid in type_updates:
                            e['type'] = type_updates[eid]
                        all_refined.append(e)

                if result.get('suggestions'):
                    all_suggestions.append(str(result['suggestions']))

            except Exception as e:
                logger.warning(f"批次精筛失败 (offset={batch_start}): {e}")
                all_refined.extend(batch)  # 失败时整批保留

        logger.info(f"LLM 精筛: {len(entities)}→{len(all_refined)} (规则删{len(pre_removed)}, LLM删{len(all_removed)-len(pre_removed)})")
        return {"entities": all_refined, "removed": all_removed, "suggestions": all_suggestions}

    def extract_relations(self, chunks: list, entities: list) -> dict:
        """
        提取实体间关系 — 发送给 LLM 提取

        Returns:
            {"relations": [{source, target, type, reason}], "count": N}
        """
        if not entities or not chunks:
            return {"relations": [], "count": 0}

        try:
            prompt = self._build_relation_prompt(chunks, entities)
            raw = self._call_api([
                {"role": "system", "content": "你是知识图谱关系提取专家，只返回 JSON 格式的结果。"},
                {"role": "user", "content": prompt},
            ])
            result = self._parse_json(raw)
            relations = result.get('relations', [])

            # 基本过滤：source/target 非空且不是垃圾单词
            weak = {'the','a','an','is','it','data','text','code','file','value','test','type','key','list','item'}
            valid = [r for r in relations
                     if r.get('source') and r.get('target')
                     and len(r.get('source','').strip()) >= 2
                     and len(r.get('target','').strip()) >= 2
                     and r.get('source','').strip().lower() not in weak
                     and r.get('target','').strip().lower() not in weak]

            logger.info(f"[LLM 关系提取]: {len(valid)}/{len(relations)} 有效")
            return {"relations": valid, "count": len(valid)}

        except Exception as e:
            logger.warning(f"LLM 关系提取失败: {e}")
            return {"relations": [], "count": 0, "error": str(e)}