# LLM 精筛 + 关系提取 + Web 适配实现计划

> **REQUIRED SUB-SKILL:** Use the executing-plans skill to implement this plan task-by-task.

**Goal:** 改造 wiki_manager_web.py 的 LLM 辅助判断面板，使其支持 LLM 精筛 jieba 实体 + 关系提取 + 领域分类切换 + API 配置

**Architecture:** rag_core/llm_refiner.py 提供 LLM精筛/关系提取接口 → Web settings表存储API配置 → wiki_manager_web.py 新增面板

**Tech Stack:** Python 3.9, Flask, libsql, jieba, OpenAI-compatible LLM API

**Special considerations:**
- 原小说版 `call_llm()` 函数保留但重构为通用版本
- `settings` 表新建（key/value schema）
- 领域分类系统（ML/小说/自定义）通过 JSON 模板存储，切换时 Prompt 自动适配
- 关键词绑定：`refine-entities`、`extract-relations`、`source-chunks-entities`

---

## Task 1: 数据库迁移 — settings 表 + 领域模板存储

**What:** 在 `wiki_manager_web.py` 的 `ensure_db_schema()` 中新增 settings 表创建

**Steps:**
1. 在 `ensure_db_schema()` 中添加 `SETTINGS` 表：
   ```sql
   CREATE TABLE IF NOT EXISTS settings (
       key TEXT PRIMARY KEY,
       value TEXT
   )
   ```
2. 添加默认 API 配置项：
   ```python
   DEFAULTS = {
       'llm_endpoint': rag_config.AGNES_API_BASE,
       'llm_api_key': rag_config.AGNES_API_KEY,
       'llm_model': 'agnes-2.0-flash',
       'domain_type': 'machine-learning',
       'max_tokens': '3000',
       'temperature': '0.1'
   }
   ```
3. 检查 `ensure_db_schema()` 在 app 启动时自动调用，确保新表存在

**Testing:** 重启 wiki_manager_web，确认 DB 中 settings 表被创建，默认值被写入

**Commits:**
- `db: settings 表 + 默认 LLM API 配置`

---

## Task 2: llm_refiner.py — LLM 精炼 + 关系提取模块

**What:** 创建 `rag_core/llm_refiner.py`，封装 LLM API 调用和 Prompt 构建

**Steps:**

1. 创建 `rag_core/llm_refiner.py`，接口如下：
   ```python
   class LLMRefiner:
       def __init__(self, endpoint: str, api_key: str, model: str, domain: str = 'machine-learning'):
           self.endpoint = endpoint
           self.api_key = api_key
           self.model = model
           self.domain = domain

       def _build_refine_prompt(self, entities: list, chunks: list, domain: str) -> str
       def _build_relation_prompt(self, chunks: list, entities: list) -> str
       def refine_entities(self, entities: list, chunks: list) -> dict
       def extract_relations(self, chunks: list, entities: list) -> dict
   ```

2. `_build_refine_prompt` 生成类似如下 prompt：
   ```
   你是知识图谱审核专家。请审核以下 [ML 领域] 的关键实体列表。

   【实体列表】
   - 交叉验证 (类型: 方法)
   - 欠拟合 (类型: 未分类)

   【上下文 chunks】
   <chunk_texts>

   请分析：
   1. 各实体有效性（应保留/应删除/需修改分类）
   2. 建议的正确分类
   ```
   返回 JSON：`{"valid": [...], "invalid": [...], "suggestions": [...]}`

3. `_build_relation_prompt` 生找到类似如下 prompt：
   ```
   你是知识图谱关系提取专家。从以下文本中提取 [ML 领域] 的实体间关系。

   【上下文 chunks】
   {chunks}

   【已知实体列表】
   {entities}

   提取所有有意义的关系，格式：
   [{"source": "欠拟合", "target": "交叉验证", "type": "防止"}]
   ```

4. `refine_entities()` 流程：
   - 构建 prompt → 调用 `call_llm` → 解析 JSON → 过滤（name 匹配 + 长度/quality）
   - 返回：`{"entities": [...], "removed": [...] , "suggestions": [...]}`

5. `extract_relations()` 流程：
   - 构建 prompt → 调用 `call_llm` → 解析 JSON → 过滤（source/target 在实体集中）
   - 返回：`{"relations": [...], "count": N}`

