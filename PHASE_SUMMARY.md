# 阶段复盘：Phase 6 - 文档更新（libsql 迁移）
- 时间：2026-07-26 02:00
- 状态：✅ 完成

---

# 阶段复盘：知识图谱修复 + 图搜索重构 + Canvas 可视化
- 时间：2026-07-29 01:55
- 状态：✅ 完成

## ✅ 做得好的点
- ECharts dataIndex bug 排查彻底：同一页面图搜索正常但知识图谱报错，定位为大数据量触发
- 图搜索从向量库改为 SQL 直查，速度更快且不依赖向量库
- Canvas 力导向布局自研，零外部依赖，200 帧动画
- 知识库向量库成功导入 630 个 AAAMLP-CN chunks

## 📝 实现内容

### 1. ECharts 知识图谱 → Canvas 力导向
- **问题**：ECharts 5.3.3/5.4.3 force layout 在知识图谱（57 节点 + 76 边）初始化报 `TypeError: Cannot set properties of undefined (setting 'dataIndex')`
- **排查**：去掉 category、用名字字符串做 source/target、降级版本均无效
- **关键发现**：图搜索（2-5 节点）用同一版本 ECharts 正常，大数据量关联
- **方案**：Canvas 手写力导向，排斥力 + 弹簧力 + 中心引力 + 阻尼
- **功能**：节点拖拽、悬停高亮、点击详情、PNG 导出

### 2. 图搜索 /api/graph 重写
- **原问题**：图搜索依赖向量库查找 seed 实体，但向量库存 chunks 而非关系
- **方案**：retriever.py 纯 SQL 方案
  - 实体名模糊匹配（完全匹配 > 包含匹配 > jieba 分词匹配）
  - 关系索引 + BFS 扩展图
  - 用名字字符串而非 entity_id(UUID) 查关系
- **修复**：设置 `conn.row_factory = sqlite3.Row` 支持列名访问

### 3. wiki_db_libsql.py 属性安全解析
- `_safe_json_load()` 方法处理非 JSON 格式的 properties 字段
- 纯文本 auto-wrapper 为 `{"text": value}`

### 4. 向量库重建
- 使用 `VectorStoreManager()` 直接导入 AAAMLP-CN 15 文件 630 chunks

## 🐛 遇到的问题
- **ECharts dataIndex bug**：5.3.3 和 5.4.3 在 knowledge graph 下均不可用
- **SQLite Row 访问**：默认返回 tuple 需显式设 `row_factory = sqlite3.Row`
- **retriever get_relations 传 UUID 非名称**：误传 entity_id(UUID) 造成空结果

## 📦 产出物
- `rag_core/graph_retriever/retriever.py` — 全面重写为纯 SQL
- `rag_core/wiki_db_libsql.py` — `_safe_json_load()` 方法
- `scripts/wiki_manager_web.py` — Canvas 力导向布局替代 ECharts
- Git: `feature/llm-extraction`, commit `2326cdf`

## ➡️ 下一步
- 关系提取：jieba TF-IDF 基础上支持 LLM 精炼
- 领域词表：补充更多专业术语关系
- 审核面板：支持按类型筛选删除

---

# 阶段复盘：Web 功能扩展（知识图谱 + 图搜索 + 审核清理）
- 时间：2026-07-28
- 状态：✅ 完成

## ✅ 做得好的点
- 图搜索用 ECharts 子图渲染，复用现有图表模式
- 审核清理用事件代理解决 Python 模板转义问题
- 数据清理自动化：删除单字/超长文本实体 119 个
- 踩坑记录完整：向量库旧索引、ChromaDB libsql 混用、转义错误

## 📝 实现内容

### 知识图谱页面优化
- `/api/entities` 返回 500 条，优先有关系的实体
- `/api/relations` 返回 500 条，过滤空 target_name
- 图谱数量控制：50/100/200/500/全部 + "仅已连接"复选框
- 渲染时过滤无关系节点

### jieba 提取升级
- 替换为 `jieba.analyse.extract_tags()` + 150+ 停用词
- 过滤 Markdown 符号/URL/纯数字

