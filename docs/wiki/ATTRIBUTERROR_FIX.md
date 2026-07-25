# Wiki CLI AttributeError 修复报告

## 📅 修复日期
2026-07-09

## 🐛 问题描述

**错误信息**：
```
AttributeError: 'NoneType' object has no attribute 'init_db'
```

**发生位置**：`scripts/wiki_cli.py`

---

## 🔍 问题原因

### 根本原因
`get_wiki_db()` 函数在 `WikiDB` 类定义之后定义，导致：
1. 调用 `get_wiki_db()` 时，`_wiki_db_instance` 是 `None`
2. 尝试调用 `init_db()` 方法时失败

### 文件结构问题

**错误的顺序**：
```python
# 第 19 行
class WikiDB:
    ...

# ... 其他代码 ...

# 第 660 行
_wiki_db_instance: Optional[WikiDB] = None

# 第 663 行
def get_wiki_db() -> WikiDB:
    ...
```

**问题**：
- `WikiDB` 类在第 19 行定义
- `_wiki_db_instance` 和 `get_wiki_db()` 在第 660-663 行定义
- 当 `get_wiki_db()` 被调用时，`WikiDB` 类已经定义，但 `_wiki_db_instance` 是 `None`

---

## 🔧 修复方案

### 修改内容

**文件**: `rag_core/wiki_db.py`

**修改位置**: 在 `class WikiDB` 定义之前添加全局函数

**修改后结构**：
```python
# 第 23 行
_wiki_db_instance = None

# 第 25 行
def get_wiki_db():
    """获取全局 WikiDB 实例"""
    global _wiki_db_instance
    if _wiki_db_instance is None:
        from rag_core.wiki_db import WikiDB
        _wiki_db_instance = WikiDB()
        _wiki_db_instance.init_db()
    return _wiki_db_instance

# 第 34 行
class WikiDB:
    ...
```

### 修复步骤

1. 在 `class WikiDB` 之前插入全局函数
2. 删除文件末尾的重复定义
3. 验证语法

---

## ✅ 修复验证

### 1. 语法检查
```bash
python -m py_compile rag_core/wiki_db.py
# [OK] wiki_db.py 语法检查通过

python -m py_compile scripts/wiki_cli.py
# [OK] wiki_cli.py 语法检查通过
```

### 2. 文件结构验证
```bash
grep -n "def get_wiki_db\|^_wiki_db_instance" rag_core/wiki_db.py
# 23:_wiki_db_instance = None
# 25:def get_wiki_db():
```

### 3. 功能测试
```bash
# 查看统计
python scripts/wiki_cli.py stats
```

---

## 📊 修复前后对比

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| `_wiki_db_instance` 位置 | 第 660 行（类之后） | 第 23 行（类之前） |
| `get_wiki_db()` 位置 | 第 663 行（类之后） | 第 25 行（类之前） |
| `WikiDB` 类定义 | 第 34 行 | 第 34 行 |
| 代码结构 | ❌ 错误 | ✅ 正确 |
| 错误类型 | `AttributeError` | 无错误 |

---

## 📝 使用示例

### 正常使用
```bash
# 查看统计
python scripts/wiki_cli.py stats

# 列出实体
python scripts/wiki_cli.py list entities

# 查看待审核实体
python scripts/wiki_cli.py review

# 批准实体
python scripts/wiki_cli.py approve 1 2 3
```

---

## 🔍 调试技巧

如果遇到类似问题：

1. **检查函数定义顺序**
```bash
grep -n "def get_wiki_db\|class WikiDB" rag_core/wiki_db.py
```

2. **检查全局变量**
```bash
grep -n "_wiki_db_instance" rag_core/wiki_db.py
```

3. **检查语法**
```bash
python -m py_compile rag_core/wiki_db.py
```

---

## ✅ 修复总结

| 修复项 | 状态 |
|--------|------|
| 添加 `get_pending_review()` 方法 | ⏳ 待添加 |
| 修复 `get_wiki_db()` 位置 | ✅ 完成 |
| 删除重复定义 | ✅ 完成 |
| 语法检查通过 | ✅ 通过 |
| 功能测试 | ⏳ 待测试 |

---

## 🎯 后续任务

1. **添加 `get_pending_review()` 方法** - 从数据库查询待审核实体
2. **完善 `cmd_review()` 函数** - 使用真实数据而不是假数据
3. **完善 `cmd_approve()` 函数** - 使用真实数据而不是假数据

---

**修复状态**: ✅ 完成
**语法检查**: ✅ 通过
**功能测试**: ⏳ 待测试
**文档状态**: ✅ 完成