6. **领域系统**：根据 `domain` 参数（`machine-learning` / `novel` / `ontology`），动态切换：
   ```python
   DOMAIN_CONFIGS = {
       'machine-learning': {
           'entity_types': ['算法', '模型', '方法', '概念', '指标', '工具', '框架', '数据集'],
           'rel_types': ['使用', '基于', '对比', '包含', '实现', '改进', '防止', '优化', '关联'],
           'entity_review_rules': '关键词型术语，2-20字，不能是描述句',
           'relation_check': 'source/target 在实体列表中，关系在上下文中明确出现'
       },
       'novel': {
           'entity_types': ['人物', '蛊虫', '势力', '流派', '地点', '境界', '法宝'],
           'rel_types': ['持有', '属于', '主修', '师承', '盟友', '敌对', '击杀', '使用', '控制'],
           'entity_review_rules': '小说命名实体，2-8汉字，不能含英文/数字',
           'relation_check': 'source/target 在实体列表中，关系在剧情中明确出现'
       },
       'ontology': {
           'entity_types': ['概念', '属性', '实例', '关系', '约束', '公理'],
           'rel_types': ['is-a', 'has-part', 'instance-of', 'related-to', 'constrained-by'],
           'entity_review_rules': '概念型术语，不应含数字或特例',
           'relation_check': 'source/target 在实体列表中，本体论约束'
       }
   }
   ```

**Testing:** `tests/test_llm_refiner.py` — 测试 prompt 构建逻辑（不调用 LLM API），验证 domain 切换

**Commits:**
- `feat: rag_core/llm_refiner.py + 测试 — Prompt 构建 + 领域切换`
- `test: test_llm_refiner 领域切换+Prompt 构建测试`

---

## Task 3: LLM 功能通用化 — call_llm 从 rag_config 改为 settings 表

**What:** `wiki_manager_web.py` 中的 `call_llm` 函数改为根据 settings 表读取 API 配置

**Steps:**
1. 新增函数：
   ```python
   def get_llm_settings():
       conn = get_db_connection()
       try:
           cursor = conn.execute('SELECT key, value FROM settings WHERE key LIKE "llm_%"')
           rows = cursor.fetchall()
           result = {}
           for row in rows:
               result[row['key']] = row['value']
           return result
       finally:
           conn.close()
   ```

2. 修改 `call_llm()` 为：
   ```python
   def call_llm(prompt: str, max_tokens: int = 2000) -> str:
       settings = get_llm_settings()
       if not settings.get('llm_api_key'):
           raise RuntimeError("LLM API Key 未在设置中配置")
       base_url = settings.get('llm_endpoint', 'http://21.200.171.222:9090')
       # 使用 settings 中的 key/model
       ...
   ```

3. `/api/llm/health-check` 端点：测试 connectivity（不消耗 tokens）：
   ```python
   @app.route('/api/llm/health-check', methods=['POST'])
   def health_check():
       try:
           # 调用 call_llm('Hello', max_tokens=10)
           return {"success": True, "connected": True}
       except Exception as e:
           return {"success": False, "error": str(e)}
   ```

4. `get_llm_settings()` 函数供 Web 面板调用 — GET `/api/settings`：
   ```python
   @app.route('/api/settings')
   def get_settings():
       s = get_llm_settings()
       return jsonify(s)
   ```

**Testing:** 手动启动 wiki_manager_web.py → 测试 `/api/settings` 返回默认值 + `/api/llm/health-check` 返回连通状态

**Commits:**
- `feat: call_llm 改为 settings 表驱动`
- `feat: /api/settings + /api/llm/health-check 端口`

---

## Task 4: LLM 精筛 API 端点 + Web 面板

**What:** 在 `wiki_manager_web.py` 中新增精筛端点 + 修改 HTML/JS

**Steps:**

1. 新增端点：
   ```python
   @app.route('/api/llm/refine-entities', methods=['POST'])
   def refine_entities():
       data = request.json
       source_file = data.get('source')
       if source_file is None:
           ents = data.get('entities', [])
       else:
           # 从 entities 表查询 source_chapter 匹配的实体
           conn = get_db()
               rows = conn.execute('SELECT e.id, e.name, e.type, e.properties FROM entities e WHERE e.source_chapter = ?', (source_file,) )
               ents = [dict(row) for row in rows]
           if not ents:
               return {"success": False, "error": f"没有找到 source_file: {source_file}"}

       settings = get_llm_settings()
       refiner = LLMRefiner(settings['llm_endpoint'], settings['llm_api_key'], settings['llm_model'], settings['domain_type'])
       chunks = get_chunks_from_source(source_file) if source_file else []
       result = refiner.refine_entities(ents, chunks)
       return jsonify({"success": True, "result": result})
   ```

2. 创建 `get_chunks_from_source(source)` 辅助函数：
   ```python
   def get_chunks_from_source(source):
       conn = get_db_connection()
       rows = conn.execute("SELECT id, chunk_text FROM chunks WHERE source = ?", (source,))
       return [dict(row) for row in rows.fetchall()]
   ```

