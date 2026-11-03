# 代码审查报告：Phase 1 脑启发性记忆层

- 日期：2026-11-04
- 范围：`5e4f300..a22e203`（P0 修复 + Phase 1）
- 方式：2 个 code-reviewer 子代理（范围 A/B）+ 1 次人工实证审查（范围 C）
  - 说明：范围 C 的子代理派发失败（403 并行失败、429 限流、120s 无响应被杀）→ 按 AGENTS.md 止损规则改为人工 grep 实证
- 原则：**所有发现先实证再采信**，不盲信审查结论

---

## 一、审查发现的验证结果

| # | 来源 | 发现 | 实证结论 | 处理 |
|---|------|------|---------|------|
| 1 | A | `compute_importance` 传非 str 会 `TypeError` | ✅ 成立 | 已修 + 测试 |
| 2 | A | `compute_final_score` 不处理 NaN | ✅ **成立且更严重**：`max(0.0, min(1.0, nan))` 返回 **1.0**，NaN 会排到**最前** | 已修 + 测试 |
| 3 | A | `_resolve_half_life` 读 env，不算"纯函数" | ✅ 成立（文档问题） | 已改文档表述 |
| 4 | A | "LUFY 六维"名不副实 | ✅ 成立 | 已改文档为"规则版 MVP" |
| 5 | A | `metadata` 是哑参数 | ✅ 成立 | 加 TODO 注释 |
| 6 | A | `test_now_defaults_to_utcnow` 注释说 "1 microsecond" | ❌ **不成立**（代码中无此注释，幻觉） | 不处理 |
| 7 | A | 正则 `.{0,6}` 会跨行匹配 | ❌ **不成立**（Python `.` 默认不匹配 `\n`，实测 False） | 不处理 |
| 8 | B | 排序键可能 `datetime` vs `None` → `TypeError` | ⚠️ **理论成立但不可达**（元组第 3 元素是唯一的行号 `i`，永远轮不到尾部比较） | 已加固（显式排序键）+ 注释 |
| 9 | B | `_reinforce` 逐条 UPDATE 会部分提交 | ❌ **不成立**（`isolation_level=''` → 隐式事务，`in_transaction=True`，提交是原子的） | 仍加显式 `rollback()` 防御 |
| 10 | B | 迁移并发 → `duplicate column name` → `__init__` 崩溃 | ✅ 成立 | 已修（捕获 `OperationalError`）+ 测试 |
| 11 | B | 建议改 `ADD COLUMN IF NOT EXISTS` | ❌ **该建议本身是错的**（SQLite 不支持，实测 3.51.2 报语法错误） | 采用 try/except 方案 |
| 12 | B | `get_memories_stats` 全表扫 `last_access` | ✅ 成立（可优化） | 已加 `WHERE last_access IS NOT NULL` |
| 13 | B | 关闭记忆时 SELECT 多取 3 列 | ⚠️ 成立但无影响（列数不改变输出，"逐字节一致"指行为） | 不处理（保持单一代码路径） |
| 14 | C | 隔离不完备：有模块绑定路径常量未被 patch | ✅ **成立，且实际造成了污染**（见下） | 已修 |

**误报率 4/14**，验证是必要的。

---

## 二、🔴 审查 C 挖出的真实事故（本次最大收获）

`tests/test_unified_importer.py` / `test_auto_importer.py` **一直在写生产库**，
只是旧守卫覆盖面太窄（只盯 3 个文件）而漏报。

### 现象（守卫升级后抓到的证据）
```
id_map.pkl:         (28479756, ...) -> (28479929, ...)      # +173B = 1 向量
knowledge_base.db:  (118071296, ...) -> (118071296, ...)    # 同 size，mtime 变 = INSERT OR REPLACE
novel_lsh.index:    (9567325, ...) -> (9567581, ...)        # +256B
```

### 根因（三层，逐层实证）
1. **`WikiDB` 的默认路径从 `__file__` 推算**（`rag_core/wiki_db_libsql.py:54-60`），
   不是从 `rag_config` 常量读取 → **monkeypatch 常量完全无效**，永远指向生产库。
   且 `get_wiki_db()` 是**全局单例**，跨测试复用。
2. **`conftest.py` 自身的 bug**：扫描 `sys.modules` patch 同名路径常量时，
   **把 conftest 自己的 `STORAGE_DIR` 也 patch 成临时目录** → 后续迭代的
   `_is_under(v, STORAGE_DIR)` 比较基准被污染 → `rag_config.*` 一个都没 patch 上
   （探测输出：`patched 1 ['tests.conftest.STORAGE_DIR']`）。
3. 旧守卫只覆盖 3 个文件，而 `vector_store.db` / `wiki.db` / `progress_*.json` /
   `global_counter.json` 等同样是生产状态，写坏了不会被发现。

### 修复
| 文件 | 改动 |
|------|------|
| `tests/conftest.py` | ① 引入**不可变基准** `PRODUCTION_STORAGE` ② 跳过 conftest 自身 ③ 守卫覆盖 `storage/` **全部文件**（递归，排除 `*.log`） ④ 重置 `_wiki_db_instance` 单例 |
| `rag_core/wiki_db_libsql.py` | 默认路径改读 `LIBSQL_DICTIONARY_PATH`（可被隔离 patch）+ 自动建父目录 |
| `tests/test_guard_coverage.py` | 新增 13 项守卫覆盖面测试 |

### 残留污染清理
- 审计出测试窗口（19:40–19:52）写入的 **10 块**（`_pytest_*` / `test*.txt|md|json` / `subdir\nested.txt` / `integration_test.txt`）
- 先备份 `storage/knowledge_base.db.pre-testfix-20261104`，再按**精确 chunk_id** 删除
- 结果：12596 → **12586**，残留测试命名源：无

> 这已是**同一类事故的第三次**（13198→690、+607 块、+10 块）。
> 结论：**"守卫覆盖面"必须一次性做全，窄守卫比没有守卫更危险**（给出虚假安全感）。

---

## 三、最终验证

| 项目 | 结果 |
|------|------|
| `pytest tests/`（排除 3 个需外网 LLM 的文件） | **178 passed / 1 failed / 0 errors** |
| 唯一失败 | `test_wiki_pipeline.py::test_path_config` — `ModuleNotFoundError`，**改动前即存在**，与本次无关 |
| `node --test`（3 文件） | **25 passed / 0 fail** |
| 生产库 | 12586 chunks，测试前后指纹不变（守卫零触发） |
| 新增测试 | 记忆 67 项 + 守卫 13 项 + 鲁棒性/竞态 20 项 |

---

## 四、结论

**就绪（Ready）**。

- 2 个 Critical（NaN 排序污染、WikiDB 生产写库）已修复并有回归测试
- 审查误报 4 项已驳回并记录理由（不盲从）
- 1 项审查建议本身有误（`ADD COLUMN IF NOT EXISTS`）已纠正
- 剩余 Minor（`metadata` 哑参数、SELECT 列数、`_vector_to_blob` 内重复 `import struct`）不阻塞

**遗留**：
- `storage/knowledge_base.db.pre-cleanup-20261104` / `.pre-testfix-20261104`（各 118MB 备份）待用户决定去留
- `stash@{0}` 仍未裁决
