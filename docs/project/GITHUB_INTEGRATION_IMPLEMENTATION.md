# GitHub 数据集成实施总结

> 阶段 3：GitHub 数据集成
> 实施时间：2026-07-10
> 状态: ⚠️ 部分完成（需要 GitHub API Key）

---

## 📋 实施内容

### 1. 修改 `github_collector.py`

#### 1.1 添加 `search_and_import_to_chroma()` 方法

```python
def search_and_import_to_chroma(self, query: str, max_results: int = 5, kb=None):
    """
    搜索 GitHub 仓库并直接导入 ChromaDB

    Args:
        query: 搜索关键词
        max_results: 最大结果数
        kb: 知识库实例（可选，默认自动创建）

    Returns:
        仓库信息列表
    """
    from langchain_core.documents import Document

    if kb is None:
        from rag_core.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()

    logger.info(f"搜索 GitHub 仓库并导入 ChromaDB: {query}")

    # 搜索仓库
    repos = self.search_repositories(query, max_results)

    if not repos:
        logger.warning(f"未找到相关仓库: {query}")
        return []

    results = []

    for repo in repos:
        full_name = repo.get("full_name")
        logger.info(f"正在导入仓库: {full_name}")

        # 获取 README
        readme_content = self.get_readme(full_name)

        # 构建文档内容
        content = f"""## {full_name}

{repo.get('description', '')}

**基本信息:**
- Stars: {repo.get('stargazers_count', 0)}
- Forks: {repo.get('forks_count', 0)}
- 语言: {repo.get('language', 'Unknown')}
- 创建时间: {repo.get('created_at', 'Unknown')}
- 更新时间: {repo.get('updated_at', 'Unknown')}

**Topics:** {', '.join(repo.get('topics', []))}

**README 预览:**
{readme_content[:500] if readme_content else '无 README'}
"""

        # 创建 Document
        doc = Document(
            page_content=content,
            metadata={
                'source': repo.get('html_url', ''),
                'news_title': full_name,
                'document_type': 'github_repo',
                'stars': repo.get('stargazers_count', 0),
                'forks': repo.get('forks_count', 0),
                'language': repo.get('language', ''),
                'topics': repo.get('topics', []),
            }
        )

        # 添加到 ChromaDB
        kb.vector_store.add_documents([doc])

        # 同步 Wiki 层（实体提取）
        kb._sync_wiki_layer([doc], f"github/{query}")

        results.append({
            'full_name': full_name,
            'stars': repo.get('stargazers_count', 0),
            'language': repo.get('language', ''),
            'topics': repo.get('topics', []),
            'html_url': repo.get('html_url', '')
        })

    logger.info(f"成功导入 {len(results)} 个仓库到 ChromaDB")
    return results
```

**功能特性**:
- ✅ 搜索 GitHub 仓库
- ✅ 获取 README 内容
- ✅ 自动导入 ChromaDB
- ✅ 同步 Wiki 层（实体提取）
- ✅ 保存元数据（Stars、Forks、语言、Topics）

### 2. 修改 `rag_cli.py`

#### 2.1 添加 `cmd_github()` 命令

```python
def cmd_github(args):
    """搜索 GitHub 仓库"""
    from tools.github_collector import GitHubCollector
    from tools.multi_source_kb import MultiSourceKB

    collector = GitHubCollector()
    kb = KnowledgeBase()

    # 导入到 ChromaDB
    results = collector.search_and_import_to_chroma(
        query=args.query,
        max_results=args.top_k,
        kb=kb
    )

    # 格式化输出
    multi_kb = MultiSourceKB()
    results_dict = {'github': results}
    output = multi_kb.format_results(results_dict)

    print(output)

    print(f"\n[INFO] 共导入 {len(results)} 个仓库到 ChromaDB")
    print(f"[INFO] 可以使用 'rag_cli.py search' 命令搜索这些仓库内容")
```

#### 2.2 添加命令行参数

```python
p_github = subparsers.add_parser("github", help="搜索 GitHub 仓库")
p_github.add_argument("query", help="搜索关键词")
p_github.add_argument("--top-k", type=int, default=5, help="返回结果数")
p_github.set_defaults(func=cmd_github)
```

#### 2.3 更新帮助文档

```python
# === 其他 ===
python rag_cli.py github "AI视频生成"           # 搜索 GitHub 仓库
```

---

## ✅ 测试结果

### 测试：GitHub 搜索