3. HTML 端：在 LLM 面板中新增"精筛实体"按钮 + 来源文件下拉选择器：
   - 来源文件列表从 `/api/chunks/sources` 或 `GET /api/sources` 获取
   - 点击 → 发送 `/api/llm/refine-entities` → 显示结果表格（实体名 | 原类型 | 推荐分类 | 状态）

4. 应用按钮：用户可以把 LLM 精筛结果写入实体（更新 type/状态）

**Testing:** 选择 AAAMLP-CN 中的某文件 → 点击 LLM 精筛 → 前端显示返回的实体列表

**Commits:**
- `feat: /api/llm/refine-entities + Web 精筛面板`
- `feat: Web精筛结果 + 应用按钮`

---

## Task 5: LLM 关系提取端点 + Web 面板

**What:** 新增 `/api/llm/extract-relations` 端点

**Steps:**
1. 创建端点：
   ```python
   @app.route('/api/llm/extract-relations', methods=['POST'])
   def extract_relations():
       data = request.json
       source = data.get('source')  # 来源文件
       entity_ids = data.get('entity_ids', [])  # 可选：select entities
       # 获取 chunk 文本 + 实体列表
       conn = get_db()
       rows = conn.execute("SELECT e.id, e.name, e.type FROM entities e WHERE e.source_chapter = ?", (source,))
       entities = [dict(row) for row in rows]

       chunks = get_chunks_from_source(source)
       settings = get_llm_settings()
       refiner = LLMRefiner(settings['llm_endpoint'], settings['llm_api_key'], settings['llm_model'], settings['domain_type'])
       relations = refiner.extract_relations(chunks, entities)
       return jsonify({"success": True, "relations": relations})
   ```

2. `/api/relations/import` POST — 批量写入关系：
   ```python
   @app.route('/api/relations/import', methods=['POST'])
   def import_relations():
       data = request.json
       relations = data.get('relations', [])
       # 用 wiki_db.add_relationship 每条写入
       for rel in relations:
           wiki_db.add_relationship(rel['source'], rel['target'], rel['type'], source_chapter=source)
       return {"success": True, "added": len(relations)}
   ```

3. HTML 端：关系提取面板：
   - 来源文件选择器（同上）
   - 点击后提交 → 前端显示候选关系列表 [source → target，type]
   - 全选/取消 → 批量导入 → 完成

**Testing:** 手动从 AAAMLP-CN 单个文件提取关系 → 验证返回 JSON 格式

**Commits:**
- `feat: /api/llm/extract-relations + Web 提取面板`
- `feat: /api/relations/import 批量写入端点`

---

## Task 6: 领域切换 Web 配置面板

**What:** 设置页面支持域切换 + 自定义域名

**Steps:**
1. Web 端的 LLM 面板加一个领域选择器：
   ```html
   <select id="domain-select" onchange="setDomain(this.value)">
       <option value="machine-learning">ML 知识点</option>
       <option value="novel">小说/剧情</option>
       <option value="ontology">技术概念本体</option>
       <option value="custom">自定义...</option>
   </select>
   ```

2. `/api/settings/update` POST — 写 settings 表：
   ```python
   @app.route('/api/settings/update', methods=['POST'])
   def update_settings():
       data = request.json
       key = data['key']
       value = data['value']
       conn = get_db()
       conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
       conn.commit()
       return {"success": True}
   ```

3. 前端确认后调用 `/api/settings/update` 存新的值和LLM配置

**Testing:** 切换领域 → 所有后端调用的 Prompt 正确切换

**Commits:**
- `feat: 领域切换面板 + API配置页面`

---

## Task 7: 端到端验证 + 文档

**Steps:**
1. 手动验证：导入 AAAMLP-CN → 查看实体 → LLM 精筛来源文件 → 关系提取 → 切换领域不报错
2. 更新 CHANGELOG.md / README.md：拍摄新增功能（LLM 精筛/关系提取/领域切换）
3. 知识库 importer 配合（`import.py`）—— 确认 `--llm` 标志通过 LLM 补充关系

**Testing:** 端到端测试

**Commits:**
- `docs: LLM 精筛+关系提取+领域切换 完成文档`

---

## Dependencies

```
T1 (DB) → T2 (LLM模块) → T3 (call_llm 通用化)
                               ↓
T2 → T4 (精筛端点)       T5 (关系提取端点)
         ↓                  ↓
                         T6 (领域切换)
                               ↓
                         T7 (验证+ 文档)
```