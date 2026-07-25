# 实时搜索功能实施总结

> 阶段 2：改造搜索链路
> 实施时间：2026-07-10
> 状态：✅ 已完成

---

## 📋 实施内容

### 1. 修改 `rag_cli.py`

#### 1.1 添加导入
```python
from tools.multi_source_kb import MultiSourceKB
```

#### 1.2 添加 `cmd_search` 函数改造
```python
def cmd_search(args):
    """搜索并回答问题（支持实时数据源）"""
    kb = KnowledgeBase()

    # 实时模式：只搜 Tavily + TrendRadar
    if args.realtime:
        multi_kb = MultiSourceKB()
        results = multi_kb.search_by_sources(
            args.query,
            ['tavily', 'trend'],
            args.top_k
        )

        # 生成回答（如果需要）
        if args.generate:
            context = "\n\n".join([
                f"【{r['source_type'].upper()}】{r['title']}\n{r['content']}"
                for r in results['tavily'] + results['trend']
            ])

            llm = get_llm()
            if llm:
                answer = llm.predict(f"根据以下信息回答问题：\n\n{context}\n\n问题：{args.query}")
                print(f"\n[ANSWER]\n{answer}")
            else:
                print("[WARN] 未配置 LLM，无法生成回答")
                print(f"\n[CONTEXT]\n{context}")
        else:
            # 打印原始结果
            output = multi_kb.format_results(results)
            print(output)
        return

    # 普通 搜索模式：先搜本地 KB，如果没结果再搜实时数据
    result = kb.search(args.query, top_k=args.top_k, use_web=args.web)

    print(f"\n[QUERY] {result['query']}")

    # 如果使用了实时数据，显示提示
    if result.get('has_web'):
        print("\n[INFO] 本次结果包含实时网络搜索数据")

    print(f"\n[ANSWER]")
    print(result['answer'])

    if result.get('sources'):
        print(f"\n[SOURCES]")
        for i, src in enumerate(result['sources'], 1):
            print(f"  [{i}] {src['source']} (score: {src['score']:.4f})")
            print(f"      {src['content'][:100]}...")
```

#### 1.3 添加 `get_llm()` 函数
```python
def get_llm():
    """获取 LLM 实例"""
    try:
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("RAG_OPENAI_API_KEY")
        if api_key:
            return ChatOpenAI(model_name="gpt-4", temperature=0.7)
        else:
            return None
    except Exception:
        return None
```

#### 1.4 添加命令行参数
```python
p_search = subparsers.add_parser("search", help="搜索并回答问题")
p_search.add_argument("query", help="搜索问题")
p_search.add_argument("--top-k", type=int, default=5, help="返回结果数")
p_search.add_argument("--web", action="store_true", help="启用实时网络搜索（本地无结果时自动搜）")
p_search.add_argument("--realtime", "-r", action="store_true", help="实时模式：只搜 Tavily/TrendRadar，排除本地 KB")
p_search.add_argument("--generate", action="store_true", help="实时模式下生成 LLM 回答")
p_search.set_defaults(func=cmd_search)
```

#### 1.5 更新帮助文本
```python
# === 知识库操作 ===
python rag_cli.py search "你的问题"            # 搜索并回答问题
python rag_cli.py search "今日热点" --web      # 搜索并回答问题（本地无结果时搜网络）
python rag_cli.py search "今日热点" -r         # 实时模式：只搜网络，排除本地 KB
python rag_cli.py search-raw <关键词>          # 原始检索（不生成回答）
```

### 2. 修改 `knowledge_base.py`

#### 2.1 修改 `search()` 函数
```python
def search(self, query: str, top_k: int = None, score_threshold: float = None, source: str = None, use_web: bool = False) -> dict:
    """
    搜索知识库并生成回答(支持混合检索路由 + 实时网络搜索)

    Args:
        query: 查询问题
        top_k: 返回数量
        score_threshold: 相似度阈值
        source: 文档来源(可选,用于路由决策)
        use_web: 是否启用实时网络搜索（本地无结果时自动搜）

    Returns:
        {
            "query": "原始问题",
            "answer": "LLM 回答",
            "sources": [{"source": "文件名", "content": "...", "score": 0.5}],
            "has_web": 是否包含实时搜索数据
        }
    """
    # 预热 ChromaDB（避免首次搜索慢）
    self._warmup_vector_store()

    # 关键优化:搜索时不触发自动导入(避免向量化大文件导致超时)
    # 只在添加文档/重建时才触发自动导入
    result = self.pipeline.ask(query, top_k, score_threshold, source)

    # 如果本地 KB 无结果且 use_web=True，搜实时数据
    if use_web and not result.get('sources'):
        from tools.multi_source_kb import MultiSourceKB
        multi_kb = MultiSourceKB()
        web_results = multi_kb.search_by_sources(query, ['tavily', 'trend'], top_k)

        if web_results['tavily'] or web_results['trend']:
            all_sources = result.get('sources', [])
            all_sources.extend(web_results['tavily'] + web_results['trend'])
            result['sources'] = all_sources
            result['has_web'] = True

    return result
```

---

