# 变更日志

## 2026-08-02

### 新增功能
- ✅ 知识图谱 Canvas 力导向布局（基于连接数的节点大小和位置）
- ✅ 知识图谱详情面板自动关闭（点击空白区域/切换面板/删除实体）
- ✅ 批量关系抽取集成到 `import.py`（Step 2+3+4 自动抽取关系）
- ✅ 批量抽取脚本支持 chunks 参数
- ✅ Web 批量导入关系增强（自动创建缺失实体）
- ✅ LLM 精炼状态显示（已精炼/未精炼/无实体，带图标和统计）
- ✅ 关系预览和手动导入功能

### 修复问题
- ✅ 修复知识图谱渲染问题（`Cannot read properties of undefined (reading 'x')`）
- ✅ 修复节点访问错误（检查节点存在性）
- ✅ 修复 `graphPositions` 数组未创建节点的问题
- ✅ 修复 Web 批量导入关系失败（实体不存在时）
- ✅ 修复详情面板不自动关闭的问题

### 文档更新
- ✅ 创建 `RELATION_EXTRACTION_INTEGRATION.md`
- ✅ 创建 `WEB_RELATION_IMPORT_ENHANCEMENT.md`
- ✅ 创建 `LLM_REFINE_STATUS_DISPLAY.md`
- ✅ 创建 `GRAPH_DETAIL_PANEL_AUTO_CLOSE.md`
- ✅ 创建 `20260802-update-summary.md`
- ✅ 更新 `README.md`（核心功能、更新日志、项目状态）
- ✅ 更新 `ARCHITECTURE_STATUS.md`（已实现模块、已知问题）

### 技术细节
- **力导布局**: 节点大小 20-60px（基于连接数×8），初始位置居中（基于连接数差异）
- **批量抽取**: 支持 chunks 参数，自动创建实体，容错处理
- **精炼状态**: 4 种状态分类，图标显示，实时统计
- **详情面板**: 统一 `closeDetailPanel()` 函数，多处自动关闭

### 数据统计
- 实体数: 136
- 关系数: 77
- 孤立实体: 54 (39.7%)
- 有关系的实体: 82
- 来源数: 16

## 2026-07-31

### 修复问题
- ✅ 知识图谱 JS 错误（connectedChk、showConnected 重复声明）
- ✅ reloadGraphData 未定义错误

### 文档更新
- ✅ 添加 troubleshooting.md 到知识库
- ✅ AGENTS.md 优化知识库检索策略（top_k=5）
- ✅ .gitignore 忽略临时文件

## 2026-07-26

### 新增功能
- ✅ libsql 统一存储（向量 + Wiki）
- ✅ 迁移脚本（backup、migrate、rollback、verify）
- ✅ 断点续传加载器
- ✅ LSH 索引管理器

### 文档更新
- ✅ 创建 `LIBSQL_MIGRATION_GUIDE.md`
- ✅ 创建 `LIBSQL_ROLLBACK_PLAN.md`
- ✅ 创建 `20260725-libsql-migration-plan.md`

## 2026-07-05

### 重构
- ✅ 统一存储路径
- ✅ 重构核心脚本（add_documents、check_knowledge_base、import_novel_chapters）
- ✅ 所有核心脚本集成度提升至 ⭐⭐⭐⭐⭐
