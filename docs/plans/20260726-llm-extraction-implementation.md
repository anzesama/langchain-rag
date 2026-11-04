# LLM 驱动实体/关系提取 - Implementation Plan

> **REQUIRED SUB-SKILL:** Use the subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace hardcoded regex entity/relationship extraction with Agnes API (LLM) as primary method, with regex and jieba as fallback comparison channels. Delete old entities and rebuild from scratch.

**Architecture:**
- New `rag_core/llm_extractor.py` with three extraction channels: LLM (auto-approve), regex (pending comparison), jieba (pending comparison)
- Modify `rag_core/wiki_updater.py` to delegate extraction to `LLMExtractor`
- Modify `rag_core/auto_importer.py` to use new extractor
- Clean database and re-import AAAMLP-CN to verify quality

**Tech Stack:**
- Agnes API (LLM) for entity/relationship extraction
- Existing WikiDB (libsql) for storage
- jieba + TF-IDF for keyword fallback
- Existing regex patterns from `wiki_updater.py`

---

## Phase 1: Core LLM Extractor

### Task 1: Create LLMExtractor class with Agnes API integration

**TDD scenario:** New feature — full TDD cycle

**Files:**
- Create: `rag_core/llm_extractor.py`
- Test: `tests/test_llm_extractor.py`

**Step 1: Write the failing test**

```python
# tests/test_llm_extractor.py
import pytest
from rag_core.llm_extractor import LLMExtractor

def test_llm_extractor_initialization():
    extractor = LLMExtractor()
    assert extractor.api_key is not None
    assert extractor.api_base is not None
    assert extractor.model == "agnes-2.0-flash"

def test_llm_extract_returns_structure():
    extractor = LLMExtractor()
    text = "交叉验证是一种评估机器学习模型性能的方法。"
    result = extractor._llm_extract(text)

    assert isinstance(result, dict)
    assert "entities" in result
    assert "relations" in result
    assert isinstance(result["entities"], list)
    assert isinstance(result["relations"], list)

def test_llm_extract_with_valid_text():
    extractor = LLMExtractor()
    text = """
    ResNet是一种深度残差学习网络。它通过跳跃连接解决了深度神经网络的退化问题。
    ResNet常用于图像分类任务。
    """
    result = extractor._llm_extract(text)

    # Should find ResNet entity
    entity_names = [e["name"] for e in result["entities"]]
    assert "ResNet" in entity_names

    # Should find relationship
    rel_names = [r["source"] + "-" + r["type"] + "-" + r["target"] for r in result["relations"]]
    assert any("ResNet" in r for r in rel_names)
```

**Step 2: Run test to verify it fails**

```bash
cd D:/class/project-config/langchain-rag
pytest tests/test_llm_extractor.py -v
```

Expected output:
```
FAILED - test_llm_extractor_initialization: ModuleNotFoundError: No module named 'rag_core.llm_extractor'
FAILED - test_llm_extract_returns_structure: ModuleNotFoundError: No module named 'rag_core.llm_extractor'
FAILED - test_llm_extract_with_valid_text: ModuleNotFoundError: No module named 'rag_core.llm_extractor'
```

**Step 3: Write minimal implementation**

```python
# rag_core/llm_extractor.py
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
                'jieba': [Entity, ...]
            }
        """
        # 1. LLM 提取
        llm_result = self._llm_extract(text)

        # 2. 正则提取
        regex_result = self._regex_extract(text)

        # 3. jieba 提取
        jieba_result = self._jieba_extract(text)

        # 去重: LLM 结果作为基准, 过滤掉与 LLM 重复的实体
        llm_entity_names = {e["name"]: e for e in llm_result["entities"]}
        filtered_regex = [e for e in regex_result if e["name"] not in llm_entity_names]
        filtered_jieba = [e for e in jieba_result if e["name"] not in llm_entity_names]

        return {
            'llm': llm_result["entities"],
            'regex': filtered_regex,
            'jieba': filtered_jieba
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
            logger.warning("Agnes API request timeout")
            return {'entities': [], 'relations': []}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Agnes API request failed: {e}")
            return {'entities': [], 'relations': []}
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error from Agnes: {e}")
            return {'entities': [], 'relations': []}
        except Exception as e:
            logger.warning(f"Unexpected error in _llm_extract: {e}")
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
            vectorizer = TfidfVectorizer(max_features=100, stop_words='cn')
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_llm_extractor.py -v
```

Expected output:
```
PASSED - test_llm_extractor_initialization
PASSED - test_llm_extract_returns_structure
PASSED - test_llm_extract_with_valid_text
```

**Step 5: Commit**

