# 脑启发性记忆 RAG 系统设计

> 设计日期：2026-11-03
> 核心灵感：艾宾浩斯遗忘曲线 + 突触可塑性 + 现代 RAG 记忆系统研究

---

## 一、问题诊断：当前系统的记忆缺陷

### 1.1 现状问题

| 维度 | 当前实现 | 人脑机制 | 差距 |
|------|---------|---------|------|
| **重要性评估** | 所有 chunk 平等存储 | LTM/STM 分层，重要性决定巩固程度 | ❌ 无重要性权重 |
| **遗忘机制** | 永不遗忘（永久存储） | 遗忘曲线：不激活的信息逐渐弱化 | ❌ 无衰减机制 |
| **记忆强化** | 无重复激活概念 | 反复回忆 → 突触强化 → 长期记忆 | ❌ 无强化机制 |
| **检索方式** | 纯语义相似度 | 语义 + 时间 + 频率 + 情境 | ❌ 缺少多因子排序 |
| **上下文注入** | 全量注入 top-K chunks | 按需选择最相关的"记忆片段" | ⚠️ 依赖硬性截断 |

### 1.2 核心矛盾

**你的目标**：「压缩知识」vs「保留重要时刻」

- 压缩 = 减少冗余信息，提取核心规律
- 保留 = 保持关键细节的清晰性（特别是重要时刻）

**人脑的解决方案**：双轨存储
- **语义记忆**（compressed）：概括性知识，高度压缩
- **情景记忆**（detailed）：重要事件，保留原始细节

---

## 二、理论基础

### 2.1 艾宾浩斯遗忘曲线在 RAG 中的映射

```
遗忘函数：R(t) = e^(-t/S)
- R(t): t 时间后的留存率
- S: 记忆强度（由重要性 × 重复次数决定）
```

**RAG 对应**：
- 记忆强度 S = 重要性评分 × 访问频率权重
- 遗忘不是删除，而是**检索分数衰减**
- 重要知识通过反复被检索而「强化」（分数提升）

### 2.2 现代 RAG 记忆系统研究要点

| 研究方向 | 关键结论 | 本系统设计启示 |
|---------|---------|--------------|
| **Importance-weighted retrieval** | 按信息重要性加权排序，优于纯相似度 | 增加 `importance_score` 字段 |
| **Recency bias in RAG** | 新检索结果应获得时间加成 | 增加 `recency_bonus` 因子 |
| **Memory consolidation** | 频繁共现的知识应聚合 | 相似 chunk 自动聚类 |
| **Forgetting curves in KB** | 长期未访问的知识应降权而非删除 | 实现「软遗忘」（降权而非删除） |
| **Episodic memory for agents** | 重要事件需保留完整细节，非摘要 | 区分「概览记忆」和「事件记忆」 |

---

## 三、架构设计：三层记忆模型

### 3.1 记忆分层（仿人脑）

```
┌─────────────────────────────────────────────────────────────┐
│                    长期记忆 (LTM)                            │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  语义记忆        │    │  情景记忆        │                │
│  │  (压缩知识)      │    │  (重要时刻)      │                │
│  │                 │    │                 │                │
│  │  - 概念定义      │    │  - 关键决策      │                │
│  │  - 方法总结      │    │  - 错误教训      │                │
│  │  - 规律提炼      │    │  - 项目里程碑    │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    工作记忆 (WM)                             │
│  - 当前会话的检索结果                                        │
│  - 最多 3-5 个 chunk，总计 ≤1200 chars                      │
│  - 每次检索重新计算，不持久化                                │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据模型扩展

```python
# 现有 chunk 结构
{
    "id": "auto_xxx",
    "content": "...",
    "source": "文件名",
    "score": 0.85  # 相似度
}