```bash
python scripts/rag_cli.py github "AI" --top-k 3
```

**结果**:
- ⚠️ GitHub API 返回 401 错误（Bad credentials）
- ❌ 未找到相关仓库
- ❌ 未导入到 ChromaDB

**错误原因**: `GITHUB_API_KEY` 环境变量未设置

---

## 🔧 配置要求

### GitHub API Key 配置

GitHub 集成需要配置 GitHub Personal Access Token：

1. 访问 https://github.com/settings/tokens
2. 生成新的 Token（`repo` 权限）
3. 设置环境变量：

```bash
# Windows (PowerShell)
$env:RAG_GITHUB_API_KEY = "your_github_token_here"

# Windows (CMD)
set RAG_GITHUB_API_KEY=your_github_token_here

# Linux/Mac
export RAG_GITHUB_API_KEY=your_github_token_here
```

4. 验证配置：

```bash
python scripts/rag_cli.py github "langchain" --top-k 2
```

---

## 📝 使用示例

### 1. 搜索 GitHub 仓库

```bash
python rag_cli.py github "AI视频生成" --top-k 5
```

### 2. 搜索并搜索仓库内容

```bash
# 1. 搜索 GitHub 仓库
python rag_cli.py github "langchain" --top-k 3

# 2. 搜索仓库内容
python rag_cli.py search "langchain" --top-k 5
```

### 3. 搜索特定语言的仓库

```bash
python rag_cli.py github "python" --top-k 5
python rag_cli.py github "javascript" --top-k 5
```

---

## 🎯 功能特性

### ✅ 已实现
- [x] GitHub 仓库搜索
- [x] README 内容获取
- [x] 自动导入 ChromaDB
- [x] Wiki 层实体提取
- [x] 元数据保存（Stars、Forks、语言、Topics）
- [x] 格式化输出（Markdown）

### ⚠️ 限制
- [ ] 需要 GitHub API Key
- [ ] API 速率限制（每分钟 40 次请求）
- [ ] 仓库数量限制（每次搜索最多 100 个）

---

## 📊 数据源优先级

| 优先级 | 数据源 | 适用场景 |
|--------|--------|----------|
| 1 | 本地 KB（ChromaDB） | 知识查询、历史文档 |
| 2 | Wiki 层（SQLite） | 实体查询、事实检索 |
| 3 | Tavily（实时） | 今日热点、最新新闻 |
| 4 | TrendRadar（趋势） | 平台热点、话题分析 |
| 5 | **GitHub（代码库）** | 技术问题、开源项目 |

---

## 🔧 技术细节

### 仓库信息结构

```python
{
    'full_name': 'langchain-ai/langchain',
    'stars': 12345,
    'language': 'Python',
    'topics': ['llm', 'ai', 'chatbot'],
    'html_url': 'https://github.com/langchain-ai/langchain'
}
```

### 文档元数据

```python
metadata = {
    'source': 'https://github.com/langchain-ai/langchain',
    'news_title': 'langchain-ai/langchain',
    'document_type': 'github_repo',
    'stars': 12345,
    'forks': 2345,
    'language': 'Python',
    'topics': ['llm', 'ai', 'chatbot']
}
```

---

## 📚 相关文档

- `docs/project/MULTI_SOURCE_INTEGRATION_PLAN.md` - 多源集成改进计划
- `docs/project/REALTIME_SEARCH_IMPLEMENTATION.md` - 实时搜索实施总结
- `tools/github_collector.py` - GitHub 数据收集工具
- `tools/multi_source_kb.py` - 多源知识库统一检索系统

---

## ➡️ 下一步

### 优化
- [ ] 添加 GitHub 搜索缓存机制
- [ ] 优化 README 获取性能
- [ ] 添加搜索历史记录
- [ ] 支持按语言/Stars 过滤

### 扩展
- [ ] 添加 Issue 分析
- [ ] 支持搜索仓库文件
- [ ] 添加仓库贡献者信息
- [ ] 支持搜索特定分支/标签

---

## ⚠️ 已知问题

### GitHub API 401 错误

**问题**: 搜索 GitHub 仓库时返回 `401 Bad credentials`

**原因**: 未配置 `RAG_GITHUB_API_KEY` 环境变量

**解决方案**: 按照上述"配置要求"设置 GitHub API Key

---

**状态**: ⚠️ 部分完成（需要 GitHub API Key）
**下一步**: 配置 GitHub API Key 并测试