```bash
cd D:/class/project-config/langchain-rag
git add rag_core/llm_extractor.py tests/test_llm_extractor.py
git commit -m "feat: 新增 LLMExtractor 类 - Agnes API 实体/关系提取"
```

---

### Task 2: Add LLMExtractor to WikiUpdater

**TDD scenario:** Modifying tested code — run existing tests first

**Files:**
- Modify: `rag_core/wiki_updater.py:1-763`

**Step 1: Run existing tests**

```bash
pytest tests/test_wiki_db_libsql.py -v -k "test_add_entity or test_add_relationship"
```

Expected: Tests pass

**Step 2: Modify WikiUpdater to use LLMExtractor**

Replace the `scan_new_entities` and `scan_new_relations` methods with LLM-based extraction:

```python
# rag_core/wiki_updater.py

def scan_new_entities(
    self,
    text: str,
    source_chapter: str = None,
    min_confidence: int = 2
) -> List[Dict[str, Any]]:
    """
    扫描新文本中的潜在实体（LLM + 正则 + jieba 混合提取）

    Args:
        text: 文本内容
        source_chapter: 来源章节
        min_confidence: 最小置信度(仅用于正则/jieba)

    Returns:
        新创建的实体列表
    """
    if not text or not text.strip():
        return []

    # 使用 LLMExtractor 提取
    try:
        from rag_core.llm_extractor import LLMExtractor
        extractor = LLMExtractor()
        extraction_result = extractor.extract_all(text, source_chapter)

        # LLM 结果直接批准入库
        new_entities = []
        for entity in extraction_result["llm"]:
            try:
                self.wiki_db.add_entity(
                    name=entity["name"],
                    entity_type=entity["type"],
                    properties={"description": entity.get("description", "")},
                    source_chapter=source_chapter
                )
                new_entities.append({
                    "name": entity["name"],
                    "type": entity["type"],
                    "confidence": 1,
                    "source_chapter": source_chapter,
                    "method": "llm"
                })
            except Exception as e:
                logger.error(f"添加 LLM 实体失败 {entity['name']}: {e}")

        logger.info(f"LLM 扫描到 {len(new_entities)} 个新实体并已入库")

        # 正则/jieba 结果写入 pending_reviews 表供对比
        self._write_to_pending(
            extraction_result["regex"],
            source_chapter=source_chapter,
            method="regex"
        )
        self._write_to_pending(
            extraction_result["jieba"],
            source_chapter=source_chapter,
            method="jieba"
        )

        return new_entities

    except Exception as e:
        logger.warning(f"LLM 提取失败，回退到正则提取: {e}")
        return self._regex_scan_new_entities(text, source_chapter, min_confidence)

def scan_new_relations(
    self,
    text: str,
    source_chapter: str = None
) -> List[Dict[str, Any]]:
    """
    扫描新文本中的潜在关系（LLM + 正则混合提取）

    Args:
        text: 文本内容
        source_chapter: 来源章节

    Returns:
        新创建的关系列表
    """
    if not text or not text.strip():
        return []

    # 使用 LLMExtractor 提取
    try:
        from rag_core.llm_extractor import LLMExtractor
        extractor = LLMExtractor()
        extraction_result = extractor.extract_all(text, source_chapter)

        # LLM 关系直接批准入库
        new_relations = []
        for rel in extraction_result["llm"]:
            try:
                self.wiki_db.add_relationship(
                    source_name=rel["source"],
                    target_name=rel["target"],
                    rel_type=rel["type"],
                    properties={"description": rel.get("description", "")},
                    source_chapter=source_chapter
                )
                new_relations.append({
                    "source": rel["source"],
                    "target": rel["target"],
                    "rel_type": rel["type"],
                    "confidence": 1,
                    "source_chapter": source_chapter,
                    "method": "llm"
                })
            except Exception as e:
                logger.error(f"添加 LLM 关系失败 {rel['source']}->{rel['target']}: {e}")

        logger.info(f"LLM 扫描到 {len(new_relations)} 个新关系并已入库")

        # 正则/jieba 关系写入 pending_reviews 表供对比
        self._write_pending_relations(
            extraction_result["regex"],
            source_chapter=source_chapter,
            method="regex"
        )
        self._write_pending_relations(
            extraction_result["jieba"],
            source_chapter=source_chapter,
            method="jieba"
        )

        return new_relations

    except Exception as e:
        logger.warning(f"LLM 关系提取失败，回退到正则提取: {e}")
        return self._regex_scan_new_relations(text, source_chapter)

# 保留原有的正则方法作为回退
def _regex_scan_new_entities(self, text: str, source_chapter: str = None, min_confidence: int = 2) -> List[Dict[str, Any]]:
    """正则提取实体（原有逻辑，保留作为回退）"""
    # ... 保持原有 _regex_scan_new_entities 逻辑不变 ...
    pass

def _regex_scan_new_relations(self, text: str, source_chapter: str = None) -> List[Dict[str, Any]]:
    """正则提取关系（原有逻辑，保留作为回退）"""
    # ... 保持原有 _regex_scan_new_relations 逻辑不变 ...
    pass

def _write_to_pending(self, entities: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
    """将实体写入 pending_reviews 表"""
    count = 0
    for entity in entities:
        name = entity.get("name", "")
        entity_type = entity.get("type", "未分类")
        description = entity.get("description", "")
        confidence = entity.get("confidence", 0)

        try:
            self.wiki_db.add_to_pending(
                entity_name=name,
                relation_type=entity_type,
                properties={"description": description, "method": method, "source_chapter": source_chapter},
                confidence=confidence
            )
            count += 1
        except Exception as e:
            logger.error(f"写入待审核实体失败 {name}: {e}")

    return count

def _write_pending_relations(self, relations: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
    """将关系写入 pending_reviews 表"""
    count = 0
    for rel in relations:
        source_name = rel.get("source", "")
        target_name = rel.get("target", "")
        rel_type = rel.get("type", "关联")
        description = rel.get("description", "")
        confidence = rel.get("confidence", 0)

        try:
            self.wiki_db.add_to_pending(
                entity_name=f"{source_name}--{rel_type}--{target_name}",
                relation_type=f"{source_name}--{rel_type}--{target_name}",
                properties={"description": description, "method": method, "source_chapter": source_chapter, "source": source_name, "target": target_name, "rel_type": rel_type},
                confidence=confidence
            )
            count += 1
        except Exception as e:
            logger.error(f"写入待审核关系失败 {source_name}->{target_name}: {e}")

    return count
```

