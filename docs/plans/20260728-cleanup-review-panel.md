# 审核清理面板 Implementation Plan

> **REQUIRED SUB-SKILL:** Use the executing-plans skill to implement this plan task-by-task.

**Goal:** 在 wiki_manager_web.py 中新增"审核清理"标签页，支持按(实体名长度/是否有关系/类型/状态)条件过滤实体列表，支持选中批量删除。

**Architecture:** 纯 Web 端改动（wiki_manager_web.py），后端扩展现有 `/api/entities` 过滤参数 + 新增 `/api/entities/batch_delete`，前端新增标签页 HTML + 过滤控件 + 批量操作逻辑。

**Tech Stack:** Python Flask, SQLite (libsql), 原生 JavaScript (前端)

**设计决策:**
- 不做 source_method 字段（需要 ALTER TABLE + 回填 → 耗时且数据库不熟）
- 用已有维度过滤：实体名长度(<=3/4-80/>80字)、是否有关系(connected/isolated)、状态(pending)、类型
- 批量删除 API 接收 JSON 数组 `ids`
- 筛选条件放前端实时过滤，不用后端 SQL 动态拼接（简单可靠）

---

### Task 0: 后端 — `/api/entities/batch_delete` API

**场景：该 API 是新增功能，无现有测试文件覆盖**

**Files:**
- Modify: `scripts/wiki_manager_web.py`（在 `/api/entities` 路由后添加）

**Step 1: 实现 batch_delete API**

在 `/api/entities/<entity_id>/delete` 路由后面新增：

```python
@app.route('/api/entities/batch_delete', methods=['POST'])
def batch_delete_entities():
    """批量删除实体"""
    try:
        data = request.json
        entity_ids = data.get('ids', [])
        if not entity_ids:
            return jsonify({"success": False, "error": "ids 不能为空"}), 400

        conn = get_db_connection()
        try:
            # 先删除关联的关系
            for eid in entity_ids:
                conn.execute('DELETE FROM relationships WHERE source_id = ? OR target_id = ?', (eid, eid))
            # 删除实体
            placeholders = ','.join(['?'] * len(entity_ids))
            conn.execute(f'DELETE FROM entities WHERE id IN ({placeholders})', entity_ids)
            conn.commit()
            deleted = conn.total_changes
            return jsonify({"success": True, "deleted": deleted, "ids": entity_ids})
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"批量删除失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

**Step 2: 编译验证**

```bash
python -c "import py_compile; py_compile.compile('scripts/wiki_manager_web.py', doraise=True); print('OK')"
```

**Step 3: Commit**

```bash
git add scripts/wiki_manager_web.py
git commit -m "feat: 批量删除实体 API (/api/entities/batch_delete)"
```

---

### Task 2: 前端 HTML 模板 — "审核清理"标签页

**Files:**
- Modify: `scripts/wiki_manager_web.py` — HTML_TEMPLATE 字符串（导航栏 + 面板 + 样式）

**Step 1: 导航栏新增标签**

在导航栏 `nav-tabs` 中新增第四个标签按钮：

```html
<button class="nav-tab" data-panel="cleanup">审核清理</button>
```

**Step 2: 新增清洗面板 HTML**

在 `<!-- 知识库搜索面板 -->` 后面新增：

```html
<!-- 审核清理面板 -->
<div class="panel" id="panel-cleanup" style="display: none;">
    <div class="panel-header">
        <div class="panel-title">审核清理</div>
        <div style="display: flex; gap: 10px;">
            <button class="btn btn-danger" onclick="batchDeleteEntities()" id="btn-batch-delete" disabled>批量删除所选</button>
        </div>
    </div>

    <!-- 过滤条件 -->
    <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; align-items: center;">
        <label>名称长度:</label>
        <select id="filter-len" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="all">全部</option>
            <option value="short">短 (≤3字)</option>
            <option value="mid">中 (4-80字)</option>
            <option value="long">长 (>80字)</option>
        </select>

        <label>关系状态:</label>
        <select id="filter-rel" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="all">全部</option>
            <option value="connected">有连接关系</option>
            <option value="isolated">无连接关系</option>
        </select>

        <label>状态:</label>
        <select id="filter-status" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
            <option value="pending">待审核</option>
            <option value="approved">已批准</option>
            <option value="all">全部</option>
        </select>

        <label>姓名搜索:</label>
        <input type="hidden" id="filter-search" oninput="renderCleanupList()" placeholder="输入关键字..." style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px; width: 150px;">

        <span id="cleanup-stats" style="margin-left: auto; color: #666; font-size: 13px;"></span>
    </div>

    <!-- 实体列表 -->
    <div style="max-height: 600px; overflow-y: auto; border: 1px solid #eee; border-radius: 4px;">
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #fafafa; position: sticky; top: 0;">
                    <th style="padding: 10px;"><input type="checkbox" id="select-all" onchange="toggleAllClean(this)"></th>
                    <th style="padding: 10px; text-align: left;">实体名</th>
                    <th style="padding: 10px;">类型</th>
                    <th style="padding: 10px;">长度</th>
                    <th style="padding: 10px;">关系数</th>
                    <th style="padding: 10px;">状态</th>
                    <th style="padding: 10px;">操作</th>
                </tr>
            </thead>
            <tbody id="cleanup-tbody"></tbody>
        </table>
    </div>
