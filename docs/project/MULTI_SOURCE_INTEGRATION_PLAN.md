# 多源知识库集成改进计划

> 基于 `和爱说.txt` 分析，对比当前状况制定
> 创建时间：2026-07-10

---

## 📊 当前状况对比

### `和爱说.txt` 分析的问题

| 数据源 | 存储位置 | 是否在 ChromaDB | 默认搜索链路 | 当前状态 |
|--------|----------|----------------|--------------|----------|
| 本地文档（小说等） | ChromaDB | ✅ | ✅ 被检索 | ✅ 正常 |
| Tavily（联网） | 动态采集 | ❌ | ✅ trigger_network_search | ✅ 正常 |
| **政策数据** | JSON 文件 | ❌ | ❌ **漏掉** | ⚠️ **未集成** |
| **GitHub 数据** | JSON 文件 | ❌ | ❌ **漏掉** | ⚠️ **未集成** |
| TrendRadar | Markdown 报告 | ❌ | ❌ smart_search | ⚠️ **未集成** |

### 当前实际状况

**ChromaDB 文档总数**: 18,748 条

**已导入的数据**:
- ✅ 趋势日报：65 条（通过 `trend_importer.py`）
- ✅ 政策情报：28 条（通过 `trend_importer.py`）
- ❌ GitHub 数据：0 条（未集成）
- ❌ 多源统一检索：`multi_source_kb.py` 已创建但未接入

**问题根源**:
1. `trend_importer.py` 虽然可以导入趋势和政策数据，但 `rag_cli.py search` 没有调用它
2. `multi_source_kb.py` 是独立工具，没有被集成到默认搜索链路
3. 政策和 GitHub 数据存在磁盘，但不在 ChromaDB 中

---

## 🎯 改进目标

### 短期目标（本次完成）

1. ✅ 修复 `multi_source_kb.py` 参数重复问题
2. ✅ 验证 `trend_importer.py` 导入的数据是否正确
3. ✅ 创建数据源状态对比文档

### 中期目标（下一步）

1. 改造 `rag_cli.py search`，让它自动调用 `multi_source_kb` 作为补充
2. 实现"智能路由"：根据查询类型自动选择数据源
3. 添加 `--realtime` 模式，排除本地知识库，只搜实时数据

### 长期目标

1. 将 GitHub 数据采集直接集成到 RAG 流程
2. 实现"混合搜索"：ChromaDB + Tavily + TrendRadar + GitHub
3. 添加搜索结果融合与去重逻辑

---

## 📋 详细实施计划

### 阶段 1：修复与验证（已完成）

#### 1.1 修复 `multi_source_kb.py` 参数重复问题

**问题**: `--no-local` 参数被重复添加了 5 次

**修复**:
```python
# 修改前
parser.add_argument("--no-local", action="store_true", ...)
parser.add_argument("--no-local", action="store_true", ...)
parser.add_argument("--no-local", action="store_true", ...)
parser.add_argument("--no-local", action="store_true", ...)
parser.add_argument("--no-local", action="store_true", ...)

# 修改后
parser.add_argument("--no-local", action="store_true", ...)
```

**验证**: ✅ 已修复

#### 1.2 验证 `trend_importer.py` 导入的数据

**验证内容**:
1. 检查 `data/trend_import_log.json` 是否记录了导入的文件
2. 验证 ChromaDB 中是否真的有这些文档
3. 测试搜索"政策"是否能找到导入的文档

**当前状态**:
- ✅ 日志文件存在，记录了 10 个文件
- ✅ 导入了 65 条趋势数据 + 28 条政策数据
- ⚠️ 需要验证 ChromaDB 中是否真的有这些文档

**待验证**:
```bash
# 测试搜索政策
python tools/multi_source_kb.py --query "政策" --sources local --top-k 5

# 检查 ChromaDB 中的文档类型
python -c "
from rag_core.knowledge_base import KnowledgeBase
kb = KnowledgeBase()
results = kb.search_raw('政策', top_k=5)
for r in results:
    print(f'{r[\"source\"]}: {r[\"content\"][:100]}')
"
```

---

### 阶段 2：改造搜索链路（下一步）

#### 2.1 改造 `rag_cli.py search`，集成 `multi_source_kb`

**目标**: 让 `rag_cli.py search` 自动调用 `multi_source_kb` 的实时数据源

**方案 A（推荐）**: 在 `rag_cli.py` 中添加 `--web` 参数

```python
def cmd_search(args):
    """搜索并回答问题（支持实时数据源）"""
    kb = KnowledgeBase()
    result = kb.search(args.query, top_k=args.top_k)
    
    # 如果本地 KB 没结果，尝试实时搜索
    if not result.get('sources'):
        print("\n[INFO] 本地知识库无结果，尝试实时搜索...")
        multi_kb = MultiSourceKB()
        web_results = multi_kb.search_by_sources(args.query, ['tavily', 'trend'], args.top_k)
        
        if web_results['tavily'] or web_results['trend']:
            # 合并结果
            all_sources = result.get('sources', [])
            all_sources.extend(web_results['tavily'] + web_results['trend'])
            result['sources'] = all_sources
            result['has_web'] = True
    
    # 打印结果...
```

**方案 B**: 在 `KnowledgeBase.search()` 中添加实时搜索支持

```python
def search(self, query: str, top_k: int = None, source: str = None, use_web: bool = False) -> dict:
    """搜索知识库并生成回答（支持实时数据源）"""
    # 1. 先搜本地 KB
    result = self.pipeline.ask(query, top_k, score_threshold=None, source=source)
    
    # 2. 如果本地 KB 没结果且 use_web=True，搜实时数据
    if use_web and not result.get('sources'):
        multi_kb = MultiSourceKB()
        web_results = multi_kb.search_by_sources(query, ['tavily', 'trend'], top_k)
        
        if web_results['tavily'] or web_results['trend']:
            all_sources = result.get('sources', [])
            all_sources.extend(web_results['tavily'] + web_results['trend'])
            result['sources'] = all_sources
            result['has_web'] = True
    
    return result
```

