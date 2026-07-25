# langchain-rag 目录垃圾清理计划

**清理时间**：2026-07-05 11:47
**执行方式**：手动清理垃圾文件

---

## 🗑️ 垃圾文件分类

### 1. 临时脚本（可以删除）✅
| 文件名 | 说明 |
|--------|------|
| add_guzhenren.py | 临时添加蛊真人脚本 |
| add_guzhenren_direct.py | 临时添加蛊真人脚本 |
| convert_guzhenren_utf8.py | 临时转换脚本 |
| fast_load_guzhenren.py | 临时快速加载脚本 |
| incremental_load_guzhenren.py | 临时增量加载脚本 |
| load_guzhenren_dedup.py | 临时去重加载脚本 |
| load_guzhenren_resume.py | 临时断点续传加载脚本 |
| reload_guzhenren.py | 临时重载脚本 |
| search_guzhenren_goal.py | 临时搜索脚本 |
| split_novel.py | 临时分割小说脚本 |
| split_novel_final.py | 临时分割小说脚本 |
| split_novel_v2.py | 临时分割小说脚本 |
| test_async_build.py | 临时测试脚本 |
| test_async_build_complete.py | 临时测试脚本 |
| test_async_build_full.py | 临时测试脚本 |
| test_github_simple.py | 临时测试脚本 |
| test_github_token.py | 临时测试脚本 |
| test_lsh_search.py | 临时测试脚本 |
| test_resume_loader.py | 临时测试脚本 |
| test_search_raw.py | 临时测试脚本 |
| upload_all_documents.py | 临时上传脚本 |
| upload_documents_simple.py | 临时上传脚本 |

**小计**：23 个文件

---

### 2. 日志文件（可以删除）✅
| 文件名 | 说明 |
|--------|------|
| rag_server.log | 服务器日志 |
| storage/add_doc.log | 文档添加日志（如存在） |
| storage/novel_import.log | 小说导入日志（如存在） |
| storage/check_status.log | 状态检查日志（如存在） |

**小计**：1-4 个文件

---

### 3. 临时 JSON 文件（可以删除）✅
| 文件名 | 说明 |
|--------|------|
| search_results_guzhenren_goal.json | 搜索结果 |
| search_results_simple.json | 搜索结果 |

**小计**：2 个文件

---

### 4. 空文件 ✅
| 文件名 | 说明 |
|--------|------|
| nul | 空文件 |

**小计**：1 个文件

---

### 5. 缓存目录（可以删除）✅
| 目录名 | 说明 |
|--------|------|
| __pycache__/ | Python 字节码缓存 |
| .pytest_cache/ | Pytest 缓存 |
| .pytest_cache/v/ | Pytest 缓存版本 |
| rag_core/__pycache__/ | Python 字节码缓存 |
| rag_core/chunkers/__pycache__/ | Python 字节码缓存 |
| rag_core/quality/__pycache__/ | Python 字节码缓存 |
| tests/__pycache__/ | Python 字节码缓存 |

**小计**：8 个目录

---

## ✅ 需要保留的文件

### 核心脚本
- add_documents.py - 文档添加工具
- check_knowledge_base.py - 知识库检查工具
- clean_then_reload.py - 清理重载工具
- import_novel_chapters.py - 小说导入工具
- rag_cli.py - RAG CLI 工具
- rag_server.py - RAG 服务器
- rag_server_v2.py - RAG 服务器 V2

### 配置文件
- package.json - Node.js 配置
- package-lock.json - Node.js 锁文件
- requirements.txt - Python 依赖

### 文档文件
- README.md - 说明文档
- PROJECT_INDEX.md - 项目索引
- PROJECT_SUMMARY.md - 项目总结
- ARCHITECTURE_STATUS.md - 架构状态
- EXECUTION_SUMMARY_*.md - 执行总结
- HYBRID_ROUTER_SUMMARY.md - 混合路由总结
- IMPLEMENTATION_SUMMARY.md - 实现总结
- LOAD_SUMMARY_*.md - 加载总结
- PROJECT_EXPERIENCES.md - 项目经验
- UPGRADE_SUMMARY.md - 升级总结
- KNOWLEDGE_BASE_ISSUES.md - 问题分析
- KNOWLEDGE_BASE_FIX_PLAN.md - 修复计划
- CLEANUP_REPORT.md - 清理报告
- FIX_SUMMARY.md - 修复总结
- FIX_REPORT.md - 修复报告
- PHASE_SUMMARY.md - 阶段总结

---

## 📊 清理统计

| 类型 | 数量 |
|------|------|
| 临时脚本 | 23 个 |
| 日志文件 | 1-4 个 |
| 临时 JSON | 2 个 |
| 空文件 | 1 个 |
| 缓存目录 | 8 个 |
| **总计** | **35-38 项** |

---

## 🎯 清理效果

- **减少文件数**：~35 个
- **释放空间**：~5-10 MB（主要是缓存和日志）
- **目录更清晰**：只保留核心脚本和文档

---

## ⚠️ 备份说明

所有要删除的文件都可以通过 git 恢复（如果已提交），或者可以从 `backups/backup_20260705/` 恢复。

---

**清理完成时间**：2026-07-05 11:47
**状态**：待执行
