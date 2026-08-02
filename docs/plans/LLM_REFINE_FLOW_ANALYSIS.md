# LLM 精筛流程完整性检查报告

## 概述
检查 `wiki_manager_web.py` 和 `llm_refiner.py` 中 LLM 精筛相关流程的完整性。

---

## 一、脚本定位

| 脚本 | 路径 | 角色 |
|------|------|------|
| wiki_manager_web.py | `scripts/wiki_manager_web.py` | Web 服务层（API 接口 + UI） |
| llm_refiner.py | `rag_core/llm_refiner.py` | 核心精筛逻辑（规则预过滤 + LLM 调用） |
| llm_extractor.py | `rag_core/llm_extractor.py` | 实体/关系抽取（独立于精筛） |
| reranker.py | `rag_core/reranker.py` | CrossEncoder 重排（检索后精排） |

---

## 二、API 路由完整性

### ✅ 已实现的路由

| 路由 | 方法 | 功能 | 状态 |
|------|------|------|------|
| `/api/llm/refine-and-extract` | POST | 一键精炼（精筛+关系提取合并） | ✅ |
| `/api/llm/refine-entities` | POST | 单独精筛实体 | ✅ |
| `/api/llm/extract-relations` | POST | 单独提取关系 | ✅ |
| `/api/llm/apply-changes` | POST | 应用精炼变更（实体+关系） | ✅ |
| `/api/llm/apply-refine` | POST | 应用精筛结果（仅实体） | ✅ |
| `/api/llm/review-entities` | GET/POST | LLM 审核实体（旧接口） | ✅ |
| `/api/llm/review-relations` | GET/POST | LLM 审核关系（旧接口） | ⚠️ 逻辑缺陷 |
| `/api/sources` | GET | 列出所有来源文件 | ✅ |
| `/api/settings` | GET | 获取 LLM 配置 | ✅ |
| `/api/settings/update` | POST | 更新 LLM 配置 | ✅ |
| `/api/relations/batch-import` | POST | 批量导入关系 | ✅ |
| `/api/llm/refine-all` | POST | 旧接口（已弃用） | ⚠️ 返回错误提示 |

### ❌ 缺失的路由

| 缺失路由 | 功能说明 |
|---------|---------|
| `/api/llm/apply-relation` | 应用关系提取结果（无单独 API） |
| `/api/llm/retry-refine` | 重试失败的精筛批次 |

---

## 三、流程完整性检查

### 3.1 精筛实体流程 (`/api/llm/refine-entities`)

**完整流程：**
1. ✅ 前端选择来源文件 → POST `/api/llm/refine-entities`
2. ✅ 后端查询实体列表和 chunks
3. ✅ 调用 `LLMRefiner.refine_entities()`
4. ✅ 规则预过滤（_prefilter）
5. ✅ 分批调用 LLM（每批 40 个实体）
6. ✅ 返回精筛结果（valid + removed）
7. ✅ 前端展示结果，点击"应用"按钮
8. ✅ POST `/api/llm/apply-refine` 应用变更
9. ✅ 删除无效实体 + 更新实体类型

**问题：**
- ⚠️ `apply-refine` 不删除关联关系（`DELETE FROM relationships WHERE source_id = ? OR target_id = ?` 存在但只在 `apply_refine` 中）
- ⚠️ 批次失败时回退策略：整批保留（可能导致部分垃圾实体保留）

### 3.2 合并精炼流程 (`/api/llm/refine-and-extract`)

**完整流程：**
1. ✅ 前端选择来源文件 → POST `/api/llm/refine-and-extract`
2. ✅ 后端查询实体列表和 chunks 文本
3. ✅ 调用 `prefilter_entities()` 预过滤（4级优先级）
4. ✅ 第一段 LLM 调用：精筛实体
5. ✅ 第二段 LLM 调用：关系提取（使用精筛后的实体）
6. ✅ 返回合并结果（valid + removed + relations）
7. ✅ 前端展示预览，用户确认后点击"应用全部"
8. ✅ POST `/api/llm/apply-changes` 应用变更
9. ✅ 同时更新实体 + 导入关系

**问题：**
- ⚠️ `apply-changes` 不删除关联关系（只删除实体）
- ⚠️ 关系提取失败时降级为 `relations = []`（非致命）
- ⚠️ 导入关系时未去重（可能重复添加）

### 3.3 关系提取流程 (`/api/llm/extract-relations`)

**完整流程：**
1. ✅ 前端选择来源文件 → POST `/api/llm/extract-relations`
2. ✅ 后端查询实体列表和 chunks
3. ✅ 调用 `LLMRefiner.extract_relations()`
4. ✅ 调用 LLM 提取关系
5. ✅ 返回关系列表
6. ✅ 前端展示，点击"导入所有关系"
7. ✅ POST `/api/relations/batch-import` 批量导入

**问题：**
- ⚠️ 关系提取后无去重检查
- ⚠️ 未验证 source/target 是否真实存在于实体表中

---

## 四、核心模块完整性

### 4.1 LLMRefiner (`rag_core/llm_refiner.py`)

| 功能 | 方法 | 状态 |
|------|------|------|
| 规则预过滤 | `prefilter_entities()` | ✅ |
| 实体精筛 | `refine_entities()` | ✅ |
| 关系提取 | `extract_relations()` | ✅ |
| API 调用 | `_call_api()` | ✅（含重试） |
| JSON 解析 | `_parse_json()` | ✅ |
| 构建精筛 Prompt | `_build_refine_prompt()` | ✅ |
| 构建关系 Prompt | `_build_relation_prompt()` | ✅ |
| 构建合并 Prompt | `build_combined_prompt()` | ⚠️ 已实现但未被使用 |