</div>
```

**Step 3: 编译验证 + Commit**

同 Step 2。

---

### Task 3: 前端 JS — 清洗面板逻辑（数据加载、筛选、渲染、批量删除）

**Files:**
- Modify: `scripts/wiki_manager_web.py` — HTML_TEMPLATE 字符串（JavaScript 部分）

**Step 1: 全局变量**

在 `var entities = [];` 和 `var relations = [];` 下方新增：

```javascript
var cleanupSelected = new Set();  // 选中的实体 ID
```

**Step 2: 加载清洗面板数据**

新增函数 `loadCleanupData()`：

```javascript
async function loadCleanupData() {
    try {
        const resp = await fetch('/api/entities?connected_only=false&limit=5000');
        const data = await resp.json();
        // 为每个实体计算关系数
        const relCountMap = {};
        relations.forEach(r => {
            if (!relCountMap[r.source_name]) relCountMap[r.source_name] = 0;
            relCountMap[r.source_name]++;
            if (!relCountMap[r.target_name]) relCountMap[r.target_name] = 0;
            relCountMap[r.target_name]++;
        });
        data.entities.forEach(e => {
            e._relCount = relCountMap[e.name] || 0;
        });
        cleanupEntities = data.entities;
        cleanupSelected.clear();
        renderCleanupList();
    } catch(e) {
        showToast('加载清洗数据失败', 'error');
    }
}
```

**Step 3: 渲染清洗列表**

函数 `renderCleanupList()`：

```javascript
function renderCleanupList() {
    if (!cleanupEntities || !cleanupEntities.length) return;

    let filtered = [...cleanupEntities];
    var lenFilter = document.getElementById('filter-len').value;
    var relFilter = document.getElementById('filter-rel').value;
    var statusFilter = document.getElementById('filter-status').value;

    // 过滤长度
    if (lenFilter === 'short') filtered = filtered.filter(e => (e.name || '').length <= 3);
    if (lenFilter === 'mid') filtered = filtered.filter(e => (e.name || '').length > 3 && (e.name || '').length <= 80);
    if (lenFilter === 'long') filtered = filtered.filter(e => (e.name || '').length > 80);

    // 过滤关系
    if (relFilter === 'connected') filtered = filtered.filter(e => e._relCount > 0);
    if (relFilter === 'isolated') filtered = filtered.filter(e => e._relCount === 0);

    // 过滤状态
    if (statusFilter !== 'all') filtered = filtered.filter(e => e.status === statusFilter);

    document.getElementById('cleanup-stats').textContent = '匹配 ' + filtered.length + ' / ' + cleanupEntities.length + ' 个实体';

    // 渲染表格
    var tbode = '';
    filtered.forEach(eystem => {
        var checked = cleanupSelected.has(e.id) ? 'checked' : '';
        var nameDisp = e.name || '（空）';
        if (nameDisp.length > 60) nameDisp = nameDisp.substring(0, 60) + '...';
        tbode += '<tr>';
        tbode += '<td style="padding: 4px; text-align: center;"><input type="checkbox" value="' + e.id + '" ' + checked + ' onchange="toggleCleanEntity(this)"></td>';
        tbode += '<td style="padding: 4px;" title="' + (e.name || '').replace(/"/g,'&quot;') + '">' + nameDisp + '</td>';
        tbode += '<td style="padding: 4px; text-align: center;">' + (e.type || '未分类') + '</td>';
        tbode += '<td style="padding: 4px; text-align: center;">' + (e.name || '').length + '</td>';
        tbode += '<td style="padding: 4px; text-align: center;">' + e._relCount + '</td>';
        tbode += '<td style="padding: 4px; text-align: center;">' + (e.status || 'pending') + '</td>';
        tbode += '<td style="padding: 4px; text-align: center;"><button class="btn btn-sm btn-danger" onclick="deleteOne(' + e.id + ')">删除</button></td>';
        tbode += '</tr>';
    });
    document.getElementById('cleanup-tbody').innerHTML = tbode;

    // 更新全选/批量操作按钮
    document.getElementById('select-all').checked = (filtered.length > 0 && filtered.every(e => cleanupSelected.has(e.id)));
    document.getElementById('btn-batch-delete').disabled = (cleanupSelected.size === 0);
}
```

**Step 4: 辅助函数**

```javascript
function toggleCleanup(cb) {
    if (cb.checked) cleanupSelected.add(cb.value);
    else cleanupSelected.delete(cb.value);
    document.getElementById('btn-batch-delete').disabled = (cleanupSelected.size === 0);
}

function toggleAllClean(cb) {
    // 获取当前筛选后的所有实体 ID
    var lenFilter = document.getElementById('filter-len').value;
    var relFilter = document.getElementById('filter-rel').value;
    var statusFilter = document.getElementById('filter-status').value;
    let filtered = cleanupEntities.filter(e => {
        if (lenFilter === 'short' && (e.name||'').length > 3) return false;
        if (lenFilter === 'mid' && ((e.name||'').length <= 3 || (e.name||'').length > 80)) return false;
        if (lenFilter === 'long' && (e.name||'').length <= 80) return false;
        if (relFilter === 'connected' && e._relCount === 0) return false;
        if (relFilter === 'isolated' && e._relCount > 0) return false;
        if (statusFilter !== 'all' && e.status !== statusFilter) return false;
        return true;
    });
    if (cb.checked) {
        filtered.forEach(e => cleanupSelected.add(e.id));
    } else {
        filtered.forEach(e => cleanupSelected.delete(e.id));
    }
    renderCleanupList();
}

async function batchDeleteEntities() {
    if (cleanupSelected.size === 0) return;
    if (!confirm('确认删除 ' + cleanupSelected.size + ' 个实体及其所有关系吗？此操作不可恢复！')) return;
    try {
        var ids = Array.from(cleanupSelected);
        var resp = await fetch('/api/entities/batch_delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ids: ids})
        });
        var data = await resp.json();
        if (data.success) {
            showToast('已删除 ' + data.deleted + ' 个实体', 'success');
            cleanupSelected.clear();
            await Promise.all([loadEntities(), loadRelations()]);
            loadCleanupData();
        } else {
            showToast('删除失败: ' + data.error, 'error');
        }
    } catch(e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}
```

**Step 5: 面板切换时加载数据**

在 `switchPanel()` 函数中、`search` panel 后面添加清洗面板的激活：

```javascript
if (panelName === 'cleanup') {
    if (!cleanupEntities || cleanupEntities.length === 0) {
        loadCleanupData();
    } else {
        renderCleanupList();
    }
}
```

**Step 6: 编译验证**

```bash
python -c "import py_compile; py_compile.compile('scripts/wiki_manager_web.py', doraise=True); print('OK')"
```

**Step 7: Commit**

```bash
git add scripts/wiki_manager_web.py
git commit -m "feat: 审核清理面板 — 筛选列表 + 批量删除"
```

---

### 验证验证（所有任务完成后）

```bash
curl -s http://127.0.0.1:5000/api/entities?limit=5
# Should return {"entities": [...]}
```

重启服务并验证面板功能。

---

**End of Plan**