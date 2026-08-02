# 批量关系抽取集成文档

## 集成完成时间
2026-08-02

## 功能概述
在 `import.py` 的 Step 2+3+4 阶段自动集成批量关系抽取功能，实现新文档导入时自动补全关系。

## 集成位置
- **文件**: `rag_core/unified_importer.py`
- **方法**: `_import_entities_and_relations()`
- **集成点**: 在写入实体后，自动调用批量关系抽取

## 集成流程

### Step 2+3+4 执行流程
```
1. jieba 实体提取
   ↓
2. 写入实体到 WikiDB
   ↓
3. 【新增】批量关系抽取（基于新导入的 chunks）
   ↓
4. 写入关系到 WikiDB
```

### 关系抽取逻辑
```python
# 获取刚导入的 chunks
chunks = self.vs.get_chunks_by_source(source)

if chunks and len(chunks) > 0:
    # 调用批量关系抽取
    relations_added = batch_extract_relations(
        chunks=chunks,
        source=source,
        model_name='agnes-2.0-flash'
    )
```

## 依赖组件

### 1. batch_extract_relations.py
**位置**: `scripts/batch_extract_relations.py`

**函数签名**:
```python
def batch_extract_relations(
    chunks: List[Dict],
    source: str,
    model_name: str = 'agnes-2.0-flash'
) -> int
```

**功能**:
- 从 chunks 列表中提取实体间关系
- 使用 AGNES API 进行 LLM 关系提取
- 自动创建不存在的实体
- 导入关系到 WikiDB

**参数说明**:
- `chunks`: chunks 列表，格式为 `[{'page_content': t, 'chunk_text': t}, ...]`
- `source`: chunks.source（文档路径）
- `model_name`: 模型名称，默认 'agnes-2.0-flash'

**返回值**:
- 导入的关系数量

### 2. LLMRefiner
**位置**: `rag_core/llm_refiner.py`

**功能**:
- 使用 LLM 提取实体间关系
- 支持多领域（machine-learning, deep-learning 等）

## 使用方式

### 方式 1: 使用 import.py（自动抽取）
```bash
# 导入文档时自动抽取关系（Step 2+3+4）
python scripts/import.py documents/

# 只导入实体（Step 1+2）
python scripts/import.py documents/ --steps 1,2

# 只导入实体和关系（Step 2+3+4）
python scripts/import.py documents/ --steps 2,3,4
```

### 方式 2: 手动调用批量抽取
```bash
# 对单个文档抽取关系
python scripts/batch_extract_relations.py --source README.md

# 对所有文档抽取关系
python scripts/batch_extract_relations.py --all

# 限制处理数量
python scripts/batch_extract_relations.py --all --limit 5
```

### 方式 3: 在代码中调用
```python
from scripts.batch_extract_relations import batch_extract_relations

# 从 chunks 抽取关系
relations_added = batch_extract_relations(
    chunks=chunks_list,
    source='README.md',
    model_name='agnes-2.0-flash'
)
print(f"Added {relations_added} relations")
```

## 技术细节

### 关系提取 Prompt
- 基于 `_build_relation_prompt()` 函数
- Few-shot 示例 + 严格类型限制
- 支持的关系类型：适用、使用、依赖、优化、组成、关联、传递等

### 错误处理
- 如果 chunks 为空，跳过关系抽取
- 如果 LLM 返回空响应，记录警告但不中断导入
- 如果实体不存在，自动创建

### 性能优化
- 关系抽取在实体写入后异步执行
- 使用 AGNES API（快速、免费）
- 支持批量处理多个文档

## 测试

### 集成测试
```bash
python test_relation_simple.py
```

**预期输出**:
```
============================================================
Testing Relation Extraction Integration
============================================================
[OK] _import_entities_and_relations method exists
[OK] WikiDB initialized internally

============================================================
Integration Test Complete!
============================================================
```

### 手动测试
1. 导入新文档
2. 检查控制台日志，确认看到：
   ```
   [INFO]   开始批量关系抽取: X chunks from Y
   [INFO]   提取到 Z 条关系
   [INFO]   关系抽取完成: Z 条关系
   ```
3. 在 Web UI 中查看知识图谱，确认新关系已显示

## 已知限制

1. **LLM 返回空响应**: 部分文档可能没有明确的关系，导致抽取失败
2. **孤立实体**: 没有关系的实体不会出现在"仅已连接"模式下
3. **API 限制**: AGNES API 可能有请求频率限制

## 后续改进

1. 在 Web UI 中显示关系抽取进度
2. 支持自定义关系类型
3. 添加关系抽取结果预览功能
4. 支持增量更新（只抽取新增 chunks 的关系）

## 相关文件

- `rag_core/unified_importer.py` - 导入流程集成
- `scripts/batch_extract_relations.py` - 批量关系抽取脚本
- `rag_core/llm_refiner.py` - LLM 关系提取
- `rag_config.py` - API 配置

## 版本历史

- 2026-08-02: 初始集成完成