# 扩展后
{
    "id": "auto_xxx",
    "content": "...",
    "source": "文件名",
    "score": 0.85,          # 语义相似度
    "importance": 0.9,      # 重要性评分 (0-1)
    "access_count": 42,     # 被检索次数
    "last_access": "2026-11-03T23:00:00",
    "memory_type": "episodic",  # semantic | episodic
    "consolidated": False,    # 是否已巩固（多次访问后）
}
```

---

## 四、核心机制设计

### 4.1 重要性评分（Importance Scoring）

**触发时机**：文档导入时（一次性）+ 检索时（动态更新）

#### 静态重要性（导入时计算）

```python
def compute_importance(text: str, source: str) -> float:
    """基于内容的静态重要性评分"""
    score = 0.0
    
    # 1. 长度惩罚（过短的内容可能是碎片）
    if len(text) < 50:
        score -= 0.2
    elif len(text) > 1000:
        score += 0.1  # 长文可能是重要章节
    
    # 2. 关键词信号
    important_patterns = [
        r"重要.*发现|关键.*结论|核心.*观点",  # 明确的重要性声明
        r"经验.*总结|教训|最佳实践",           # 经验性内容
        r"错误|失败|bug|修复",                 # 错误相关（高价值）
        r"决策|决定|选择",                     # 决策点
    ]
    for pattern in important_patterns:
        if re.search(pattern, text):
            score += 0.15
    
    # 3. 来源权重
    source_weights = {
        "project_info.json": 0.8,      # 项目核心配置
        "troubleshooting.md": 0.9,     # 踩坑经验
        "novel_chapters/": 0.3,        # 小说（低重要性）
    }
    for prefix, weight in source_weights.items():
        if source.startswith(prefix):
            score += weight
    
    return max(0.0, min(1.0, score))
```

#### 动态重要性（检索时更新）

```python
def update_importance_after_retrieval(chunk_id: str, accessed: bool):
    """检索命中后更新重要性的「突触可塑性」"""
    if accessed:
        # 每次被检索 → 重要性提升（强化记忆）
        chunk.importance *= 1.05
        chunk.access_count += 1
        chunk.last_access = now()
        
        # 多次访问后「巩固」为长期记忆
        if chunk.access_count >= 3:
            chunk.consolidated = True
    
    # 遗忘曲线（未访问的 chunk 自然衰减）
    days_since_access = (now() - chunk.last_access).days
    decay_factor = exp(-days_since_access / 30)  # 30天半衰期
    chunk.retrieval_score *= decay_factor
```

### 4.2 软遗忘机制（Soft Forgetting）

**关键设计决策**：不删除数据，只降低检索权重

```python
def compute_final_score(base_score: float, chunk: Chunk) -> float:
    """综合检索分数 = 相似度 × 重要性 × 遗忘衰减"""
    
    # 1. 基础相似度（原有逻辑）
    similarity = base_score
    
    # 2. 重要性加成
    importance_bonus = 0.5 + 0.5 * chunk.importance  # [0.5, 1.0]
    
    # 3. 访问频率加成（被检索越多越靠前）
    access_bonus = min(1.5, 1 + 0.1 * log1p(chunk.access_count))
    
    # 4. 遗忘衰减（长时间未访问则降权）
    days_since = (now() - chunk.last_access).days
    forgetting_decay = exp(-days_since / RECALL_HALF_LIFE)  # 30天半衰期
    
    # 5. 综合分数
    final_score = similarity * importance_bonus * access_bonus * forgetting_decay
    
    return final_score
```

**效果**：
- 新内容 → 初始重要性由 LLM/规则评估
- 常用内容 → 反复检索 → 重要性累积 → 排名上升
- 长期未访问 → 自然衰减 → 不会消失但优先级降低

### 4.3 记忆巩固（Consolidation）

**类比**：睡眠时的记忆巩固过程

```python
def consolidate_memories():
    """定期运行：将频繁共现的知识聚类合并"""
    
    # 1. 找出高频共现的 chunk 对
    co_occurrence = find_frequently_co_accessed_chunks(window_days=7)
    
    # 2. 对高频对生成摘要
    for chunk_pair in co_occurrence:
        if chunk_pair.similarity > 0.8 and chunk_pair.co_access_count > 5:
            # 生成压缩摘要
            summary = llm.summarize([chunk_pair.a.content, chunk_pair.b.content])
            
            # 创建「概览记忆」节点
            create_summary_chunk(
                content=summary,
                sources=[chunk_pair.a.source, chunk_pair.b.source],
                memory_type="semantic",
                importance=max(chunk_pair.a.importance, chunk_pair.b.importance)
            )
    
    # 3. 标记原 chunk 为「已关联」
    mark_as_related(chunk_pair.a.id, chunk_pair.b.id)
