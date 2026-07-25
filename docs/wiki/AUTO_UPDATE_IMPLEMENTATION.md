# Wiki 层自动更新功能实现

## 📅 实现日期
2026-07-09

## 🎯 实现目标

在添加文档时自动执行完整方案：
1. ✅ 更新 ChromaDB + LSH（RAG 层）
2. ✅ 更新 Wiki 数据库（Wiki 层）
3. ✅ 重新生成知识图谱 HTML（可视化层）

---

## 🔧 修改内容

### 1. 修改文件
**文件**: `rag_core/knowledge_base.py`

**方法**: `_add_novel_document()`

**修改位置**: 第 117-176 行

**新增代码**:
```python
# 4. 更新 Wiki 层（完整方案）
try:
    from rag_core.wiki_updater import WikiUpdater
    from scripts import wiki_graph_web

    # 获取文档内容用于 Wiki 扫描
    full_text = ""
    for chunk in loader.get_progress()['chunks']:
        full_text += chunk.page_content + "\n"

    # 扫描并添加实体/关系
    updater = WikiUpdater()
    wiki_stats = updater.batch_add_from_text(
        text=full_text,
        source_chapter=filepath,
        min_confidence=2
    )

    if wiki_stats["entities_added"] > 0 or wiki_stats["relations_added"] > 0:
        logger.info(f"[OK] Wiki 层已更新: {wiki_stats['entities_added']} 个实体, {wiki_stats['relations_added']} 个关系")

        # 重新生成知识图谱 HTML
        wiki_graph_web.generate_html()
        logger.info(f"[OK] 知识图谱已重新生成")
    else:
        logger.debug(f"[INFO] Wiki 层无新实体/关系: {filepath}")

except Exception as e:
    logger.warning(f"[WARNING] Wiki 层更新失败: {e}")
    # 不影响主流程，继续执行
```

---

## 📊 执行流程

### 完整流程图

```
用户执行: python rag_cli.py add novel.txt
    ↓
cmd_add_novel()
    ↓
_add_novel_document()
    ↓
┌─────────────────────────────────────┐
│ 1. ResumeLoader 加载文档            │
│    - 分块                           │
│    - 生成嵌入向量                   │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. 同步双写到 ChromaDB + LSH       │
│    - 写入向量                       │
│    - 保存索引                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. 更新 Wiki 层（新增）            │
│    - WikiUpdater 扫描文本           │
│    - 提取实体                       │
│    - 提取关系                       │
│    - 批量添加到数据库               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 4. 重新生成知识图谱 HTML（新增）   │
│    - 读取 Wiki 数据库               │
│    - 生成 JSON 数据                 │
│    - 写入 HTML 文件                 │
└─────────────────────────────────────┘
    ↓
完成
```

---

## 🧪 测试

### 测试方法

```bash
# 方法 1: 使用测试脚本
python tests/test_complete_solution.py

# 方法 2: 直接添加文档
python rag_cli.py add documents/novel_chapters/chapter_1158.txt
```

### 预期结果

1. **ChromaDB + LSH 更新**：✅ 正常
2. **Wiki 数据库更新**：✅ 提取并添加实体/关系
3. **知识图谱 HTML 更新**：✅ 重新生成

### 查看结果

```bash
# 查看 Wiki 数据库统计
python scripts/wiki_cli.py stats

# 查看知识图谱
start scripts/wiki_graph.html
```

---

## 📝 日志输出示例

```
[INFO] 小说文档已入库: chapter_1158.txt (50 个块)
[INFO] 扫描到 3 个新实体候选
[INFO] 批准实体: 龙公 (类型: 人物)
[OK] Wiki 层已更新: 1 个实体, 2 个关系
[OK] 知识图谱已重新生成
```

---

## ⚠️ 注意事项

### 1. 性能影响

- Wiki 层更新会增加 2-5 秒的延迟
- 知识图谱生成会增加 1-2 秒的延迟
- 总体延迟增加约 3-7 秒

### 2. 错误处理

- Wiki 层更新失败不会影响主流程
- 错误会被记录为 WARNING，但不会中断添加操作

### 3. 置信度阈值

- 默认 `min_confidence=2`（匹配模式数量 ≥ 2）
- 可以根据需要调整

---

## 🔄 后续优化

### 可能的优化方向

1. **异步更新**：将 Wiki 层更新放到后台线程
2. **增量更新**：只扫描新文档的实体/关系
3. **缓存机制**：避免重复扫描相同文本
4. **批量处理**：添加多个文档时合并扫描

---

## ✅ 实现总结

| 功能 | 状态 |
|------|------|
| ChromaDB + LSH 自动更新 | ✅ 已实现（原有功能） |
| Wiki 数据库自动更新 | ✅ 新增 |
| 知识图谱 HTML 自动生成 | ✅ 新增 |
| 错误处理 | ✅ 已实现 |
| 日志记录 | ✅ 已实现 |

---

**实现状态**: ✅ 完成
**测试状态**: ⏳ 待测试
**文档状态**: ✅ 完成