### 审核清理面板
- 标签页：名称长度/关系状态/类型筛选 + 表格列表
- 批量删除：API 接收 ids 参数 + 级联删除关联关系
- 全选/取消全选

### 图搜索标签页
- `POST /api/graph` 路由：向量召回 + 1-hop
- ECharts 子图：种子节点红色 + 点击钻取
- 右侧关联事实列表

## 🐛 遇到的问题
- JS `Uncaught SyntaxError`：Python 三引号中转义 → 事件代理替代 inline onclick ✅
- 图搜索节点不在实体库：chunks 表残留 337 条旧索引 → DEL chunks + 重建 ✅
- 低质量实体：单字/超长文本 → 删除 119 个（≤3字 | >80字）✅
- tooltip `_content.name` 不存在 → `_raw.name` ✅

## 📦 产出物
- `scripts/wiki_manager_web.py` — 审核清理 + 图搜索 ~500 行
- `docs/plans/20260728-cleanup-review-panel.md` — 清理面板计划
- `docs/plans/20260728-graph-search.md` — 图搜索完成记录

## ➡️ 下一步
- 关系提取质量优化（LLM prompt 调优）
- 图搜索 edges=0 需改善
- 可选：图搜索节点染色依据 type 分类

---

# 阶段复盘：Phase 6 - 文档更新（原）
- 时间：2026-07-26 02:00
- 状态：✅ 完成

## ✅ 做得好的点
- 全面梳理了所有需要更新的文档，确保信息一致性
- 使用 edit 工具精确替换，避免破坏已有内容
- 创建了独立的 Phase 6 总结文档，便于追溯
- 更新了根目录 README.md 和 docs/ 下所有相关文档

## 📝 实现内容

### 1. 根目录 README.md
- 更新存储架构说明：libsql + FAISS LSH + ChromaDB（回退）
- 更新目录结构：新增 libsql 相关文件
- 更新系统状态：29,000+ chunks，LSH ~0.1ms
- 添加 2026-07-26 更新日志

### 2. docs/technical/ARCHITECTURE_STATUS.md
- 新增存储层架构图
- 更新已实现模块表（含 libsql 向量存储、Wiki DB、迁移脚本）
- 更新验收状态（添加 libsql 相关项）

### 3. docs/technical/LIBSQL_MIGRATION_GUIDE.md
- 状态从"待实施"改为"已完成"
- 新增当前状态表格
- 保留迁移前准备步骤

### 4. docs/technical/LIBSQL_ROLLBACK_PLAN.md
- 更新日期和状态

### 5. docs/technical/RAG_UPGRADE_PLAN.md
- 更新两阶段目标（LSH + libsql）
- 更新文档更新章节

### 6. docs/project/PROJECT_SUMMARY.md
- 新增 libsql 统一存储章节
- 更新章节编号和项目结构
- 更新验收标准

### 7. docs/project/PROJECT_INDEX.md
- 更新核心模块列表和存储目录
- 更新文档导航（含 libsql 文档链接）
- 更新核心功能列表（13 项）

### 8. docs/project/README.md
- 添加警告说明区分独立项目

### 9. 新建文档
- `docs/technical/PHASE6_DOCUMENT_UPDATE_SUMMARY.md` — Phase 6 专项总结

## 🐛 遇到的问题
无重大问题。所有编辑均一次成功。

## 📦 产出物
- `README.md` — 更新
- `docs/technical/ARCHITECTURE_STATUS.md` — 更新
- `docs/technical/LIBSQL_MIGRATION_GUIDE.md` — 更新
- `docs/technical/LIBSQL_ROLLBACK_PLAN.md` — 更新
- `docs/technical/RAG_UPGRADE_PLAN.md` — 更新
- `docs/project/PROJECT_SUMMARY.md` — 更新
- `docs/project/PROJECT_INDEX.md` — 更新
- `docs/project/README.md` — 更新（添加项目区分说明）
- `docs/technical/PHASE6_DOCUMENT_UPDATE_SUMMARY.md` — 新建

## ➡️ 下一步
- Phase 6 文档更新已完成
- 如果 libsql 迁移的代码实现（Phase 1-5）也已完成，可进行整体集成测试
- 考虑清理旧的 ChromaDB/SQLite 数据（迁移验证通过后）
