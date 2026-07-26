# 工具模块文档

本目录包含 RAG 知识库系统的各种工具模块。

---

## 📚 工具列表

### 1. tavily_search.py

**功能**：Tavily 搜索 API 封装

**用途**：
- 实时网络搜索
- 获取最新信息
- 趋势数据采集

**使用示例**：
```python
from tools.tavily_search import tavily_search

results = tavily_search(
    query="AI Agent 最新项目",
    max_results=20
)
```

---

### 2. bayesian_analyzer.py

**功能**：贝叶斯分类器

**用途**：
- 知识库文档分类
- 带置信度的搜索
- 主题分析

**使用示例**：
```python
from tools.bayesian_analyzer import BayesianClassifier

classifier = BayesianClassifier()
classifier.analyze_categories()
```

**详细文档**：`BAYESIAN_ANALYZER_README.md`

---

### 3. github_collector.py

**功能**：GitHub 数据收集器

**用途**：
- 从 GitHub API 获取热门项目
- 存储到 SQLite 数据库
- 导入到 ChromaDB 知识库

**使用示例**：
```python
from tools.github_collector import GitHubCollector

collector = GitHubCollector()
collector.fetch_data(
    query="language:python stars:>1000",
    max_results=20
)
collector.save_to_db()
collector.save_to_kb()
```

**功能特性**：
- 支持按语言、星标数、创建时间筛选
- 自动保存到 SQLite 和 ChromaDB
- 支持增量更新
- 生成 Markdown 文档

---

## 🔧 使用方法

### 环境要求

```bash
conda activate ml_env
pip install tavily-python requests
```

### 常用命令

```bash
# 分析知识库类别
python tools/bayesian_analyzer.py --analyze-categories

# Tavily 搜索
python tools/tavily_search.py "搜索关键词"

# GitHub 数据收集
python tools/github_collector.py --query "language:python stars:>1000" --max-results 20
```

---

## 📊 工具统计

| 工具 | 文件 | 功能 | 状态 |
|------|------|------|------|
| Tavily 搜索 | tavily_search.py | 实时网络搜索 | ✅ 可用 |
| 贝叶斯分析 | bayesian_analyzer.py | 文档分类 | ✅ 可用 |
| GitHub 收集 | github_collector.py | GitHub 数据采集 | ✅ 可用 |

---

## 📝 待办事项

- [ ] 添加更多搜索源（Jina、TrendRadar）
- [ ] 优化贝叶斯分类器性能
- [ ] 扩展 GitHub 收集器功能
- [ ] 添加工具测试用例

---

**最后更新**：2026-07-01
