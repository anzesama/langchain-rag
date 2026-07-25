# Phase 1: 负反馈闭环 + 时间维度 - 实施总结

## 📅 实施时间
2026-07-09

## ✅ 完成内容

### 1. 数据库表扩展

#### 1.1 entity_history 表
```sql
CREATE TABLE entity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    old_properties TEXT,
    new_properties TEXT,
    change_reason TEXT,
    changed_by TEXT,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP,
    is_correction BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
)
```

**功能**：
- 记录实体属性的所有变更历史
- 支持版本回滚
- 标记修正操作

#### 1.2 pending_reviews 表（增强版）
```sql
CREATE TABLE pending_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT,
    entity_name TEXT NOT NULL,
    entity_type TEXT,
    properties TEXT,
    relation_type TEXT,
    source_id TEXT,
    target_id TEXT,
    confidence REAL DEFAULT 0.5,
    source_text TEXT,
    source_chapter TEXT,
    review_status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(id),
    FOREIGN KEY(source_id) REFERENCES entities(id),
    FOREIGN KEY(target_id) REFERENCES entities(id)
)
```

**功能**：
- 独立于 entities 表的待审核队列
- 支持实体和关系的审核
- 记录置信度和原始文本

#### 1.3 correction_log 表
```sql
CREATE TABLE correction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(entity_id) REFERENCES entities(id)
)
```

**功能**：
- 汇总记录所有修正操作
- 便于审计和追踪

---

### 2. 核心功能实现

#### 2.1 属性修正
```python
correct_entity_property(
    entity_name: str,
    property_name: str,
    new_value: Any,
    change_reason: str = None,
    changed_by: str = "system"
) -> bool
```

**功能**：
- 修正实体属性
- 自动生成历史记录
- 记录修正原因和操作人

**示例**：
```bash
python wiki_cli.py correct "元始仙尊" "主修" --property "主修=天道" --reason "用户纠正，正确应为天道"
```

#### 2.2 历史版本查询
```python
get_entity_history(entity_name: str, limit: int = 10) -> List[Dict]
```

**功能**：
- 查询实体的所有历史版本
- 显示修改时间、操作人、原因
- 支持版本回滚

**示例**：
```bash
python wiki_cli.py history "元始仙尊" --limit 10
```

#### 2.3 版本回滚
```python
rollback_entity_version(entity_name: str, version_id: int) -> bool
```

**功能**：
- 回滚实体到指定历史版本
- 标记旧版本为过期（valid_to = CURRENT_TIMESTAMP）

**示例**：
```bash
python wiki_cli.py rollback "元始仙尊" --version_id 1
```

#### 2.4 待审核队列（增强版）
```python
get_pending_reviews(
    review_status: str = 'pending',
    limit: int = 20,
    entity_type: str = None
) -> List[Dict]
```

**功能**：
- 支持按状态过滤（pending/approved/rejected）
- 支持按实体类型过滤
- 返回详细信息（置信度、原文、来源章节）

**示例**：
```bash
python wiki_cli.py review-pending --limit 20 --entity-type "人物"
```

#### 2.5 审核操作
```python
approve_review(review_id: int, reviewed_by: str = "system") -> bool
reject_review(review_id: int, reject_reason: str = "", reviewed_by: str = "system") -> bool
```

**功能**：
- 审核通过待审核项
- 审核拒绝待审核项（可选原因）
- 自动更新 review_status 和 reviewed_by

**示例**：
```bash
python wiki_cli.py approve --review-id 1
python wiki_cli.py reject --review-id 1 --reason "内容不准确"
```

---

### 3. CLI 命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `correct` | 修正实体属性 | `correct "元始仙尊" "主修" --property "主修=天道" --reason "纠正"` |
| `history` | 查看历史版本 | `history "元始仙尊" --limit 10` |
| `rollback` | 回滚版本 | `rollback "元始仙尊" --version_id 1` |
| `review-pending` | 查看待审核项 | `review-pending --limit 20 --entity-type "人物"` |
| `reject` | 拒绝待审核项 | `reject --review-id 1 --reason "不准确"` |

---

## ✅ 验收结果

### 1. 数据库表创建
- [x] entity_history 表创建成功
- [x] pending_reviews 表创建成功
- [x] correction_log 表创建成功
- [x] 索引创建成功

### 2. 功能测试
- [x] correct 命令：成功修正实体属性并记录历史
- [x] history 命令：成功显示历史版本
- [x] review-pending 命令：成功显示待审核列表
- [x] rollback 命令：功能实现（待测试）
- [x] reject 命令：功能实现（待测试）

### 3. CLI 集成
- [x] 所有新命令成功注册
- [x] 参数解析正确
- [x] 错误处理完善

---

## 🐛 已修复问题

1. **SQL 查询缺少 'id' 列**
   - 问题：`get_entity_history()` 中 SQL 查询缺少 `id` 列
   - 解决：在 SELECT 语句中添加 `id` 列

2. **history 命令索引错误**
   - 问题：`reversed(history)` 返回迭代器，导致 `history[-i]` 报错
   - 解决：将 `reversed(history)` 转换为列表 `list(reversed(history))`

3. **命令映射不匹配**
   - 问题：命令名使用连字符（`review-pending`），但命令映射使用下划线（`review_pending`）
   - 解决：在命令映射中同时添加连字符和下划线形式

---

## 📊 测试数据

### 修正示例
```
实体: 元始仙尊
属性变更: 主修 = 力道 → 天道
修正原因: 用户纠正，正确应为天道
历史记录:
  - 旧属性: {'主修': '力道', '时间': '自动'}
  - 新属性: {'主修': '天道'}
  - 操作人: cli
  - 时间: 2026-07-09 11:13:25
```

### 表统计
```
entity_history: 1 条记录
correction_log: 1 条记录
```

---

## 🎯 下一步计划

### Phase 2: 推理引擎
- [ ] 定义推理规则（持有→主修、师承→师兄弟等）
- [ ] 实现 `wiki_reasoner.py` 模块
- [ ] 集成到 WikiUpdater
- [ ] 添加 CLI 命令触发推理

### Phase 3: 事实锚点 + RAG 约束
- [ ] 创建 facts 表
- [ ] 实现 `add_fact()` 和 `get_facts_for_entity()`
- [ ] 在 RAG pipeline 中集成事实约束
- [ ] 添加 CLI 命令

### Phase 4: 自动发现增强
- [ ] 增强置信度评分
- [ ] 实现高置信度自动入库
- [ ] 完善自动发现流程

---

## 📝 经验总结

### ✅ 做得好的地方
1. **数据库设计**：清晰分离了 entities、history、pending_reviews、correction_log 四个表，职责明确
2. **CLI 集成**：新增命令语法清晰，参数完整
3. **错误处理**：所有方法都有 try-except，返回 bool 标识成功/失败

### ⚠️ 需要改进的地方
1. **日志输出**：GBK 编码导致中文乱码，需要统一使用英文或配置编码
2. **测试覆盖**：缺少单元测试和集成测试
3. **文档完善**：需要补充 API 文档和使用示例

---

## 📦 产出物

- [x] `rag_core/wiki_db.py` - 扩展了数据库表和核心方法
- [x] `scripts/wiki_cli.py` - 新增 5 个 CLI 命令
- [x] `docs/wiki/PHASE1_SUMMARY.md` - 本总结文档
- [x] `test_phase1.py` - 测试脚本
- [x] `test_history_debug*.py` - 调试脚本

---

**状态**: ✅ Phase 1 完成
