# 模型预设切换栏 Implementation Plan

> **REQUIRED SUB-SKILL:** Use the executing-plans skill to implement this plan task-by-task.

**Goal:** 将裸露的 LLM API 输入框改为预设下拉切换 + 可编辑模式。预设存 settings 表 `llm_profiles` 字段（JSON 数组），下拉选预设自动填入字段，可现场编辑并覆盖保存。

**Architecture:** settings 表现有 6 个 key-value（llm_endpoint/key/model/max_tokens/temperature + domain_type）。新增 `llm_profiles` key 存 JSON 数组 `[{name, endpoint, key, model}]`。前端下拉预设 → 填入输入框 → 点保存更新当前配置 + 覆写对应预设。默认 3 个预设（AGNES / GLM / 自定），可新增删除。

**Tech Stack:** Flask + 原生 JS + libsql settings 表

---

### Task 1: 初始化预设数据 + 更新 /api/settings 返回 profiles

**TDD scenario:** Trivial change — 改数据结构和 API 返回格式

**Files:**
- Modify: `scripts/wiki_manager_web.py` (ensure_db_schema + get_settings_api)

**Step 1: ensure_db_schema 写入默认 profiles**

在 `ensure_db_schema()` 的默认值插入后，追加 profiles 初始化：

```python
# 默认 LLM 预设配置
default_profiles = json.dumps([
    {
        "name": "AGNES Flash",
        "endpoint": "https://apihub.agnes-ai.cn/v1",
        "api_key": AGNES_API_KEY or "",
        "model": "agnes-2.0-flash",
    },
    {
        "name": "GLM-4 Flash",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "b92daae003f94dfd95f39b246161fbf0.nHGUco5";
        "model": "glm-4.7-flash",
    },
    {
        "name": "自定义",
        "endpoint": "",
        "api_key": "",
        "model": "",
    },
], ensure_ascii=False)
conn.execute(
    "INSERT OR IGNORE INTO settings (key, value) VALUES ('llm_profiles', ?)",
    (default_profiles,)
)
```

**Step 2: 更新 /api/settings 返回 profiles**

在 `get_settings_api()` 中，额外查 `llm_profiles`：

```python
profile_row = conn.execute(
    "SELECT value FROM settings WHERE key = 'llm_profiles'"
).fetchone()
profiles = json.loads(profile_row['value']) if profile_row else []
return jsonify({"success": True, "settings": settings, "profiles": profiles})
```

需要先 get_db_connection。改函数加 conn 查询。（PRIVATE: 当前函数只用 `get_llm_settings()` 不自己连数据库，加一个 conn 查询。）

**Step 3: 重启验证**

```bash
curl -s http://127.0.0.1:5000/api/settings | python -m json.tool | head -20
```

验证 `profiles` 数组存在。

**Step 4: Commit**

```bash
git add scripts/wiki_manager_web.py
git commit -m "feat: settings 表加 llm_profiles 预设，/api/settings 返回 profiles"
```

---

### Task 2: HTML 面板改造 — LLM API 区域加预设下拉

**TDD scenario:** Trivial change — HTML 修改

**Files:**
- Modify: `scripts/wiki_manager_web.py` (HTML_TEMPLATE 区域配置 div)

将当前裸露的 `<input>` 三个框改为：预设下拉 + 可编辑输入框。

```html
<!-- 预设切换 -->
<select id="profile-select" onchange="switchProfile()" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px;">
    <option value="">-- 选择模型预设 --</option>
</select>
<!-- 配置输入（点击预设自动填入，也可手动编辑） -->
<input type="text" id="llm-endpoint" placeholder="API 端点" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 240px;">
<input type="text" id="llm-key" placeholder="API Key" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 180px;">
<input type="text" id="llm-model" placeholder="模型名" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 140px;">
<button class="btn btn-primary" onclick="saveLLMSettings()" style="padding: 6px 14px;">保存</button>
```

**Step 2: Commit**

```bash
git add scripts/wiki_manager_web.py
git commit -m "feat: 前端加预设下拉切换栏"
```

---

### Task 3: JS — 加载预设 / 切换预设 / 保存时覆写预设

**TDD scenario:** Trivial change — JS 修改

**Files:**
- Modify: `scripts/wiki_manager_web.py` (JS 函数 loadLLMSettings, saveLLMSettings + 新函数 switchProfile)

