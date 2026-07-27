import json
import requests
import logging
from typing import List, Dict, Any
from rag_config import AGNES_API_KEY, AGNES_API_BASE, LLM_MODEL, LLM_MAX_TOKENS

logger = logging.getLogger(__name__)


class LLMExtractor:
    """
    LLM驱动的实体和关系提取器

    三路提取通道:
    1. Agnes API (LLM) → 自动批准, 直接入库
    2. 正则 (regex) → 待审核, 对比参考
    3. jieba关键词 → 待审核, 对比参考
    """

    def __init__(self):
        self.api_key = AGNES_API_KEY
        self.api_base = AGNES_API_BASE
        self.model = LLM_MODEL
        self.max_tokens = LLM_MAX_TOKENS
        self.max_retries = 3
        self.retry_delay = 5  # 秒, 429 限流时等待
        from rag_core.wiki_db_libsql import get_wiki_db
        self.wiki_db = get_wiki_db()

    def extract_all(self, text: str, source: str = None) -> Dict[str, Any]:
        """
        三路提取合并

        Args:
            text: 待提取的文本
            source: 来源标识 (文件名/章节名)

        Returns:
            {
                'llm': [LLMEntity, ...],
                'regex': [Entity, ...],
                'jieba': [Entity, ...],
                'relations': [Relation, ...]
            }
        """
        # 1. LLM 提取（包含实体和关系）
        llm_result = self._llm_extract(text)

        # 2. 正则提取（只提取实体）
        regex_result = self._regex_extract(text)

        # 3. jieba 提取（只提取实体）
        jieba_result = self._jieba_extract(text)

        # 去重: LLM 结果作为基准, 过滤掉与 LLM 重复的实体
        llm_entity_names = {e["name"]: e for e in llm_result["entities"]}
        filtered_regex = [e for e in regex_result.get("entities", []) if e["name"] not in llm_entity_names]
        filtered_jieba = [e for e in jieba_result.get("entities", []) if e["name"] not in llm_entity_names]

        # 合并实体（LLM + 正则 + jieba）
        all_entities = llm_result["entities"] + filtered_regex + filtered_jieba

        # 合并关系（LLM + 正则）
        all_relations = llm_result.get("relations", []) + regex_result.get("relations", [])

        return {
            'llm': llm_result["entities"],
            'regex': filtered_regex,
            'jieba': filtered_jieba,
            'entities': all_entities,
            'relations': all_relations
        }

    def _llm_extract(self, text: str) -> Dict[str, Any]:
        """
        调用 Agnes API 提取实体和关系

        Args:
            text: 文本内容

        Returns:
            {
                'entities': [{'name': str, 'type': str, 'description': str}],
                'relations': [{'source': str, 'target': str, 'type': str, 'description': str}]
            }
        """
        if not text or not text.strip():
            return {'entities': [], 'relations': []}

        prompt = f"""你是一个知识图谱实体提取专家。请从以下文本中提取关键实体和关系。

要求：
1. 实体类型自由发挥，常见：概念、方法、算法、工具、框架、人物、数据集、评估指标、论文、模型
2. 提取完整的、独立的命名实体，不要提取不完整的字符片段
3. 每个实体含：name(中/英均可), type(自定义), description(一句话)

4. 提取实体间明确存在的关系，关系类型自由发挥，常见：包含、使用、改进、基于、属于、对比、实现

请以严格JSON格式返回：
{{
  "entities": [
    {{"name": "交叉验证", "type": "方法", "description": "将数据集分为K折,轮流作为训练集和验证集的方法"}}
  ],
  "relations": [
    {{"source": "交叉验证", "target": "过拟合", "type": "对抗", "description": "交叉验证用于检测和防止过拟合"}}
  ]
}}

文本：
{text}
"""

        # 重试机制
        last_error = None
        for attempt in range(self.max_retries):
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的知识图谱实体提取专家，只返回JSON格式结果，不要包含任何解释文字。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": self.max_tokens
                }

                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 429:
                    # 限流，等待后重试
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.warning(f"Agnes API 429 rate limit, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
                    import time
                    time.sleep(wait_time)
                    continue

                if response.status_code != 200:
                    logger.warning(f"Agnes API error: {response.status_code} {response.text}")
                    return {'entities': [], 'relations': []}

                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()

                # 移除可能的markdown代码块标记
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

                result = json.loads(content)
                return result

            except requests.exceptions.Timeout:
                last_error = "timeout"
                if attempt < self.max_retries - 1:
                    continue
                logger.warning("Agnes API request timeout")
                return {'entities': [], 'relations': []}
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    continue
                logger.warning(f"Agnes API request failed: {e}")
                return {'entities': [], 'relations': []}
            except json.JSONDecodeError as e:
                last_error = f"JSON parse: {e}"
                if attempt < self.max_retries - 1:
                    continue
                logger.warning(f"JSON parse error from Agnes: {e}")
                return {'entities': [], 'relations': []}
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    continue
                logger.warning(f"Unexpected error in _llm_extract: {e}")
                return {'entities': [], 'relations': []}

        logger.warning(f"Agnes API failed after {self.max_retries} retries: {last_error}")
        return {'entities': [], 'relations': []}

    def _regex_extract(self, text: str) -> Dict[str, Any]:
        """
        正则提取实体和关系

        保留 wiki_updater.py 中的原有模式，但移除蛊真人专用内容
        """
        import re
        from rag_core.wiki_db import WikiDB
        from rag_config import BASE_DIR

        wiki_db = WikiDB()
        wiki_db.init_db()

        entities = {}
        relations = []

        # 简化的实体模式 (适用于通用文本)
        entity_patterns = {
            "概念": [
                r'([一-龥]{2,8}法)',
                r'([一-龥]{2,8}模型)',
                r'([一-龥]{2,8}算法)',
                r'([一-龥]{2,8}指标)',
                r'([一-龥]{2,8}技术)',
            ],
            "工具": [
                r'([一-龥]{2,8}库)',
                r'([一-龥]{2,8}框架)',
                r'([一-龥]{2,8}工具)',
            ],
            "数据集": [
                r'([一-龥]{2,8}数据集)',
                r'([一-龥]{2,8}数据集)',
            ]
        }

        # 简化的关系模式
        rel_patterns = [
            r'(.+?)使用(.+?)',
            r'(.+?)基于(.+?)',
            r'(.+?)包含(.+?)',
            r'(.+?)改进(.+?)',
            r'(.+?)对比(.+?)',
        ]

        # 正则提取实体
        for entity_type, patterns in entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for name in matches:
                    name = name.strip(',。、;:""''')
                    if not self._is_valid_entity(name):
                        continue
                    if not wiki_db.entity_exists(name):
                        wiki_db.add_entity(name, entity_type, source_chapter="regex")
                        entities[name] = {
                            "name": name,
                            "type": entity_type,
                            "description": f"通过正则提取的实体 (来源: regex)",
                            "confidence": 1,
                            "method": "regex"
                        }

        # 正则提取关系
        for pattern in rel_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    source = match[0].strip()
                    target = match[1].strip() if len(match) > 1 else ""

                    if not source or not target:
                        continue

                    source = source.strip(',。、;:""''')
                    target = target.strip(',。、;:""''')

                    # 自动创建不存在的实体
                    if not wiki_db.entity_exists(source):
                        wiki_db.add_entity(source, "未分类", source_chapter="regex")
                    if not wiki_db.entity_exists(target):
                        wiki_db.add_entity(target, "未分类", source_chapter="regex")

                    relations.append({
                        "source": source,
                        "target": target,
                        "type": "关联",
                        "description": f"通过正则提取的关系 (来源: regex)",
                        "confidence": 1,
                        "method": "regex"
                    })

        wiki_db.connect().close()

        return {
            "entities": list(entities.values()),
            "relations": relations
        }

    def _jieba_extract(self, text: str) -> Dict[str, Any]:
        """
        jieba TF-IDF 关键词提取作为补充

        返回频率最高的关键词作为潜在实体
        """
        import jieba
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        import numpy as np

        if not text or not text.strip():
            return {'entities': [], 'relations': []}

        try:
            # 简单的分句
            sentences = [s.strip() for s in text.split('。') if len(s.strip()) > 10]

            if len(sentences) < 2:
                return {'entities': [], 'relations': []}

            # TF-IDF 提取关键词
            vectorizer = TfidfVectorizer(max_features=100, stop_words=None)
            tfidf_matrix = vectorizer.fit_transform(sentences)
            feature_names = vectorizer.get_feature_names_out()

            # 按句子聚合关键词
            entity_keywords = {}
            for i, sentence in enumerate(sentences):
                words = jieba.lcut(sentence)
                # 过滤停用词和短词
                words = [w for w in words if len(w) >= 2 and w not in ['的', '了', '是', '在', '和', '与', '或', '等', '以及', '其中']]
                for word in words:
                    if word not in entity_keywords:
                        entity_keywords[word] = 0
                    entity_keywords[word] += 1

            # 取前20个关键词
            sorted_keywords = sorted(entity_keywords.items(), key=lambda x: x[1], reverse=True)[:20]

            entities = []
            for word, freq in sorted_keywords:
                entities.append({
                    "name": word,
                    "type": "关键词",
                    "description": f"jieba关键词提取 (频率: {freq}, 来源: jieba)",
                    "confidence": freq,
                    "method": "jieba"
                })

            return {
                "entities": entities,
                "relations": []
            }

        except Exception as e:
            logger.warning(f"jieba提取失败: {e}")
            return {'entities': [], 'relations': []}

    def _is_valid_entity(self, name: str) -> bool:
        """验证实体名称是否有效"""
        if not name or len(name) < 2 or len(name) > 15:
            return False

        # 不能有数量词
        if any(word in name for word in ['一位', '一只', '一个', '两个', '这个', '那个']):
            return False

        # 排除纯动词
        common_verbs = ['持有', '使用', '拥有', '属于', '主修', '修炼']
        if name in common_verbs:
            return False

        return True