**缺失：**
- ❌ 无单元测试（`tests/` 目录下无 `test_llm_refiner_integration.py`）
- ❌ 无批量重试机制（批次失败后直接跳过）

### 4.2 LLMExtractor (`rag_core/llm_extractor.py`)

| 功能 | 方法 | 状态 |
|------|------|------|
| 三路提取 | `extract_all()` | ✅ |
| LLM 提取 | `_llm_extract()` | ✅ |
| jieba 提取 | `_jieba_extract()` | ✅ |
| 正则提取 | `_regex_extract()` | ✅ |
| 后端质量过滤 | （内嵌在 `_llm_extract` 中） | ✅ |

**问题：**
- ⚠️ jieba 提取结果直接入库，无 LLM 精筛（质量不稳定）
- ⚠️ 正则提取结果仅作为参考，不入库

---

## 五、数据流完整性

### 精筛数据流
```
Entities (DB) 
    ↓ query entities by source_chapter
    ↓ prefilter_entities()  (规则预过滤)
    ↓ LLMRefiner.refine_entities()  (LLM 精筛)
    ↓ refine result (valid/removed)
    ↓ POST /api/llm/apply-refine
    ↓ DELETE entities + UPDATE type
```

### 关系提取数据流
```
Entities + Chunks (DB)
    ↓ LLMRefiner.extract_relations()
    ↓ relation result
    ↓ POST /api/relations/batch-import
    ↓ INSERT relationships
```

---

## 六、发现的问题

### 🔴 严重问题

1. **关系导入去重缺失**
   - 位置：`/api/relations/batch-import`
   - 问题：未检查关系是否已存在，可能导致重复添加
   - 建议：添加 `(source, target, type)` 唯一约束或去重逻辑

2. **删除实体时关系清理不完整**
   - 位置：`apply_refine()` 和 `apply_changes()`
   - 问题：只删除实体，未删除关联关系
   - 建议：确保删除实体时 cascade 删除关系

3. **jieba 提取无 LLM 精筛**
   - 位置：`llm_extractor.py` → `extract_all()`
   - 问题：jieba 提取结果直接入库，无精筛流程
   - 建议：添加对 jieba 结果的 LLM 精筛

### 🟡 中等问题

4. **合并 Prompt 未被使用**
   - 位置：`llm_refiner.py` → `build_combined_prompt()`
   - 问题：已实现但 `refine-and-extract` API 使用自定义 prompt 而非调用此方法
   - 建议：统一使用 `build_combined_prompt()` 或移除该方法

5. **旧接口残留**
   - 位置：`/api/llm/review-entities` 和 `/api/llm/review-relations`
   - 问题：使用缓存机制（`llm_cache`），但缓存 key 使用 `hash()` 可能不稳定
   - 建议：移除旧接口或修复缓存逻辑

6. **批次失败回退策略保守**
   - 位置：`LLMRefiner.refine_entities()`
   - 问题：批次失败时整批保留（可能导致垃圾实体）
   - 建议：失败时仅标记为"待审核"而非直接保留

### 🟢 轻微问题

7. **无重试机制（精筛批次）**
   - 位置：`LLMRefiner.refine_entities()`
   - 问题：批次失败后直接保留，无重试
   - 建议：添加批次重试逻辑

8. **日志信息不充分**
   - 位置：多处
   - 问题：缺少精筛前后对比统计
   - 建议：添加详细日志（保留率、删除率等）

---

## 七、建议改进

### 1. 添加关系去重
```python
# 在 batch-import 前检查
cursor.execute('''
    SELECT COUNT(*) FROM relationships 
    WHERE source_id = ? AND target_id = ? AND rel_type = ?
''', (src_id, tgt_id, rel_type))
if cursor.fetchone()[0] == 0:
    # 插入新关系
```

### 2. 添加实体删除时的级联关系清理
```python
# 在 apply_refine 中
for ent in removed:
    eid = ent.get('id')
    if eid:
        conn.execute('DELETE FROM relationships WHERE source_id = ? OR target_id = ?', (eid, eid))
        cur = conn.execute('DELETE FROM entities WHERE id = ?', (eid,))
```

### 3. 添加 jieba 结果的 LLM 精筛
```python
# 在 llm_extractor.py 中
if os.environ.get('SKIP_LLM_JIEBA', '0') == '0':
    # 对 jieba 结果进行 LLM 精筛
    refined_jieba = refiner.refine_entities(jieba_result['entities'], chunks)
```

---

## 八、测试覆盖情况

| 测试文件 | 覆盖范围 | 状态 |
|---------|---------|------|
| test_llm_refiner.py | LLMRefiner 初始化、prompt 构建 | ✅ 基本覆盖 |
| test_llm_extractor.py | LLMExtractor 初始化、返回结构 | ⚠️ 仅结构测试 |
| test_llm_extractor_relations.py | 关系提取功能 | ⚠️ 仅结构测试 |
| **缺失** | API 路由测试 | ❌ 无 |
| **缺失** | 端到端流程测试 | ❌ 无 |

---

## 总结

**整体评估：🟡 流程基本完整，但存在数据一致性和质量问题**

- ✅ API 路由覆盖主要场景
- ✅ 核心精筛逻辑完整
- ❌ 关系去重缺失（严重）
- ❌ 实体删除时关系清理不完整（严重）
- ⚠️ jieba 结果无 LLM 精筛
- ⚠️ 测试覆盖不足

**优先级建议：**
1. 修复关系去重问题（立即）
2. 修复实体删除级联清理（立即）
3. 添加 jieba 结果精筛（短期）
4. 补充测试用例（中期）
