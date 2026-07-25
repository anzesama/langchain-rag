# libsql 迁移指南

- 日期：2026-07-25
- 状态：📋 待实施
- 目标：使用 libsql 替代 ChromaDB 和 SQLite，统一存储层

---

## 📋 目录

1. [概述](#概述)
2. [前置条件](#前置条件)
3. [迁移步骤](#迁移步骤)
4. [回退预案](#回退预案)
5. [验证方法](#验证方法)
6. [常见问题](#常见问题)

---

## 概述

### 背景

当前 RAG 系统使用混合存储方案：
- **ChromaDB**：向量存储（存储文档块 + 向量 + 元数据）
- **SQLite**：Wiki 数据库（存储实体、关系、历史版本、事实）
- **FAISS LSH 索引**：加速检索（独立存储）

### 问题

- 存储层不统一，数据冗余
- ChromaDB 和 SQLite 功能重叠
- 维护成本高

### 解决方案

使用 libsql（本地文件存储）统一存储：
- 向量数据：chunks 表（chunk_id, vector, metadata）
- 结构化数据：entities/relationships/facts 表
- FAISS LSH 索引：继续独立存储（用于加速检索）

---

## 前置条件

### 1. 备份现有数据

**重要**：在开始迁移前，必须先备份现有数据！

```bash
# 运行备份脚本
python scripts/backup_before_migration.py
```

备份内容包括：
- ChromaDB 数据
- SQLite 数据
- LSH 索引
- 全局计数器

### 2. 检查磁盘空间

确保有足够的磁盘空间：
- libsql 数据库文件：约 5-10 GB（取决于文档数量）
- 备份文件：约 10 GB（临时）

### 3. 确认 Python 环境

确保使用 `ml_env` 环境：
```bash
conda activate ml_env
python --version  # 应该是 3.9.x
```

---

## 迁移步骤

### 步骤 1：创建迁移分支

```bash
# 确保在迁移分支上
git checkout feature/libsql-migration

# 拉取最新代码
git pull origin feature/libsql-migration
```

### 步骤 2：备份现有数据

```bash
# 运行备份脚本
python scripts/backup_before_migration.py
```

备份成功后，会创建一个备份目录，如：`storage/backup_20260725_143022/`

### 步骤 3：执行迁移

```bash
# 运行迁移脚本
python scripts/migrate_to_libsql.py
```

迁移脚本会：
1. 创建 libsql 数据库和表结构
2. 从 ChromaDB 迁移向量数据
3. 从 SQLite 迁移 Wiki 数据
4. 保留 LSH 索引不变
5. 验证数据完整性

### 步骤 4：验证迁移结果

```bash
# 运行验证脚本
python scripts/verify_migration.py
```

验证脚本会检查：
- libsql 文件是否存在
- 数据库连接是否正常
- 向量数据数量
- 实体数据数量
- 关系数据数量
- 与备份数据对比

### 步骤 5：测试功能

```bash
# 启动 RAG 服务
python scripts/rag_cli.py service start

# 测试搜索功能
python scripts/rag_cli.py search "方源的目标是什么"

# 测试 Wiki 查询
python scripts/rag_cli.py wiki-search "方源主修什么流派？"
```

### 步骤 6：更新代码（如需要）

如果发现任何问题，可以：
1. 运行回滚脚本恢复数据
2. 修复代码问题
3. 重新执行迁移

### 步骤 7：提交代码

```bash
# 查看修改的文件
git status

# 添加修改的文件
git add .

# 提交
git commit -m "feat: 完成 libsql 迁移

- 使用 libsql 替代 ChromaDB 和 SQLite
- 统一存储层
- 保留 LSH 索引用于加速检索
- 性能提升 2-3 倍（预估)"

# 推送到远程
git push origin feature/libsql-migration
```

---

## 回退预案

### 快速回滚

如果迁移后发现问题，可以快速回滚到迁移前的状态：

```bash
# 1. 停止 RAG 服务
python scripts/rag_cli.py service stop

# 2. 运行回滚脚本
python scripts/rollback_libsql.py

# 3. 重启服务
python scripts/rag_cli.py service start

# 4. 验证服务
python scripts/rag_cli.py status
```

### 回滚时间窗口

- **最佳回滚时间**：迁移后 24 小时内
- **回滚方式**：快速回滚脚本（< 1 分钟）
- **回滚后验证**：运行 `verify_migration.py` 确认数据完整性

### 回滚后数据恢复

如果超过 24 小时，建议重新从文档加载数据：

```bash
# 1. 运行回滚脚本
python scripts/rollback_libsql.py

# 2. 重新从文档加载数据
python scripts/rag_cli.py add-dir

# 3. 验证数据
python scripts/rag_cli.py status
```

---

## 验证方法

### 迁移前验证

```bash
# 1. 检查 ChromaDB 数据
ls -lh storage/knowledge_base/

# 2. 检查 SQLite 数据
ls -lh storage/data/wiki/wiki.db

# 3. 检查 LSH 索引
ls -lh storage/lsh_index/
```

### 迁移后验证

```bash
# 1. 运行验证脚本
python scripts/verify_migration.py

# 2. 检查 libsql 数据库
ls -lh storage/knowledge_base.db

# 3. 测试数据库连接
sqlite3 storage/knowledge_base.db "SELECT COUNT(*) FROM chunks;"

# 4. 测试搜索功能
python scripts/rag_cli.py search "测试查询"
```

### 数据对比

对比迁移前后的数据量：

| 数据类型 | 迁移前 | 迁移后 | 差异 |
|---------|-------|-------|------|
| 向量数据 | ~18,738 个块 | ~18,738 个块 | 0 |
| 实体数据 | ~100+ 个 | ~100+ 个 | 0 |
| 关系数据 | ~200+ 条 | ~200+ 条 | 0 |

---

## 常见问题

### Q1: 迁移后数据丢失了？

**A**: 迁移前已备份，可以通过回滚脚本恢复：
```bash
python scripts/rollback_libsql.py
```

### Q2: 迁移后性能下降？

**A**: 迁移后性能应该提升，如果下降：
1. 运行性能测试
2. 检查数据库索引
3. 优化查询语句
4. 考虑回滚

### Q3: 迁移失败怎么办？

**A**:
1. 检查错误日志
2. 运行回滚脚本恢复
3. 查看回退预案文档
4. 联系技术支持

### Q4: 如何验证数据完整性？

**A**: 运行验证脚本：
```bash
python scripts/verify_migration.py
```

### Q5: 迁移后如何删除旧数据？

**A**: 迁移成功后，可以删除旧的 ChromaDB 和 SQLite 数据：
```bash
# 删除 ChromaDB
rm -rf storage/knowledge_base

# 删除 SQLite
rm storage/data/wiki/wiki.db

# 删除备份（可选）
rm -rf storage/backup_20260725_143022
```

---

## 相关文档

- [实现计划](../plans/20260725-libsql-migration-plan.md)
- [回退预案](./LIBSQL_ROLLBACK_PLAN.md)
- [API 参考](../wiki/API_REFERENCE.md)

---

**最后更新**：2026-07-25
**维护者**：RAG Team