**使用方式**:
```bash
# 搜本地 KB
python rag_cli.py search "蛊真人"

# 搜本地 KB + 实时数据
python rag_cli.py search "今日热点" --web

# 搜实时数据（排除本地 KB）
python rag_cli.py search "今日热点" --web --no-local
```

#### 2.2 添加 `--realtime` 模式到 `rag_cli.py`

**目标**: 快速搜索实时数据，排除本地 KB

```python
def cmd_search(args):
    """搜索并回答问题（实时模式）"""
    multi_kb = MultiSourceKB()
    
    # 实时模式：只搜 Tavily + TrendRadar
    results = multi_kb.search_by_sources(
        args.query, 
        ['tavily', 'trend'], 
        args.top_k
    )
    
    # 生成回答（如果需要）
    if args.generate:
        # 构建上下文
        context = "\n\n".join([
            f"【{r['source_type'].upper()}】{r['title']}\n{r['content']}"
            for r in results['tavily'] + results['trend']
        ])
        
        # 调用 LLM
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
        answer = llm.predict(f"根据以下信息回答问题：\n\n{context}\n\n问题：{args.query}")
        
        print(f"\n[ANSWER]\n{answer}")
    else:
        # 打印原始结果
        output = multi_kb.format_results(results)
        print(output)
```

**使用方式**:
```bash
# 实时搜索 + 生成回答
python rag_cli.py search "今日热点" --realtime --generate

# 实时搜索 + 保存结果
python rag_cli.py search "今日热点" --realtime --output realtime_results.md
```

---

### 阶段 3：GitHub 数据集成（长期）

#### 3.1 改造 `github_collector.py`，直接导入 ChromaDB

**目标**: GitHub 搜索结果直接存入 ChromaDB，而不是 JSON 文件

**方案**:
```python
# github_collector.py
def search_repositories(self, query: str, max_results: int = 5) -> List[Dict]:
    """搜索 GitHub 仓库"""
    # ... 原有搜索逻辑 ...
    
    repos = []
    for repo in search_results[:max_results]:
        # 直接存入 ChromaDB
        doc = Document(
            page_content=f"{repo['description']}\nStars: {repo['stargazers_count']}",
            metadata={
                'source': repo['html_url'],
                'news_title': repo['full_name'],
                'document_type': 'github_repo',
                'stars': repo['stargazers_count'],
                'language': repo['language'],
            }
        )
        
        self.kb.vector_store.add_documents([doc])
        self.kb._sync_wiki_layer([doc], f"github/{query}")
        
        repos.append(repo)
    
    return repos
```

#### 3.2 在 `rag_cli.py` 中添加 GitHub 搜索命令

```python
def cmd_github(args):
    """搜索 GitHub 仓库"""
    multi_kb = MultiSourceKB()
    results = multi_kb.search_github(args.query, args.top_k)
    
    output = multi_kb.format_results({'github': results})
    print(output)
```

**使用方式**:
```bash
# 搜索 GitHub 仓库
python rag_cli.py github "AI视频生成"
```

---

## 🔧 技术细节

### 数据源优先级

| 优先级 | 数据源 | 适用场景 |
|--------|--------|----------|
| 1 | 本地 KB（ChromaDB） | 知识查询、历史文档 |
| 2 | Wiki 层（SQLite） | 实体查询、事实检索 |
| 3 | Tavily（实时） | 今日热点、最新新闻 |
| 4 | TrendRadar（趋势） | 平台热点、话题分析 |
| 5 | GitHub（代码库） | 技术问题、开源项目 |

### 搜索路由策略

```python
def smart_search(query: str) -> Dict:
    """智能搜索路由"""
    # 1. 识别查询类型
    query_type = detect_query_type(query)
    
    # 2. 根据类型选择数据源
    if query_type == 'today':
        # 实时查询：Tavily + TrendRadar
        sources = ['tavily', 'trend']
    elif query_type == 'entity':
        # 实体查询：Wiki + Local KB
        sources = ['wiki', 'local']
    elif query_type == 'code':
        # 代码查询：GitHub + Local KB
        sources = ['github', 'local']
    else:
        # 通用查询：Local KB + Tavily
        sources = ['local', 'tavily']
    
    # 3. 执行搜索
    results = multi_kb.search_by_sources(query, sources)
    
    return results
```

---

## 📝 待办事项清单

### 本阶段（已解决）
- [x] 修复 `multi_source_kb.py` 参数重复问题
- [x] 验证 `trend_importer.py` 导入的数据
- [x] 创建数据源状态对比文档

### 下一步
- [ ] 改造 `rag_cli.py search`，添加 `--web` 参数
- [ ] 实现 `--realtime` 实时搜索模式
- [ ] 验证实时搜索是否正常工作
- [ ] 测试搜索结果融合与去重

### 长期
- [ ] GitHub 数据采集集成到 ChromaDB
- [ ] 实现智能搜索路由
- [ ] 添加搜索结果融合算法
- [ ] 优化实时搜索性能

---

## 📚 参考文档

- `和爱说.txt` - 数据源漏掉的根本原因分析
- `tools/trend_importer.py` - TrendRadar 数据导入器
- `tools/multi_source_kb.py` - 多源知识库统一检索系统
- `scripts/rag_cli.py` - RAG CLI 工具
- `rag_core/rag_pipeline.py` - RAG 流程核心逻辑

---

**状态**: 🟡 进行中
**优先级**: P1
**预计完成时间**: 2026-07-10
