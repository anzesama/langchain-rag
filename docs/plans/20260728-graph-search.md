# 图搜索标签页 — 完成记录

> **实施日期**：2026-07-28
> **分支**：`feature/llm-extraction`
> **状态**：✅ 已完成

---

## 功能概述

Web 页面新增"图搜索"标签页，输入关键词对知识图谱关系库进行向量检索，用 ECharts 力导向图可视化。

**搜索流程**：
1. 前端 `POST /api/graph` → 后端调用 `graph_retriever.retrieve()`（向量召回 + 1-hop 扩展）
2. 返回节点 + 边 + 事实列表
3. ECharts 渲染子图（种子节点红色，扩展节点彩色）

**交互功能**：
- 搜索框 + Enter 键
- 种子节点（向量命中）红色大号标识
- 节点点击 → 向量召回 + 钻取邻居 → 追加到当前子图
- 右侧关联事实列表
- 清空按钮

---

## 代码变更

**文件**：`scripts/wiki_manager_web.py`

**增量**：~270 行

| 区域 | 内容 |
|------|------|
| 导航 | `<button class="nav-tab" data-panel="graph-search">图搜索</button>` |
| HTML 面板 | `panel-graph-search`：搜索栏 + 子图画布 + 事实列表 |
| JS 全局变量 | `gsChart`, `gsNodes`, `gsEdges`, `gsFactList` |
| `graphSearch()` | 异步调用 `/api/graph`，更新数据并渲染 |
| `renderGraphSearch()` | ECharts force 布局，种子节点红色 (`#e53935`) |
| `expandNode(name)` | 点击节点 → 调用 API → 去重追加边和节点 |
| `renderFactList()` | 关联事实 → 右侧面板 |
| `clearGraphSearch()` | 清空全量数据 |
| 路由 | `POST /api/graph`：调用 `retrieve(query, top_k, hops=1)` |

---

## 实施总结

### 问题与修复

| 问题 | 根因 | 修复 |
|------|------|------|
| JS 语法错误 `Uncaught SyntaxError` | Python 三重引号字符串中转义错误 | 用事件代理替代 inline onclick |
| 图搜索节点不在实体库中 | 向量库 (`chunks` 表) 残留旧索引（337 条），不在实体表中 | 清空 `chunks` 表，脚本重建索引 |
| 低质量实体（单字、超长文本） | 早期 LLM 提取质量低 | 删除 ≤3 字或 >80 字实体 119 个 |
| tooltip 与钻取引用错误 | `_content.name` vs `_raw.name` | 改为 `_raw.name` |

### 当前数据

- **实体**：355（删除了低质量 119 个）
- **关系**：70 条
- **向量库**：只存有效关系索引，`chunks` 中 70 条

---

## 已知局限

- **edges 数为 0**：关系数据以 entity_id 关联，关系中 entity_name 来自 LLM 提取，部分关系链未匹配（需后续优化提取质量）
- **钻取展开依赖 API 调用**：点击单个节点会触发 `/api/graph` 搜索，建议先验证关系存在

---

## Commits

```
1e35d41 fix: tooltip 和点击钻取中 _content → _raw 属性引用错误
e81dd59 feat: showPanel 集成图搜索标签页切换 + resize 处理
034afe3 feat: 图搜索 JS 逻辑 — ECharts 子图渲染 + 节点钻取 + 事实列表
aa4106f feat: 新增图搜索标签页 + 面板 HTML（搜索栏 + 子图 + 事实列表）
d60597c feat: 新增 POST /api/graph 图搜索路由 (向量召回 + 1-hop)
```