**Step 3: Run tests to verify they still pass**

```bash
pytest tests/test_wiki_db_libsql.py -v -k "test_add_entity or test_add_relationship or test_get_stats"
```

Expected: Tests pass

**Step 4: Commit**

```bash
git add rag_core/wiki_updater.py
git commit -m "feat: WikiUpdater 集成 LLMExtractor"
```

---

### Task 3: Modify auto_importer to use LLMExtractor

**TDD scenario:** Modifying tested code — run existing tests first

**Files:**
- Modify: `rag_core/auto_importer.py:150-220`

**Step 1: Run existing tests**

```bash
pytest tests/test_auto_importer.py -v
```

Expected: Tests pass

**Step 2: Modify _import_file to use LLMExtractor**

Replace the WikiUpdater call with LLMExtractor directly:

```python
# rag_core/auto_importer.py

def _import_file(self, filepath: Path, rel_key: str) -> bool:
    """导入单个文件"""
    try:
        # 加载文档
        documents = load_document(filepath)
        if not documents:
            logger.warning(f"未从 {filepath} 加载到任何内容")
            return False

        # 切分文档
        chunks = chunk_documents(documents)
        if not chunks:
            logger.warning(f"文档 {filepath} 切分后为空")
            return False

        # 更新 metadata 使用相对路径
        for doc in chunks:
            doc.metadata["source"] = rel_key

        # 添加到向量库
        self._add_to_vector_store(chunks, rel_key)
        logger.info(f"✅ 自动导入: {filepath.name} ({len(chunks)} 个块)")

        # 使用 LLMExtractor 提取实体和关系
        try:
            from rag_core.llm_extractor import LLMExtractor
            extractor = LLMExtractor()

            combined_text = "\n".join([c.page_content for c in chunks])

            # 提取实体
            extraction_result = extractor.extract_all(combined_text, rel_key)

            # LLM 结果直接入库
            wiki_db = get_wiki_db()
            entities_added = 0
            for entity in extraction_result["llm"]:
                try:
                    wiki_db.add_entity(
                        name=entity["name"],
                        entity_type=entity["type"],
                        properties={"description": entity.get("description", "")},
                        source_chapter=rel_key
                    )
                    entities_added += 1
                except Exception as e:
                    logger.error(f"添加实体失败 {entity['name']}: {e}")

            # 正则/jieba 写入 pending
            extractor._write_to_pending(extraction_result["regex"], source_chapter=rel_key, method="regex")
            extractor._write_to_pending(extraction_result["jieba"], source_chapter=rel_key, method="jieba")

            # 提取关系
            relations_added = 0
            for rel in extraction_result["llm"]:
                try:
                    wiki_db.add_relationship(
                        source_name=rel["source"],
                        target_name=rel["target"],
                        rel_type=rel["type"],
                        properties={"description": rel.get("description", "")},
                        source_chapter=rel_key
                    )
                    relations_added += 1
                except Exception as e:
                    logger.error(f"添加关系失败 {rel['source']}->{rel['target']}: {e}")

            logger.info(f"Wiki 更新: {entities_added} 个实体, {relations_added} 个关系 (LLM)")
            logger.info(f"待审核: {len(extraction_result['regex']) + len(extraction_result['jieba'])} 个正则/jieba 候选")

        except Exception as e:
            logger.warning(f"LLM 提取失败，跳过 Wiki 更新: {e}")

        return True
    except Exception as e:
        logger.error(f"自动导入失败 {filepath}: {e}")
        return False
```