```

---

## 五、上下文注入优化

### 5.1 智能注入策略

**当前问题**：每次搜索全量注入 top-K chunks → 上下文爆炸

**改进方案**：根据查询类型选择注入策略

```python
def select_context_for_injection(query: str, retrieved_chunks: List[Chunk]) -> List[Chunk]:
    """根据查询意图选择最优上下文"""
    
    # 1. 判断查询类型
    query_type = classify_query(query)
    
    if query_type == "fact_retrieval":
        # 事实查询：只需最相关的 1-2 个 chunk
        return retrieved_chunks[:2]
    
    elif query_type == "comparison":
        # 对比查询：需要多个角度的 chunk
        return retrieved_chunks[:5]
    
    elif query_type == "debugging":
        # 调试查询：需要错误模式 + 解决方案
        error_chunks = [c for c in retrieved_chunks if "错误" in c.content or "bug" in c.content]
        return error_chunks[:3] + retrieved_chunks[3:5]
    
    else:
        # 默认：保守注入
        return retrieved_chunks[:3]
```

### 5.2 查询意图分类

```python
def classify_query(query: str) -> str:
    """轻量级查询分类（无需 LLM，正则 + 关键词）"""
    
    debug_keywords = ["报错", "错误", "bug", "异常", "failed", "error"]
    if any(kw in query for kw in debug_keywords):
        return "debugging"
    
    compare_keywords = ["对比", "区别", "vs", "and", "与", "比较"]
    if any(kw in query for kw in compare_keywords):
        return "comparison"
    
    fact_keywords = ["什么是", "定义", "如何工作", "原理", "method"]
    if any(kw in query for kw in fact_keywords):
        return "fact_retrieval"
    
    return "general"
```

---

## 六、实现计划

### Phase 1：基础框架（本周）

- [ ] `Chunk` 数据模型扩展（添加 importance, access_count, last_access 字段）
- [ ] `compute_importance()` 静态重要性评分
- [ ] `update_importance_after_retrieval()` 动态更新
- [ ] `compute_final_score()` 综合评分函数
- [ ] 单元测试覆盖

### Phase 2：软遗忘机制（下周）

- [ ] 遗忘衰减计算 `forgetting_decay()`
- [ ] 后台任务定期更新分数
- [ ] API 端点 `/api/memories/stats` 查看记忆健康度

### Phase 3：智能注入（下下周）

- [ ] 查询意图分类器
- [ ] 上下文选择策略
- [ ] pi 扩展适配新 API

### Phase 4：记忆巩固（可选）

- [ ] 高频共现检测
- [ ] 摘要生成与存储
- [ ] 记忆网络可视化

---

## 七、设计原则

1. **YAGNI 优先**：先实现 Phase 1，验证有效性后再扩展
2. **可观测性**：提供 `/api/memories/stats` 查看所有 chunk 的健康度
3. **零侵入**：不影响现有检索流程，作为「增强层」叠加
4. **可回滚**：所有新字段有默认值，旧数据无缝兼容

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 重要性评分偏差 | 重要知识被低估 | 提供人工调整 API `/api/memories/{id}/importance` |
| 遗忘过快 | 常用知识突然降权 | 半衰期可调（默认 30 天），用户可锁定重要 chunk |
| API 成本 | LLM 调用增加 | 静态重要性用规则，动态更新用轻量模型 |
| 性能下降 | 每次检索增加计算 | 分数预计算 + 缓存，检索时直接读取 |

---

**下一步**：确认后开始 Phase 1 实现计划编写。