**switchProfile() 逻辑：**

```javascript
async function switchProfile() {
    const sel = document.getElementById('llm-profile-select');
    const idx = sel.selectedIndex;
    if (idx <= 0) return;
    const profiles = window.__llm_profiles || [];
    const p = profiles[idx - 1]; // option[0] 是提示
    if (p) {
        document.getElementById('llm-endpoint').value = p.endpoint || '';
        document.getElementById('llm-key').value = p.api_key || '';
        document.getElementById('llm-model').value = p.model || '';
    }
}
```

**loadLLMSettings 改造：**

```javascript
async function loadLLMSettings() {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.success) {
        const s = data.settings;
        if (s.llm_endpoint) document.getElementById('llm-endpoint').value = s.llm_endpoint;
        if (s.llm_api_key) document.getElementById('llm-key').value = s.llm_api_key;
        if (s.llm_model) document.getElementById('llm-model').value = s.llm_model;
        if (s.domain_type) document.getElementById('domain-select').value = s.domain_type;

        // 加载预设列表
        window.__llm_profiles = data.profiles || [];
        const sel = document.getElementById('llm-profile-select');
        sel.innerHTML = '<option value="">-- 选择模型预设 --</option>' +
            window.__llm_profiles.map(p => `<option>${escapeHtml(p.name)}</option>`).join('');
        
        // 自动匹配当前生效的预设
        const curEndpoint = s.llm_endpoint || '';
        const curModel = s.llm_model || '';
        for (let i = 0; i < window.__llm_profiles.length; i++) {
            const p = window.__llm_profiles[i];
            if (p.endpoint === curEndpoint && p.model === curModel) {
                sel.selectedIndex = i + 1;
                break;
            }
        }
    }
}
```

**saveLLMSettings 改造：**

```javascript
async function saveLLMSettings() {
    const settings = {
        domain_type: document.getElementById('domain-select').value,
        llm_endpoint: document.getElementById('llm-endpoint').value,
        llm_api_key: document.getElementById('llm-key').value,
        llm_model: document.getElementById('llm-model').value,
    };
    // 如果选中了某个预设，更新该预设的配置
    const sel = document.getElementById('llm-profile-select');
    if (sel.selectedIndex > 0) {
        const idx = sel.selectedIndex - 1;
        const profiles = window.__llm_profiles || [];
        if (profiles[idx]) {
            profiles[idx].endpoint = settings.llm_endpoint;
            profiles[idx].api_key = settings.llm_api_key;
            profiles[idx].model = settings.llm_model;
            settings.llm_profiles = JSON.stringify(profiles);
        }
    }
    // ... 发送请求
}
```

**Step 3: Commit**

```bash
git commit -am "feat: 预设下拉切换 + 保存时更新预设配置"
```

---

### Task 4: 后端 /api/settings/update 支持 profiles 更新

**TDD scenario:** Trivial change — API 修改

**Files:**
- Modify: `scripts/wiki_manager_web.py` (update_settings)

在 update_settings 里，如果传入 `llm_profiles` 字符串，则更新到 settings 表：

```python
if 'llm_profiles' in updates:
    conn.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        ('llm_profiles', updates['llm_profiles'])
    )
```

**Step 4: Commit**

```bash
git commit -am "feat: /api/settings/update 支持 llm_profiles 字段"
```

---

### Task 5: 端到端验证

**Step 1: 重启服务**

```bash
taskkill //F //IM python.exe 2>/dev/null; sleep 1
D:/class/miniconda3/envs/ml_env/python.exe scripts/wiki_manager_web.py &
```

**Step 2: 验证预设**

```bash
curl -s http://127.0.0.1:5000/api/settings | python -c "import sys,json; d=json.load(sys.stdin); print('profiles:', len(d.get('profiles',[])), d.get('profiles',[])[:2])"
```

**Step 3: Web 验证**
- 打开 `http://127.0.0.1:5000` → LLM 精筛面板
- 预设下拉应显示 AGNES Flash / GLM-4 Flash / 自定义
- 选 AGNES → 输入框自动填入
- 选 GLM → 自动填入
- 手动改 model 名 → 点保存 → 刷新页面 → 预设选中项配置已更新

**Step 4: Commit**

```bash
git commit -am "chore: 端到端验证完成"
```

---