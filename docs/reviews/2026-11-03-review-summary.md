# Code Review Report: RAG Stability Fix (2026-11-03)

**时间**: 2026-11-03 22:15
**Reviewer**: Agnes (agent)
**范围**: `rag_extension/`, `scripts/`, `tests/`

---

## ✅ Critical（已修复）

### 1. `RAG_SHELL` ReferenceError → `noShellMessage()`
**问题**: `pi_rag_tool.ts:131` 在模板串中引用未声明标识符 `RAG_SHELL`（重构后改为局部变量 `override`），导致错误路径抛 ReferenceError。

**修复**:
- 新增纯函数 `noShellMessage(): string`（`rag_extension/pi_rag_tool.ts:71-80`）
- 函数内部调用 `shellCandidates().join(", ")` 列出真实尝试的候选
- 错误分支改为 `console.error(noShellMessage())`（line 144）

**测试**: test 14 RED → GREEN ✅（test_pi_rag_tool.mts）

---

## ⚠️ Important（待改进）

### 2. `rag_autoreload.ts` 静默 catch
**位置**: line 68 `} catch {`
**建议**: 改为 `} catch (e) { console.warn(...) }`，便于开发阶段排查 notify 失败原因。
**优先级**: 低（生产环境提醒失败不影响主功能）

---

## ℹ️ Minor（已验证安全）

### 3. `rag_autoreload.ts` 无 fs.watch（事故回归防护）
- 旧版危险代码已彻底清除
- 文件 md5: `89bb09af...`（部署副本与源码一致）
- 仅在 `session_start` 检查 mtime 差异 + 提醒，不自动 reload

### 4. 扩展上下文安全
- `ctx.reload()` 仅在 `/rag-reload` 命令中由用户主动触发
- 文件写入使用 atomic replace（mtime 保留 2020-01-01 避免误触 watch）

---

## 📊 测试覆盖

```
✅ rag_extension/test_pi_rag_tool.mts      15 tests pass
✅ tests/test_rag_autoreload.mjs            4 tests pass
✅ tests/test_rag_tool_start.mjs            6 tests pass
✅ tests/test_rag_server_search.py          6 tests pass
总: 25/25 pass, 0 fail
```

---

## 🎯 结论

**所有 Critical bug 已修复，代码可合并**。建议：
1. 本次 PR 合并主修复
2. Important/Minor 项列入后续改进 backlog

**批准**: ✅ Ready to merge（Critical 已修，剩余为改进项）
