# 知识图谱详情面板自动关闭功能文档

## 更新时间
2026-08-02

## 功能概述
修复知识图谱详情面板无法自动关闭的问题，实现点击空白区域、切换面板、删除实体后自动关闭详情面板。

## 问题根因

1. **点击图谱空白区域时**，没有事件来关闭详情面板
2. **切换面板时**，没有重置详情面板状态
3. **删除实体或编辑后**，有时会残留显示

## 解决方案

### 1. 添加 `closeDetailPanel()` 函数

**文件**: `scripts/wiki_manager_web.py`
**位置**: `getEntityRelations()` 函数之后

**代码**:
```javascript
function closeDetailPanel() {
    document.getElementById('detail-panel').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'block';
    selectedEntity = null;
}
```

### 2. 修改 `onmouseup` 事件

**文件**: `scripts/wiki_manager_web.py`
**位置**: `loadGraph` 函数中的 `graphCanvas.onmouseup`

**修改前**:
```javascript
graphCanvas.onmouseup = function(e) {
    if (dragIdx >= 0) {
        var p = graphPositions[dragIdx];
        var dx = p.x - (e.offsetX || p.x), dy = p.y - (e.offsetY || p.y);
        if (Math.abs(dx) < 3 && Math.abs(dy) < 3) showEntityDetail(p.raw);
    }
    dragIdx = -1;
    graphCanvas.style.cursor = graphHoveredIdx >= 0 ? 'pointer' : 'grab';
};
```

**修改后**:
```javascript
graphCanvas.onmouseup = function(e) {
    if (dragIdx >= 0) {
        var p = graphPositions[dragIdx];
        var dx = p.x - (e.offsetX || p.x), dy = p.y - (e.offsetY || p.y);
        if (Math.abs(dx) < 3 && Math.abs(dy) < 3) showEntityDetail(p.raw);
        dragIdx = -1;
        graphCanvas.style.cursor = graphHoveredIdx >= 0 ? 'pointer' : 'grab';
    } else {
        // 点击空白区域 → 关闭详情面板
        closeDetailPanel();
    }
};
```

### 3. 修改 `showPanel()` 函数

**文件**: `scripts/wiki_manager_web.py`
**位置**: `showPanel` 函数开头

**修改内容**:
```javascript
function showPanel(panelName, evt) {
    // 切换面板时关闭详情面板
    closeDetailPanel();
    console.log('[showPanel]', panelName);
    // ... 继续执行面板切换 ...
}
```

### 4. 修改 `deleteSelectedEntity()` 函数

**文件**: `scripts/wiki_manager_web.py`
**位置**: `deleteSelectedEntity` 函数

**修改前**:
```javascript
if (data.success) {
    showToast('实体已删除', 'success');
    selectedEntity = null;
    document.getElementById('detail-panel').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'block';
    await loadEntities();
    await loadRelations();
    loadGraph();
    loadStats();
}
```

**修改后**:
```javascript
if (data.success) {
    showToast('实体已删除', 'success');
    closeDetailPanel();  // 关闭详情面板
    await loadEntities();
    await loadRelations();
    loadGraph();
    loadStats();
}
```

## 功能验证

### 验证清单

- ✅ 点击节点 → 详情面板显示
- ✅ 点击图谱空白区域 → 详情面板隐藏
- ✅ 切换到其他面板 → 详情面板隐藏
- ✅ 删除实体后 → 详情面板隐藏
- ✅ 切换面板时 → 详情面板隐藏

## 技术特点

- ✅ 使用统一的 `closeDetailPanel()` 函数
- ✅ 避免重复代码
- ✅ 提升用户体验
- ✅ 状态管理清晰

## 已知限制

1. **连线过程中**：如果连线过程中打开了详情面板，取消连线时不会自动关闭（可选改进）

## 后续改进

1. 添加"取消连线时关闭详情面板"功能
2. 添加"点击连线关闭详情面板"功能
3. 添加"双击节点关闭详情面板"功能

## 相关文件

- `scripts/wiki_manager_web.py` - Web 后端（已修改）
- `scripts/batch_extract_relations.py` - 批量关系抽取

## 版本历史

- 2026-08-02: 初始功能完成
