# 贝叶斯知识库分析工具使用指南

## 概述

`bayesian_analyzer.py` 是一个基于**朴素贝叶斯定理**的可复用知识库分析工具。它对知识库中的文档进行主题分类、置信度评估和文档排序。

## 核心原理

```
P(Category|Document) ∝ P(Document|Category) × P(Category)
```

- **先验概率 P(Category)**：各类别在知识库中的文档比例
- **条件概率 P(Word|Category)**：某词在某个类别中出现的概率（Laplace 平滑）
- **后验概率 P(Category|Document)**：文档属于某类别的置信度

## 使用方法

### 1. 分析知识库类别分布

```bash
python tools/bayesian_analyzer.py --analyze-categories
```

输出：
- 各类别文档数量和占比
- 分类器统计（先验概率、唯一词数）
- 抽样文档的分类结果

### 2. 带置信度的搜索

```bash
python tools/bayesian_analyzer.py "AI视频生成工具推荐" --top-k 5
```

输出：
- 匹配的文档列表
- 每个文档的预测类别和置信度
- 关键词匹配分数

### 3. 保存分析结果

```bash
python tools/bayesian_analyzer.py --analyze-categories --output-file results.json
```

## 预定义类别

| 类别 | 关键词 |
|------|--------|
| AI视频生成 | 视频生成, AI视频, 剪辑, thumbnail, 字幕 |
| 机器学习 | 机器学习, ML, 分类, 训练, 模型, BERT |
| 政策分析 | 政策, government, 产业, 低空经济 |
| 趋势情报 | 趋势, trend, 日报, Hotstar |
| 企业信息 | SpaceX, 马斯克, Tesla, 小米, 财报 |
| 员工信息 | 员工, employee, 人事 |
| 工具推荐 | 工具, tool, 推荐, software |
| 能源电力 | 电力, electricity, 水电, 能源 |

## 可扩展性

### 添加新类别

编辑 `CATEGORIES` 字典：

```python
CATEGORIES = {
    "AI视频生成": [...],
    "机器学习": [...],
    "新类别": ["关键词1", "关键词2"],
}
```

### 自定义分类器

```python
from tools.bayesian_analyzer import BayesianClassifier

classifier = BayesianClassifier()
classifier.train([
    ("这是一段关于机器学习的文本", "机器学习"),
    ("视频生成工具推荐", "AI视频生成"),
])

results = classifier.predict("如何使用AI制作视频", top_k=3)
for cat, prob in results:
    print("{}: {:.2%}".format(cat, prob))
```

## 输出示例

```
类别分布:
  机器学习: 12 个文档 (12.0%)
  政策分析: 19 个文档 (19.0%)
  ...

搜索结果:
1. [工具推荐] 置信度: 100.00%
   来源: 视频制作教程汇总报告.md
   内容: ### 12. awesome-video-editing - 视频编辑工具合集...
   关键词匹配: 2
```

## 注意事项

1. **依赖**：需要 `langchain`、`chromadb` 在项目路径中
2. **性能**：全量分析约 4000 文档，耗时 10-30 秒
3. **准确性**：基于关键词匹配，适合结构化良好的知识库
4. **网络**：避免使用向量搜索（可能触发模型下载）

## 与实际应用的关联

贝叶斯分类器在我们的中文文本分类项目中已经验证有效：
- MultinomialNB 是贝叶斯家族的直接应用
- 我们之前发现的 5 类语义重叠问题，也可以用贝叶斯后验概率来量化