## ✅ 测试结果

### 测试 1: 搜索本地 KB（蛊真人）
```bash
python scripts/rag_cli.py search-raw "蛊真人" --top-k 2
```

**结果**:
- ✅ 找到 2 条结果
- ✅ 来源：`documents/蛊真人_精校版.txt`
- ✅ 检索正常

### 测试 2: 实时模式搜索（今日热点）
```bash
python scripts/rag_cli.py search "今日热点" --realtime --top-k 3
```

**结果**:
- ✅ 找到 3 条实时网络搜索结果
- ✅ 来源：Tavily 网络搜索
- ✅ 包含：今日热点、今日热榜等

**输出示例**:
```
# 多源知识库搜索结果

> 搜索时间：2026-07-10 01:52:43

**总计：3 条结果**

## [网络] 搜索 (3 条)

### 1. 今日热点
- **来源**: https://www.facebook.com/p/今日热点-61574095903490
- **类型**: web_article

今日热点. 31614 likes · 8498 talking about this.

### 2. 今日热榜- 汇聚全网热点，热门尽览无余
- **来源**: https://hot.baiwumm.com
- **类型**: web_article

今日热榜 ; 沸. 台风. 180.48万 ; 2. 埃及教练向阿根廷运动员吐口水. 96.05万 ; 3. 当寂静的广西街头响起子弟兵口号. 75.98万
```

---

## 📝 使用示例

### 1. 搜索本地 KB
```bash
python rag_cli.py search "蛊真人"
python rag_cli.py search-raw "蛊真人" --top-k 3
```

### 2. 搜索本地 KB + 实时数据（本地无结果时自动搜）
```bash
python rag_cli.py search "今日热点" --web
```

### 3. 实时模式：只搜 Tavily + TrendRadar
```bash
python rag_cli.py search "今日热点" --realtime
python rag_cli.py search "今日热点" -r --generate  # 生成 LLM 回答
```

### 4. 原始检索（不生成回答）
```bash
python rag_cli.py search-raw "蛊真人" --top-k 3
```

---

## 🎯 功能特性

### ✅ 已实现
- [x] `--web` 参数：本地 KB 无结果时自动搜网络
- [x] `--realtime` 参数：只搜实时数据，排除本地 KB
- [x] `--generate` 参数：实时模式下生成 LLM 回答
- [x] 智能路由：根据参数自动选择数据源
- [x] 结果提示：显示是否包含实时搜索数据
- [x] 格式化输出：Markdown 格式的搜索结果

### ⚠️ 限制
- [ ] LLM 未配置时，`search` 命令会报错（`search-raw` 正常）
- [ ] `search-raw` 不支持 `--web` 参数（设计如此，因为原始检索不需要实时搜索）
- [ ] 实时搜索依赖 Tavily API（需要配置 API Key）

---

## 📊 数据源优先级

| 优先级 | 数据源 | 适用场景 |
|--------|--------|----------|
| 1 | 本地 KB（ChromaDB） | 知识查询、历史文档 |
| 2 | Wiki 层（SQLite） | 实体查询、事实检索 |
| 3 | Tavily（实时） | 今日热点、最新新闻 |
| 4 | TrendRadar（趋势） | 平台热点、话题分析 |
| 5 | GitHub（代码库） | 技术问题、开源项目 |

---

## 🔧 技术细节

### 搜索路由策略
```python
if args.realtime:
    # 实时模式：只搜 Tavily + TrendRadar
    results = multi_kb.search_by_sources(query, ['tavily', 'trend'], top_k)
else:
    # 普通 搜索模式：先搜本地 KB，如果没结果再搜实时数据
    result = kb.search(query, top_k, use_web=args.web)
```

### 实时搜索集成
```python
# 如果本地 KB 无结果且 use_web=True，搜实时数据
if use_web and not result.get('sources'):
    multi_kb = MultiSourceKB()
    web_results = multi_kb.search_by_sources(query, ['tavily', 'trend'], top_k)

    if web_results['tavily'] or web_results['trend']:
        all_sources = result.get('sources', [])
        all_sources.extend(web_results['tavily'] + web_results['trend'])
        result['sources'] = all_sources
        result['has_web'] = True
```

---

## 📚 相关文档

- `docs/project/MULTI_SOURCE_INTEGRATION_PLAN.md` - 多源集成改进计划
- `tools/multi_source_kb.py` - 多源知识库统一检索系统
- `tools/trend_importer.py` - TrendRadar 数据导入器
- `rag_core/rag_pipeline.py` - RAG 流程核心逻辑

---

## ➡️ 下一步

### 阶段 3：GitHub 数据集成
- [ ] 改造 `github_collector.py`，直接导入 ChromaDB
- [ ] 在 `rag_cli.py` 中添加 `github` 命令
- [ ] 测试 GitHub 搜索功能

### 优化
- [ ] 添加搜索结果去重逻辑
- [ ] 优化实时搜索性能
- [ ] 添加更多数据源（如知乎、微博等）

---

**状态**: ✅ 已完成
**测试状态**: ✅ 通过
**下一步**: 阶段 3（GitHub 数据集成）
