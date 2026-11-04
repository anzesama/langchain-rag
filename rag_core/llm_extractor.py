import json
import requests
import logging
from typing import List, Dict, Any
from rag_config import AGNES_API_KEY, AGNES_API_BASE, LLM_MODEL, LLM_MAX_TOKENS
import os

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
        三路提取合并 (v3 — jieba TF-IDF 为主路)

        jieba TF-IDF → 高质量实体（稳定、无 API 成本、快）
        LLM API → 关系提取 + 补充少量队实体
        regex → 降级为审核参考，不在主路中

        Args:
            text: 待提取的文本
            source: 来源标识 (文件名/章节名)

        Returns:
            {
                'jieba': [jieba实体],  # 主路
                'llm': [LLM实体],      # 辅助（关系）
                'regex': [正则实体],   # 仅参考
                'entities': [合并后的所有去重实体],
                'relations': [LLM提取的关系]
            }
        """
        # 1. ===== jieba TF-IDF 主路实体提取 =====
        jieba_result = self._jieba_extract(text)
        # 去重（按名称，同一实体不重复）
        jieba_names = {}
        jieba_unique = []
        for e in jieba_result.get("entities", []):
            if e["name"] not in jieba_names:
                jieba_names[e["name"]] = e
                jieba_unique.append(e)

        # 2. ===== LLM 提取（辅助：补充关系 + 关键实体）=====
        # 环境变量 SKIP_LLM 控制：导入时设为 1 避免高频 API 调用导致 429
        if os.environ.get('SKIP_LLM', '0') == '1':
            llm_result = {'entities': [], 'relations': []}
        else:
            llm_result = self._llm_extract(text)

        # 用 jieba 实体作为基准名集
        jieba_name_set = set(jieba_names.keys())

        # LLM 实体去重：只保留不在 jieba 中的
        llm_entities = [e for e in llm_result.get("entities", []) if e["name"] not in jieba_name_set]

        # LLM 关系过滤：只保留 source/target 至少有一方在 jieba 实体中的
        filtered_relations = []
        for r in llm_result.get("relations", []):
            src = r.get("source", "").strip()
            tgt = r.get("target", "").strip()
            if src and tgt and (src in jieba_name_set or tgt in jieba_name_set):
                filtered_relations.append(r)

        # 3. ===== 正则提取（regex）= 仅参考 =====
        regex_result = self._regex_extract(text)
        regex_entities = [e for e in regex_result.get("entities", []) 
                          if e["name"] not in jieba_name_set]

        # 合并（主路 + 辅路 + 关系）
        all_entities = jieba_unique + llm_entities

        logger.info(
            f"提取结果: jieba主路={len(jieba_unique)} LRM实体={len(llm_entities)} 关系={len(filtered_relations)} 正则参考={len(regex_entities)}"
        )

        return {
            'jieba': jieba_unique,
            'llm': llm_entities,
            'regex': regex_entities,
            'entities': all_entities,
            'relations': filtered_relations
        }

    def _llm_extract(self, text: str) -> Dict[str, Any]:
        """
        调用 Agnes API 提取实体和关系 (v2 — 强化版 Prompt + 后端质量过滤)

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

        prompt = f"""你是知识图谱构建专家。从以下文本中提取**独立的、命名实体**和**实体间的关系**。

## 实体规则（严格）
1. 实体名必须是名词或固定术语，长度限制 2-20 个字符
2. 禁止单字、禁止超过 20 字的超长实体
3. 禁止填入完整句子或句子片段（如"我们使用交叉验证方法"），只能填入"交叉验证"
4. 类型必须是严格的知识点类型：概念、方法、算法、工具、框架、模型、数据集、指标、技术、库、函数
5. 只提取真正独特的、有信息量、可检索的知识点 — 不要提取泛化的描述

## 关系规则（严格）
1. 只提取在这段文本中明确出现的实体之间的肯定关系
2. 不要猜测或臆测关系
3. 关系类型：定义、扩展、使用、基于、对比、包含、实现、改进、防止、优化

## 格式（严格JSON）
{{
  "entities": [
    {{"name": "交叉验证", "type": "方法", "description": "将数据集分为K折以验证模型泛化能力"}}
  ],
  "relations": [
    {{"source": "交叉验证", "target": "过拟合", "type": "防止", "description": "交叉验证防止模型对训练数据过拟合"}}
  ]
}}

## 文本
{text}

只返回JSON，不添加任何解释。"""

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
                        {"role": "system", "content": "你是知识图谱实体提取专家，只返回JSON结果，不包含任何解释文字。实体名必须是2-20字的命名术语，不能是描述句。"},
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

                # ====== 后端质量过滤 ======
                valid_entities = []
                valid_names = set()

                # 英文常见弱词黑名单
                WEAK_EN_WORDS = {
                    'the','a','an','is','it','we','he','she','they',
                    'and','or','not','but','for','with','from','into',
                    'onto','up','down','out','in','on','at','by','to',
                    'of','no','yes','has','had','are','was','were',
                    'be','been','can','may','if','then','else','when',
                    'who','why','how','also','only','just','so','very',
                    'this','that','these','those','all','some','any',
                    'each','every','other','more','less','much','many',
                    'would','should','could','will','shall','must',
                    'about','already','again','almost','always','never',
                    'there','here','often','its','now','too','well',
                    'my','your','his','her','our','their','my','mine',
                    'data','text','code','file','time','value','size',
                    'name','user','type','key','list','item','test',
                    'base','temp','home','case','day','end','set',
                }

                for e in result.get('entities', []):
                    name = e.get('name', '').strip()
                    # 长度过滤
                    if len(name) < 2 or len(name) > 30:
                        continue
                    # 去重
                    if name in valid_names:
                        continue
                    # 拒绝含中文标点的句子
                    if re.search(r'[，。！？；]', name):
                        continue
                    # 拒绝以虚词开头
                    if re.match(r'^[的也是在都就而及与或]', name):
                        continue
                    # 拒绝数字/日期开头
                    if re.match(r'^\d', name):
                        continue
                    # 纯英文短词过滤
                    if name.isascii() and len(name) <= 4 and name.lower() in WEAK_EN_WORDS:
                        continue

                    valid_entities.append(e)
                    valid_names.add(name)

                # 只保留 source/target 都在实体列表中的关系
                valid_relations = []
                for r in result.get('relations', []):
                    src = r.get('source', '').strip()
                    tgt = r.get('target', '').strip()
                    if src in valid_names and tgt in valid_names:
                        valid_relations.append(r)

                logger.info(f"LLM提取: {len(valid_entities)}个有效实体, {len(valid_relations)}条有效关系 (原始: {len(result.get('entities',[]))}实体/{len(result.get('relations',[]))}关系)")
                return {'entities': valid_entities, 'relations': valid_relations}

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
        jieba TF-IDF 关键词提取作为补充实体

        仅提取高区分度关键词，不提取关系
        """
        import re
        from rag_config import BASE_DIR
        from rag_core.wiki_db import WikiDB

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

        使用 jieba.analyse.extract_tags 提取有区分度的关键词，
        配合停用词过滤、词长过滤、Markdown符号过滤，作为高质量补充实体。
        """
        import jieba.analyse

        if not text or not text.strip():
            return {'entities': [], 'relations': []}

        try:
            # ===== 停用词表（ML/NLP 领域核心词不删除）=====
            STOP_WORDS = {
                # 虚词永远停
                '的', '了', '是', '在', '和', '与', '或', '等', '及',
                '其中', '也', '就', '都', '但', '而', '不', '很', '最',
                '一个', '一些', '这些', '那些', '这个', '例如', '如果',
                '它', '他', '她', '它们', '我们', '他们', '你们', '自己',
                '这', '那', '之', '以', '为', '被', '把', '给', '中',
                '因为', '所以', '虽然', '但是', '已经', '然后',
                '对', '从', '到', '上', '下', '第', '该', '更',
                '可能', '非常', '继续', '或者', '并且', '即', '如', '还',
                '仅', '只', '将', '已', '都', '吗', '每个', '等等', '不是', '实际上',
                '几乎', '即将', '任何', '几个', '除非',
                '那么', '矣', '么', '否', 'IER', '会', '你',
                '需要', '能', '要', '当', '时', '后', '前', '则', '之',
                '超', '高', '低', '大', '小', '新', '旧', '多', '少',
                '它', '间', '内', '外', '此', '其', '每', '次',
                '被称为', '而言', '来说', '所示', '如下', '上述', '下面',
                # 通用词删除
                '用于', '通过', '进行', '没有',
            }

            # 无意义的英文通用词
            ENGLISH_STOP = {
                'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                'can', 'could', 'may', 'might', 'shall', 'should', 'must',
                'it', 'we', 'you', 'he', 'she', 'they', 'me', 'us', 'him',
                'her', 'them', 'my', 'our', 'your', 'his', 'its', 'their',
                'this', 'that', 'these', 'those', 'all', 'some', 'any', 'no',
                'not', 'but', 'and', 'or', 'if', 'then', 'else', 'for',
                'with', 'without', 'from', 'into', 'onto', 'up', 'down',
                'out', 'in', 'on', 'at', 'by', 'to', 'of', 'about', 'also',
                'only', 'just', 'so', 'very', 'such', 'one', 'two', 'three',
                'already', 'more', 'less', 'much', 'many', 'most', 'both',
                'another', 'each', 'every', 'other', 'same', 'different',
                'used', 'using', 'based', 'called', 'found', 'given',
                'too', 'well', 'still', 'even', 'yet', 'often',
            }

            # jieba TF-IDF 关键词提取（topK=50, 过滤短词）
            all_tags = jieba.analyse.extract_tags(text, topK=50)

            entities = []
            for tag in all_tags:
                # 过滤：长度 ≥2、不含 Markdown 标记、不含 URL
                if len(tag) < 2:
                    continue
                if tag.startswith('http'):
                    continue
                if tag.count('#') >= 2:  # Markdown 标题标记
                    continue
                # 纯数字/符号
                if tag.replace('.', '').replace('-', '').replace('_', '').replace('/', '').replace('+', '').replace('*', '').replace('),', '').replace('(','').strip() == '':
                    continue
                # 停用词过滤（中文 + 英文）
                if tag in STOP_WORDS or tag.lower() in ENGLISH_STOP:
                    continue
                # 纯 ASCII 通用词（长度 ≤4 且有英文通用词气质）过滤
                if tag.isascii() and len(tag) <= 4 and tag.lower() in ENGLISH_STOP:
                    continue

                entities.append({
                    "name": tag,
                    "type": "关键词",
                    "description": f"jieba TF-IDF 关键词提取 (来源: jieba_tfidf)",
                    "confidence": 0.7,
                    "method": "jieba_tfidf"
                })

                # 限制最多返回 20 个
                if len(entities) >= 20:
                    break

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
