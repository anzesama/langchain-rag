# Web 批量导入关系增强文档

## 更新时间
2026-08-02

## 改进概述
为 Web 界面的批量导入关系功能添加"自动创建缺失实体"逻辑，使其与 CLI 脚本保持一致。

## 问题分析

### 修复前的问题
- **Web 按钮**：调用 `/api/relations/batch-import` → 如果 LLM 返回的实体不存在，导入会失败
- **CLI 脚本**：调用 `batch_extract_relations.py` → 如果实体不存在，会**自动创建**

### 根本原因
Web 后端在导入关系前没有检查实体是否存在，直接调用 `add_relationship`，导致外键约束失败。

## 解决方案

### 修改位置
- **文件**: `scripts/wiki_manager_web.py`
- **函数**: `batch_import_relations()` (第 3157 行)

### 修改内容
在导入关系前添加实体自动创建逻辑：

```python
for rel in relations:
    try:
        src = rel.get('source', '').strip()
        tgt = rel.get('target', '').strip()
        rtype = rel.get('type', '关联')
        if src and tgt:
            # 自动创建缺失的实体
            for name in [src, tgt]:
                existing = wiki_db.get_entity_id(name)
                if not existing:
                    wiki_db.add_entity(
                        name=name,
                        entity_type='未知',
                        source_chapter=rel.get('source_chapter') or 'llm_extracted',
                        properties={}
                    )
                    logger.info(f"自动创建实体: {name}")
            # 导入关系
            wiki_db.add_relationship(src, tgt, rtype, source_chapter=rel.get('source_chapter'))
            imported += 1
```

## 功能对比

| 功能 | Web 按钮（修复前） | Web 按钮（修复后） | CLI 脚本 |
|------|-------------------|-------------------|----------|
| **关系抽取** | ✅ 使用 `LLMRefiner` | ✅ 使用 `LLMRefiner` | ✅ 使用 `LLMRefiner` |
| **实体自动创建** | ❌ 失败 | ✅ 自动创建 | ✅ 自动创建 |
| **预览确认** | ✅ 有 | ✅ 有 | ❌ 无 |
| **覆盖方式** | 手动选一个文档 | 手动选一个文档 | 批量自动遍历 |

## 使用方式

### Web 界面操作
1. 打开 `http://127.0.0.1:5000`
2. 切换到"图谱"面板
3. 选择一个文档
4. 点击"提取关系"按钮
5. 预览提取结果
6. 点击"应用更改"

### CLI 脚本操作
```bash
python scripts/batch_extract_relations.py --all
```

## 技术细节

### 自动创建逻辑
1. 遍历关系中的每个实体（`source` 和 `target`）
2. 检查实体是否存在：`wiki_db.get_entity_id(name)`
3. 如果不存在，自动创建：
   - 名称：`name`
   - 类型：`未知`
   - 来源：`source_chapter` 或 `llm_extracted`
   - 属性：`{}`
4. 然后导入关系

### 错误处理
- 如果创建实体失败，记录警告但继续导入其他关系
- 如果导入关系失败，记录警告但继续导入其他关系

## 测试验证

### API 测试
```bash
curl http://127.0.0.1:5000/api/stats
```

**预期输出**:
```json
{
  "pending_entities": 136,
  "pending_relations": 77,
  "total_entities": 136,
  "total_relations": 77
}
```

### 功能测试
1. 在 Web 界面选择一个文档
2. 点击"提取关系"
3. 预览并应用
4. 检查知识图谱，确认关系已显示

## 已知限制

1. **预览确认**：Web 按钮需要用户手动确认，CLI 脚本直接入库
2. **批量处理**：Web 按钮一次只能处理一个文档，CLI 脚本可以批量处理所有文档
3. **实体类型**：自动创建的实体类型为"未知"

## 后续改进

1. 支持批量提取和预览（类似 CLI 脚本）
2. 支持自定义实体类型
3. 添加关系抽取进度条
4. 支持增量更新（只抽取新增 chunks 的关系）

## 相关文件

- `scripts/wiki_manager_web.py` - Web 后端（已修改）
- `scripts/batch_extract_relations.py` - CLI 脚本
- `rag_core/llm_refiner.py` - LLM 关系提取

## 版本历史

- 2026-08-02: 初始增强完成
