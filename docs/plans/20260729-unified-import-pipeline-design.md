# 统一文档导入流水线 — 设计方案

- 时间：2026-07-29
- 分支：`feature/llm-extraction`
- 状态：设计完成

---

## 问题

当前文档导入是分段的，没有一个入口能把 chunks（向量）、entities（实体）、relationships（关系）三步串起来：

- `VectorStoreManager.add_documents()` → 只写 chunks 表
- jieba TF-IDF → 只在 web 后端手动触发
- 关系推导 → 要手动调 wiki_updater / llm_extractor

每次导入新文档需手工跑三步，LSH 索引也不同步。

## 设计方案

新增命令行工具 `scripts/import.py`，一条命令完成全链路导入。

### 用法

```bash
# 导入目录（增量）
python scripts/import.py documents/AAAMLP-CN/

# 导入单文件
python scripts/import.py documents/notes.md

# 全量覆盖
python scripts/import.py documents/AAAMLP-CN/ --overwrite
```

### 处理流程

```
CLI → parse args → 扫描源文件(md/txt) → Step 1-4
```

| Step | 做什么 | 对接模块 |
|------|-------|---------|
| 1 | 分块 + embedding → chunks 表 + LSH 索引同步 | VectorStoreManager + LSHIndexManager |
| 2 | jieba TF-IDF 提取实体 → entities 表 | jieba.analyse.extract_tags + wiki_updater |
| 3 | 领域词表规则推导关系 → relationships 表 | wiki_updater._build_relations() |
| 4 | LLM 对低置信度关系精炼 | llm_extractor (可选) |

### 增量 vs 覆盖

- **默认增量**：检查 chunks 表已有 source 指纹，跳过已处理文件
- **--overwrite**：删除该 source 下已写入的 chunks/entities/relationships，全量重建

增量判断：在 chunks 表中按 source 字段查已存在记录数 > 0 → 跳过。

### 关键接口

```python
# scripts/import.py 核心入口

class UnifiedImporter:
    def __init__(self):
        self.vs = VectorStoreManager()      # libsql chunks 表
        self.lsh = LSHIndexManager()        # LSH 索引（在 KnowledgeBase 里管理）
        self.entity_extractor = ...         # jieba TF-IDF
        self.relation_builder = ...         # wiki_updater
        self.llm = ...                      # llm_extractor (可选)

    def import_path(self, path, overwrite=False):
        # Step 1: chunks + LSH
        # Step 2: entities extraction
        # Step 3: relations building
        # Step 4: LLM refine (optional, conditional)

    def import_directory(self, dir_path, overwrite=False):
        # 扫描文件 → 逐个 import_path
```

### 步态控制

- `--steps 1,2,3,4`：指定只运行哪些步骤（默认全部）
- `--no-llm`：跳过 Step 4

### 日志与进度

- 实时输出进度行：`[1/630] embedding AAAMLP-CN/交叉检验.md ... done`
- 完成统计：`Done: 630 chunks, 120 entities, 85 relations`

---

## 与现有模块关系

- `VectorStoreManager`：已经有 add_documents，直接委托
- LSH：在 `knowledge_base.py` 方法里调用，需要抽出来供 import.py 调用
- `wiki_updater`：目前是 web API 触发的独立模块，需要把核心提取逻辑暴露为 import-able 函数
- `llm_extractor`：已经独立可用，低置信度判断标准后期再调

## 错误处理

- 单文件失败不影响其他文件继续处理
- 最终输出失败清单：`3/20 files skipped (no content)`

## 覆盖 Legend

| 入口 | 方式 | 适用场景 |
|-----|------|---------|
| A. 命令行 | `python scripts/import.py <path>` | 人工批量导入 |
| B. Web 页面 | 后续加 "导入新文档" 按钮 | 非技术人员 |
| C. 自动监听 | 后续加 auto_importer 全流程 | 持续集成 |