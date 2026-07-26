# KB Manager — 知识库管理系统

自动判断知识库覆盖度 → 缺则补 → 存留痕 → 时则清

```
langchain-rag/kb_manager/
├── __init__.py
├── agent_bridge.py      # Agent 决策入口：先查知识库，缺则触发采集
├── data_ingestor.py     # 调用 trend-radar 抓取 + 存原始数据到 raw/
├── analysis_archiver.py # 分析结果归档（带时间戳/版本/TTL）
├── cleanup_daemon.py    # 按 TTL 清理过期分析
├── config.py            # 配置（TTL 天数、采集源等）
└── utils.py             # 通用工具函数
```

## 核心工作流

```
用户提问
  → agent_bridge.check_coverage(query)
    → search_knowledge_base(query)
      → 命中且新鲜(<30天) → 直接回答
      → 未命中或过期 → data_ingestor.fetch_and_save()
        → 调用 trend-radar 采集
        → 原始数据存入 raw/
        → analysis_archiver.archive() 分析结果到 analysis/
        → 再回答用户
```

## 数据生命周期

- **原始数据** (`raw/`): 永久保留，带 `source`, `date_range`, `fingerprint`
- **分析结果** (`analysis/`): 带 `valid_until` (TTL)，默认 90 天
- **过期清理** (`cleanup_daemon.py`): 逻辑标记 `status=expired`，不物理删除
- **查询排除**: 默认只查 `status=active`，可指定 `include_expired=True`
