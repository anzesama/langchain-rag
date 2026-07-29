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

    def _build_refine_prompt(self, entities: list, chunks: list) -> str:
        """构建精筛实体 prompt"""
        entity_text = '\n'.join(
            f"- {e.get('name')} (类型: {e.get('type', '未分类')})"
            for e in entities
        )
        chunk_text = '\n\n'.join(
            f"[Chunk {i}] {c.get('chunk_text', c.get('page_content', ''))}"
            for i, c in enumerate(chunks[:5])
        ) if chunks else '(无上下文)'

        config = self.config
        return f"""你是知识图谱审核专家。请审核以下 [{config['label']}] 领域的实体列表。

【审核标准】
{config['entity_review_rules']}

【有效类型】
{', '.join(config['entity_types'])}

【实体列表】
{entity_text}

【上下文 chunks】
{chunk_text}

请分析每个实体并返回 JSON（只返回 JSON，不要解释）：{{
  "valid": [{{"name": "...", "recommended_type": "...", "confidence": "high/medium"}}],
  "invalid": [{{"name": "...", "reason": "..."}}],
  "suggestions": "建议补充的实体或删除原因"
}}"""

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

    def _call_api(self, messages: list, temperature: float = 0.1, max_tokens: int = 2000) -> str:
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
        精筛实体列表 — 发送给 LLM 审核过滤

        Returns:
            {entities: [...], removed: [...], suggestions: [...]}
        """
        if not entities:
            return {"entities": entities, "removed": [], "suggestions": []}

        try:
            prompt = self._build_refine_prompt(entities, chunks)
            raw = self._call_api([
                {"role": "system", "content": "你是知识图谱审核专家，只返回 JSON 格式的结果，不包含解释文字。"},
                {"role": "user", "content": prompt},
            ])
            result = self._parse_json(raw)

            # build entity name → recommended type lookup
            type_map = {}
            invalid_names = set()
            for item in result.get('valid', []):
                name = item.get('name', '').strip()
                if name:
                    type_map[name] = item
            for item in result.get('invalid', []):
                name = item.get('name', '').strip()
                if name:
                    invalid_names.add(name)

            refined = []
            removed = []
            for e in entities:
                name = e.get('name', '')
                if name in invalid_names:
                    removed.append(e)
                else:
                    recommendation = type_map.get(name, {})
                    if recommendation.get('recommended_type'):
                        e['type'] = recommendation['recommended_type']
                    refined.append(e)

            logger.info(f"LLM 精筛: {len(entities)}→{len(refined)} (删除{len(removed)})")
            return {"entities": refined, "removed": removed, "suggestions": result.get('suggestions', [])}

        except Exception as e:
            logger.warning(f"LLM 精筛失败: {e}")
            return {"entities": entities, "removed": [], "suggestions": []}

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