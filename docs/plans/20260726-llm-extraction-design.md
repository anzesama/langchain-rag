# LLM 驱动的实体/关系提取

> 日期：2026-07-26
> 状态：设计阶段
> 相关分支：main

## 问题

`wiki_updater.py` 的实体/关系提取使用蛊真人小说的硬编码正则，对其他类型文档完全无效：
- AAAMLP-CN（机器学习）导入 416 个实体，大多数是截断句子碎片
- 关系提取同样只认"持有/属于/主修/师承"等小说动词

## 方案

用 Agnes API（LLM）替换正则作为主要提取手段。正则 + jieba 作为辅助参考。

### 三通道提取架构

```
┌─────────────────────────────────────────────────────┐
│                    auto_importer                     │
│                  (已有分块, ~1000 tokens/块)          │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                 llm_extractor.py                     │
├─────────────────────────────────────────────────────┤
│  通道 1: Agnes LLM        → 自动批准, 直接入库        │
│  通道 2: 正则(regex)      → 去重后 pending, 对比参考   │
│  通道 3: jieba 关键词     → 去重后 pending, 对比参考   │
└─────────────────────────────────────────────────────┘
```

### 数据流

```
文档 → 分块(每块~1000字符) 
     → 逐块调用 Agnes API:
         Prompt: "请从以下文本中提取关键实体(概念/方法/工具/人物/框架/评估指标等)..."
         Response: {entities: [{name, type, description}], relations: [{source, target, type, description}]}
     → LLM 结果: 自动去重 → 写入 entities/relations 表(status=approved)
     → 正则/jieba 结果: 与 LLM 结果去重 → 写入 pending_reviews 表
```

### 与知识库核心功能的关系

改动仅影响 `entities` 和 `relations` 表（WikiDB），不影响向量存储和 FAISS 索引。

```
                        文档导入
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         分块+向量存储   实体提取      关系提取
        (不受影响)      (llm_extractor) (llm_extractor)
```

- 向量检索：完全不变
- 知识库问答：实体/关系作为增强，但不是必须的
- 图谱展示：仅读取 entities/relations 表，表结构不变

---

## 实现

### 新增文件

#### `rag_core/llm_extractor.py`

核心类 `LLMExtractor`：

```python
class LLMExtractor:
    def __init__(self):
        # Agnes API 配置来自 rag_config
        self.api_key = AGNES_API_KEY
        self.api_base = AGNES_API_BASE
        self.model = "agnes-2.0-flash"
    
    def extract_all(self, text: str, source: str) -> dict:
        """
        三路提取合并
        Returns: {
            'llm': [LLMEntity, ...],
            'regex': [Entity, ...],    # 与 LLM 去重后的
            'jieba': [Entity, ...]     # 与 LLM 去重后的
        }
        """
    
    def _llm_extract(self, text: str) -> LLMResult:
        """调用 Agnes API 提取实体和关系"""
    
    def _regex_extract(self, text: str) -> list:
        """正则提取"""
    
    def _jieba_extract(self, text: str) -> list:
        """jieba TF-IDF 关键词提取"""
```

#### Prompt 设计

```
你是一个知识图谱实体提取专家。请从以下文本中提取关键实体和关系。

要求：
1. 实体类型自由发挥，常见：概念、方法、算法、工具、框架、人物、数据集、评估指标、论文、模型
2. 提取完整的、独立的命名实体，不要提取不完整的字符片段
3. 每个实体含：name(中/英均可), type(自定义), description(一句话)

4. 提取实体间明确存在的关系，关系类型自由发挥，常见：包含、使用、改进、基于、属于、对比、实现

请以严格JSON格式返回：
{
  "entities": [
    {"name": "交叉验证", "type": "方法", "description": "将数据集分为K折,轮流作为训练集和验证集的方法"}
  ],
  "relations": [
    {"source": "交叉验证", "target": "过拟合", "type": "对抗", "description": "交叉验证用于检测和防止过拟合"}
  ]
}

文本：
{text}
```

### 修改文件

#### `rag_core/wiki_updater.py`
- `scan_new_entities` / `scan_new_relations` 改为调用 `LLMExtractor.extract_all`
- 原有正则 → 保留为 `_regex_extract`，传给 LLMExtractor 作为通道 2
- 删除硬编码的蛊真人 `_noise_words` 和 `_entity_patterns`

#### `rag_core/auto_importer.py`
- `_import_file` → 调用 `LLMExtractor.extract_all` 替代 `WikiUpdater.batch_add_from_text`

#### `scripts/wiki_manager_web.py`
- 审核页面增加"LLM提取结果"和"正则/jieba对比结果"两个分区

### 降级策略

| 情况 | 行为 |
|------|------|
| Agnes API 可用 | LLM 自动批准, Regex/Jieba pending 对比 |
| Agnes API 超时/限流 | 跳回正则+Jieba, 全 pending |
| 全部不可用 | 跳过,日志告警 |

---

## 数据清理

- 删除 `storage/knowledge_base.db`
- 重新导入 AAAMLP-CN
- 清理后预期：实体数 30-80 个（真实概念，不是碎片）

---

## 实现计划

1. 新增 `rag_core/llm_extractor.py`
2. 修改 `rag_core/wiki_updater.py`
3. 修改 `rag_core/auto_importer.py`
4. 清理数据库, 重新导入验证
5. 提交