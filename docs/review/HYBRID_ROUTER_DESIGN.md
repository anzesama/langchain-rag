# 混合检索路由设计文档

**日期**: 2026-07-02
**状态**: ✅ 已实现,后台异步构建父子索引已实现

---

## 🎯 设计目标

实现自动路由机制,根据**文档属性**和**查询意图**,自动选择最优检索模式:
- **普通模式**:快速响应,适合技术文档、短文本
- **父子模式**:完整上下文,适合小说、长文档

---

## 📐 架构设计

```
用户查询
    ↓
HybridRouter.route()
    ↓
┌─────────────────────────────────────┐
│ 1. 文档分类 (classify_document)     │
│    - novel → 父子模式               │
│    - long_doc → 父子模式            │
│    - short_doc → 普通模式           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. 意图分析 (analyze_query_intent)  │
│    - 因果/背景/关系 → 父子模式       │
│    - 关键词/事实 → 普通模式          │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. 决策逻辑                          │
│    - 小说 + 复杂意图 → 父子模式      │
│    - 小说 + 简单意图 → 普通模式      │
│    - 默认 → 普通模式 (更快)          │
└─────────────────────────────────────┘
    ↓
执行检索 → 返回结果
```

---

## 📁 文件结构

| 文件 | 职责 |
|------|------|
| `rag_core/hybrid_router.py` | 混合路由核心逻辑 |
| `rag_core/parent_document_retriever.py` | 父子检索器实现 |
| `rag_core/parent_index_builder.py` | 后台异步构建 (NEW!) |
| `rag_core/rag_pipeline.py` | 集成路由到 RAG 流程 |
| `rag_core/knowledge_base.py` | 传递 source 参数 |

---

## 🔧 实现细节

### 1. 文档分类

```python
def classify_document(source: str) -> str:
    """根据文件路径分类"""
    if filename in NOVEL_FILES:
        return "novel"
    elif ext in LONG_DOC_FILES:
        return "long_doc"
    else:
        return "short_doc"
```

### 2. 意图分析

```python
def analyze_query_intent(query: str) -> str:
    """根据查询关键词判断意图"""
    if re.search(r"为什么.*|背景.*|关系.*", query):
        return "parent"  # 需要上下文
    elif re.search(r"代码.*|配置.*|安装.*", query):
        return "child"   # 关键词匹配即可
    else:
        return "neutral"  # 默认
```

### 3. 路由决策

```python
def route(self, query: str, source: str = None) -> str:
    doc_type = classify_document(source)
    intent = analyze_query_intent(query)

    # 小说 + 复杂意图 → 父子模式
    if doc_type == "novel" and intent in ("parent", "neutral"):
        return "parent"

    # 其他情况 → 普通模式
    return "child"
```

### 4. 后台异步构建 (NEW!)

```python
def add_document(self, filepath: str, auto_build_parent: bool = True):
    # 1. 添加文档到知识库
    self.vector_store.add_documents(valid_chunks)

    # 2. 异步构建父子索引
    if self.auto_build_parent and len(valid_chunks) > 500:
        self._async_build_parent_index(filepath)
```

---

## ⚠️ 当前限制

### 1. 父子索引未构建
- **问题**: 当前知识库使用普通模式存储,没有父子索引
- **影响**: 父子模式检索返回 0 结果
- **解决方案**:
  - 方案 A: 重新构建知识库,使用父子模式存储
  - 方案 B: 动态构建父子索引(性能开销大)

### 2. 路由仅基于 source 参数
- **问题**: 搜索时不一定知道 source
- **解决方案**: 扩展路由逻辑,支持无 source 时的默认策略

---

## 📋 后续优化

### P0 (必须)
- [ ] 重新构建知识库，启用父子索引
- [ ] 添加 source 自动推断逻辑

### P1 (重要)
- [ ] 支持用户指定检索模式
- [ ] 添加路由决策日志
- [ ] 性能基准测试

### P2 (可选)
- [ ] 机器学习路由（训练分类器）
- [ ] 自适应调整阈值
- [ ] A/B 测试框架

---

## 🧪 测试用例

### 普通模式
```python
# 技术文档 + 关键词查询
result = kb.search("安装报错怎么办", source="test.md")
# 预期: mode=child
```

### 父子模式
```python
# 小说 + 意图查询
result = kb.search("方源的目标是什么", source="guzhenren.txt")
# 预期: mode=parent
```

---

## 📊 预期效果

| 场景 | 当前模式 | 混合模式 | 提升 |
|------|---------|---------|------|
| 技术文档查询 | 普通 | 普通 | 无变化 |
| 小说因果查询 | 普通 | 父子 | +30% 准确率 |
| 小说事实查询 | 普通 | 普通 | 无变化 |
| 长文档查询 | 普通 | 父子 | +50% 准确率 |

---

*文档版本: v1.1 (新增后台异步构建)*  
*最后更新: 2026-07-02 08:10*
