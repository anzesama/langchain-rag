# LLM 精炼状态显示功能文档

## 更新时间
2026-08-02

## 功能概述
在 Web 界面的 LLM 面板中显示每个文档的精炼状态（已精炼/未精炼/关系数量），并在精炼后自动刷新状态。

## 功能特性

### 1. 状态分类
后端根据实体和关系数量，为每个文档分配状态：

| Status | 实体数 | 关系数 | 图标 | 说明 |
|--------|--------|--------|------|------|
| `no_entities` | 0 | 0 | ⚪ | 无实体 |
| `refined_with_rel` | > 0 | > 0 | 🟢 | 已精炼（有关系） |
| `refined_empty` | > 0 | 0 | 🟡 | 已精炼（无关系） |
| 其他 | > 0 | 0 | 🔴 | 未精炼 |

### 2. 下拉列表显示
- 每个选项前显示颜色图标和状态文字
- 示例：
  - 🟢 `README.md (已精炼 (18关系))`
  - 🟡 `index.md (已精炼 (无关系))`
  - 🔴 `未精炼文档.md (未精炼)`
  - ⚪ `空文档.md (无实体)`

### 3. 统计信息
- 显示精炼覆盖情况：`精炼覆盖: 3 / 16 文档`
- 自动创建统计显示区域（如果不存在）
- 每次精炼应用后自动刷新统计

## 实现细节

### 后端修改

**文件**: `scripts/wiki_manager_web.py`
**函数**: `list_sources()` (第 3381 行)

**修改内容**:
1. 查询关系数量：`SELECT COUNT(*) FROM relationships WHERE source_chapter = ? OR source_chapter = ?`
2. 根据实体和关系数量判断状态
3. 返回包含 `status` 字段的源列表

```python
# 判断状态
if ec == 0:
    status = 'no_entities'
elif rc > 0:
    status = 'refined_with_rel'
else:
    status = 'refined_empty'  # 有实体但无关系
```

### 前端修改

**文件**: `scripts/wiki_manager_web.py`
**函数**: `loadSources()` (第 2347 行)

**修改内容**:
1. 根据状态显示图标和文字
2. 统计已精炼文档数量
3. 更新统计显示区域

```javascript
if (s.status === 'refined_with_rel') {
    refined++;
    icon = '🟢';
    statusText = `已精炼 (${s.relations}关系)`;
} else if (s.status === 'refined_empty') {
    icon = '🟡';
    statusText = '已精炼 (无关系)';
} else if (s.status === 'no_entities') {
    icon = '⚪';
    statusText = '无实体';
} else {
    icon = '🔴';
    statusText = '未精炼';
}
```

**函数**: `applyChanges()` (第 2559 行)

**修改内容**:
- 在成功应用后调用 `loadSources()` 刷新状态

```javascript
if (data.success) {
    showToast(`应用完成: ...`, 'success');
    pendingChanges = null;
    loadStats();
    loadSources();  // 刷新精炼状态
    document.getElementById('llm-results').innerHTML = '<div class="empty-state">变更已应用</div>';
}
```

**HTML**: LLM 面板 (第 715 行后)

**修改内容**:
- 添加统计显示区域 `<div id="refine-stats">`

```html
<!-- 精炼状态统计 -->
<div id="refine-stats" style="margin-bottom: 10px; font-size: 13px; color: #666;"></div>
```

## API 响应示例

```json
{
  "success": true,
  "sources": [
    {
      "name": "README.md",
      "entities": 13,
      "chunks": 15,
      "relations": 18,
      "status": "refined_with_rel"
    },
    {
      "name": "index.md",
      "entities": 15,
      "chunks": 20,
      "relations": 7,
      "status": "refined_with_rel"
    },
    {
      "name": "未精炼文档.md",
      "entities": 25,
      "chunks": 30,
      "relations": 0,
      "status": "refined_empty"
    }
  ]
}
```

## 使用方式

### Web 界面操作
1. 打开 `http://127.0.0.1:5000`
2. 切换到"LLM 精筛与关系提取"面板
3. 查看下拉列表中的状态图标和统计信息
4. 执行精炼操作
5. 应用更改后，状态和统计自动刷新

### CLI 脚本
```bash
python scripts/import.py documents/ --steps 2,3,4
```

## 技术特点

- ✅ 无需修改数据库结构
- ✅ 利用现有 `entities` 和 `relationships` 表
- ✅ 自动创建统计显示区域
- ✅ 实时刷新状态
- ✅ 状态分类清晰

## 已知限制

1. **状态定义**：`refined_empty` 既表示"未精炼"也表示"精炼过但无关系"
   - 如需更精确区分，可后续添加 `refine_log` 表

2. **图标显示**：依赖浏览器支持 emoji

3. **统计刷新**：只在应用更改后刷新，预览时不会刷新

## 后续改进

1. 添加"从未精炼"和"精炼过但无关系"的区分
2. 支持自定义状态图标
3. 添加状态筛选功能
4. 显示精炼历史记录

## 相关文件

- `scripts/wiki_manager_web.py` - Web 后端（已修改）
- `rag_core/unified_importer.py` - 导入流程
- `scripts/batch_extract_relations.py` - 批量关系抽取

## 版本历史

- 2026-08-02: 初始功能完成