**Step 3: Add helper methods to LLMExtractor**

```python
# rag_core/llm_extractor.py

def _write_to_pending(self, entities: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
    """将实体写入 pending_reviews 表"""
    if not entities:
        return 0

    count = 0
    for entity in entities:
        name = entity.get("name", "")
        entity_type = entity.get("type", "未分类")
        description = entity.get("description", "")
        confidence = entity.get("confidence", 0)

        try:
            self.wiki_db.add_to_pending(
                entity_name=name,
                relation_type=entity_type,
                properties={"description": description, "method": method, "source_chapter": source_chapter},
                confidence=confidence
            )
            count += 1
        except Exception as e:
            logger.error(f"写入待审核实体失败 {name}: {e}")

    return count
```

**Step 4: Run tests to verify they still pass**

```bash
pytest tests/test_auto_importer.py -v
```

Expected: Tests pass

**Step 5: Commit**

```bash
git add rag_core/auto_importer.py
git commit -m "feat: auto_importer 使用 LLMExtractor"
```

---

## Phase 2: Database Cleanup and Re-import

### Task 4: Clean database and re-import AAAMLP-CN

**TDD scenario:** Trivial change — use judgment, run tests after

**Files:**
- Modify: `scripts/auto_import.py` (or create new script)

**Step 1: Create cleanup and re-import script**

```python
# scripts/cleanup_and_reimport.py
import sys
from pathlib import Path
from rag_core.auto_importer import AutoImportManager

# 清理数据库
db_path = Path("storage/knowledge_base.db")
if db_path.exists():
    db_path.unlink()
    print(f"✓ 已删除旧数据库: {db_path}")

# 重新导入
print("开始导入 AAAMLP-CN...")
mgr = AutoImportManager(documents_dir=Path("documents/AAAMLP-CN"), storage_dir=Path("storage"))
stats = mgr.scan_and_import()
print(f"\n导入完成:")
print(f"  实体总数: {stats['total_entities']}")
print(f"  关系数: {stats['total_relationships']}")
print(f"  待审核实体: {stats.get('pending_entities', 0)}")
print(f"  待审核关系: {stats.get('pending_relations', 0)}")
```

**Step 2: Run script**

```bash
cd D:/class/project-config/langchain-rag
python scripts/cleanup_and_reimport.py
```

Expected output:
```
✓ 已删除旧数据库: storage/knowledge_base.db
开始导入 AAAMLP-CN...
[日志输出...]
导入完成:
  实体总数: ~30-80 (不是 416)
  关系数: ~5-20
  待审核实体: ~10-30 (正则/jieba 对比结果)
  待审核关系: ~2-10
```

**Step 3: Verify in browser**

```bash
start http://127.0.0.1:5000
```

打开页面，检查：
- 实体数减少到 30-80 个（真实概念，不是碎片）
- 待审核区域有正则/jieba 的对比结果
- 知识图谱显示正确节点和连线

**Step 4: Commit**

```bash
git add scripts/cleanup_and_reimport.py
git commit -m "feat: 新增清理+重新导入脚本"
```

---

## Phase 3: Testing and Finalization

### Task 5: Add comprehensive tests for LLMExtractor

**TDD scenario:** New feature — full TDD cycle

**Files:**
- Create: `tests/test_llm_extractor.py` (extend existing)

**Step 1: Add tests**

