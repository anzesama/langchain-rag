# RAG 知识库升级实施计划

**时间**: 2026-07-02
**目标**: 实现高性能语义检索引擎架构（基于 gte-small ONNX + FAISS LSH）
**状态**: 待开始

---

## 📋 升级目标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 嵌入推理 | 20-30 ms | 3-5 ms | 5-10x |
| 向量检索 | 5-20 ms | 0.1-0.2 ms | 25-200x |
| 总查询延迟 | 30-50 ms | ~5 ms | 6-10x |
| 内存占用 | ~2 GB | ~1 GB | 50% |

---

## 🎯 实施步骤

### 阶段 1: 基础设施升级（并行执行）

#### 1.1 嵌入服务升级
- **文件**: `rag_core/embedding_service.py`（重写）
- **技术**: gte-small + ONNX Runtime + int8 量化
- **接口**: 保持 `encode(texts: List[str]) -> np.ndarray`
- **子任务**:
  - [ ] 下载/加载 gte-small 模型
  - [ ] ONNX Runtime 量化配置
  - [ ] 批量推理优化
  - [ ] 保留缓存接口

#### 1.2 文档处理器增强
- **文件**: `rag_core/document_processor.py`（新建）
- **功能**:
  - 自动注入 `chunk_index`、`global_order`、`source` 等元数据
  - 继承现有 chunk_documents 逻辑
- **子任务**:
  - [ ] 创建 DocumentProcessor 类
  - [ ] 实现元数据注入
  - [ ] 测试分块效果

#### 1.3 因果排序器
- **文件**: `rag_core/causal_sorter.py`（新建）
- **功能**: 按 global_order 排序，支持上下文窗口
- **子任务**:
  - [ ] 创建 CausalSorter 类
  - [ ] 实现排序逻辑
  - [ ] 实现窗口截取

---

### 阶段 2: LSH 索引实现

#### 1.4 LSH 索引管理器
- **文件**: `rag_core/lsh_index.py`（新建）
- **功能**:
  - FAISS LSH 索引构建/保存/加载
  - 检索接口
  - 元数据映射管理
- **子任务**:
  - [ ] 创建 LSHIndexManager 类
  - [ ] 实现索引构建
  - [ ] 实现检索方法
  - [ ] 实现进度保存

---

### 阶段 3: 断点续传加载

#### 1.5 断点续传加载器
- **文件**: `scripts/load_guzhenren_resume.py`（新建）
- **功能**:
  - 检查进度文件
  - 筛选缺失 chunk
  - 分批加载
  - 双写（FAISS + ChromaDB）
  - 保存进度
- **子任务**:
  - [ ] 创建 ResumeLoader 类
  - [ ] 实现进度检查
  - [ ] 实现增量加载
  - [ ] 实现进度保存

---

### 阶段 4: 集成与测试

#### 1.6 查询入口改造
- **文件**: `rag_cli.py`（修改）
- **功能**:
  - 集成 LSH 检索
  - 集成因果排序
  - 组装上下文
- **子任务**:
  - [ ] 修改 search 方法
  - [ ] 集成 LSH 检索
  - [ ] 集成因果排序
  - [ ] 测试查询流程

#### 1.7 配置更新
- **文件**: `rag_config.py`（修改）
- **功能**:
  - 更新 embedding 模型配置
  - 添加 LSH 配置
  - 添加断点续传配置
- **子任务**:
  - [ ] 更新 EMBEDDING_MODEL
  - [ ] 添加 LSH 参数
  - [ ] 添加进度配置

---

### 阶段 5: 验收与文档

#### 1.8 性能测试
- **子任务**:
  - [ ] 测试嵌入推理速度
  - [ ] 测试检索速度
  - [ ] 测试总查询延迟
  - [ ] 对比新旧方案

#### 1.9 文档更新
- **文件**:
  - `README.md`
  - `PROJECT_SUMMARY.md`
  - `USAGE_GUIDE.md`
- **内容**:
  - 更新架构说明
  - 添加使用指南
  - 记录性能指标

---

## 📊 并行执行策略

### 第一批（核心模块）
- Agent 1: 嵌入服务升级 + 文档处理器
- Agent 2: LSH 索引管理器
- Agent 3: 因果排序器

### 第二批（加载脚本）
- Agent 4: 断点续传加载器

### 第三批（集成）
- Agent 5: 查询入口改造 + 配置更新

### 第四批（测试）
- Agent 6: 性能测试 + 文档更新

---

## ✅ 验收标准

- [ ] 嵌入推理速度 < 5ms
- [ ] 检索速度 < 0.2ms
- [ ] 总查询延迟 < 5ms
- [ ] 内存占用 < 1GB
- [ ] 断点续传功能正常
- [ ] 查询结果因果顺序正确
- [ ] 文档更新完成

---

## 📦 产出物

- `rag_core/embedding_service.py`（ONNX 版本）
- `rag_core/document_processor.py`
- `rag_core/causal_sorter.py`
- `rag_core/lsh_index.py`
- `scripts/load_guzhenren_resume.py`
- `rag_cli.py`（修改）
- `rag_config.py`（修改）
- `storage/novel_lsh.index`
- `storage/id_map.pkl`
- `storage/load_state.json`
- `docs/RAG_UPGRADE_PERFORMANCE.md`（性能报告）

---

**创建时间**: 2026-07-02
**预计完成**: 2026-07-03