```python
# tests/test_llm_extractor.py
import pytest
from rag_core.llm_extractor import LLMExtractor

class TestLLMExtractor:
    def test_extract_all_returns_structure(self):
        extractor = LLMExtractor()
        result = extractor.extract_all("测试文本")
        assert "llm" in result
        assert "regex" in result
        assert "jieba" in result

    def test_extract_all_filters_duplicates(self):
        extractor = LLMExtractor()
        text = "ResNet 是一种深度学习网络。ResNet 常用于图像分类。"
        result = extractor.extract_all(text)

        # 正则/jieba 应该过滤掉与 LLM 重复的 ResNet
        regex_names = [e["name"] for e in result["regex"]]
        jieba_names = [e["name"] for e in result["jieba"]]

        assert "ResNet" not in regex_names
        assert "ResNet" not in jieba_names

    def test_regex_extract_validates_entity(self):
        extractor = LLMExtractor()
        result = extractor._regex_extract("测试文本")

        for entity in result["entities"]:
            assert len(entity["name"]) >= 2
            assert len(entity["name"]) <= 15
            assert entity["method"] == "regex"

    def test_jieba_extract_returns_keywords(self):
        extractor = LLMExtractor()
        result = extractor._jieba_extract("深度学习是机器学习的一个子集。")

        assert len(result["entities"]) > 0
        for entity in result["entities"]:
            assert entity["method"] == "jieba"
            assert "频率" in entity["description"] or "jieba" in entity["description"]

    def test_llm_extract_handles_empty_text(self):
        extractor = LLMExtractor()
        result = extractor._llm_extract("")
        assert result["entities"] == []
        assert result["relations"] == []

    def test_llm_extract_handles_api_error(self):
        extractor = LLMExtractor()
        # Mock API error
        import requests
        original_post = requests.post
        def mock_post(*args, **kwargs):
            class MockResponse:
                status_code = 500
                text = "Internal Server Error"
            return MockResponse()
        requests.post = mock_post

        result = extractor._llm_extract("测试文本")
        assert result["entities"] == []
        assert result["relations"] == []

        requests.post = original_post

    def test_llm_extract_handles_timeout(self):
        extractor = LLMExtractor()
        import requests
        original_post = requests.post
        def mock_post(*args, **kwargs):
            raise requests.exceptions.Timeout()
        requests.post = mock_post

        result = extractor._llm_extract("测试文本")
        assert result["entities"] == []
        assert result["relations"] == []

        requests.post = original_post

    def test_llm_extract_returns_valid_json(self):
        extractor = LLMExtractor()
        result = extractor._llm_extract("ResNet 是一种深度学习网络。")
        assert isinstance(result["entities"], list)
        assert isinstance(result["relations"], list)
        for entity in result["entities"]:
            assert "name" in entity
            assert "type" in entity
            assert "description" in entity
```

**Step 2: Run tests**

```bash
pytest tests/test_llm_extractor.py -v
```

Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_llm_extractor.py
git commit -m "test: 添加 LLMExtractor 完整测试套件"
```

---

### Task 6: Final integration test

**TDD scenario:** Integration test — run all tests

**Files:**
- Tests: `tests/test_wiki_db_libsql.py`, `tests/test_auto_importer.py`

**Step 1: Run all tests**

```bash
cd D:/class/project-config/langchain-rag
pytest tests/ -v --tb=short
```

Expected: All tests pass

**Step 2: Verify database stats**

```bash
python -c "
from rag_core.wiki_db_libsql import WikiDB
wiki = WikiDB()
stats = wiki.get_stats()
print(f'实体总数: {stats[\"total_entities\"]}')
print(f'关系统计: {stats[\"relationships\"]}')
"
```

Expected:
- 实体数 30-80 个（不是 416）
- 关系数合理（5-20 个）

**Step 3: Verify in browser**

```bash
start http://127.0.0.1:5000
```

Check:
- 知识图谱显示正确节点和连线
- 待审核区域有正则/jieba 的对比结果
- 实体类型多样化（不是只有蛊真人相关）

**Step 4: Commit**

```bash
git add -A
git commit -m "test: 集成测试通过，准备提交"
```

---

## Summary

**Files created:**
- `rag_core/llm_extractor.py` (new)
- `scripts/cleanup_and_reimport.py` (new)
- `tests/test_llm_extractor.py` (new)

**Files modified:**
- `rag_core/wiki_updater.py`
- `rag_core/auto_importer.py`

**Test results:**
- All existing tests pass
- New LLMExtractor tests pass (8 tests)

**Expected outcome:**
- 实体数从 416 降至 30-80 个（真实概念，不是碎片）
- 待审核区域有正则/jieba 对比结果
- 知识图谱显示正确节点和连线

---

## Handoff

Plan complete and saved to `docs/plans/20260726-llm-extraction-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - Fresh subagent per task with two-stage review. Better for plans with many independent tasks.

**2. Parallel Session (separate)** - Batch execution with human review checkpoints. Better when tasks are tightly coupled or you want more control between batches.

**Which approach?**
