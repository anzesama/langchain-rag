# 阶段复盘：slo.txt 兼容性修复
- 时间：2026-08-06
- 状态：✅ 完成

## ✅ 做得好的点
- 快速识别 `wiki_graph_web.py` 中重复定义的 `load_data` 函数（8 个定义）
- 使用 `sed` 直接定位问题行号，精确定位需要删除的片段
- 在修复前先用 `py_compile` 验证语法，确保改动正确

## 📝 未完成事项
- 任务 7（统一后端）标记为低优先级，已验证语法正确，可后续优化

## 🐛 遇到的问题
- `wiki_graph_web.py` 有 8 个重复的 `load_data` 函数定义（第 68-172 行），前 7 个是空壳，只有最后一个完整
- `auto_search_import.py` 使用旧的 `wiki_db` 导入路径，需要改为 `wiki_db_libsql`
- `wiki_review_web.py` 有残留的 "数据同步" tab，但代码中已注释说明 libsql 架构下无需同步

## 📦 产出物
- `slo_fixes_report.md` — 兼容性修复报告
- Git 提交：`637dff8`

## ➡️ 下一步
1. 运行 `python scripts/doc_importer.py` 验证导入流程
2. 启动 `python scripts/wiki_manager_web.py --open` 验证 Web UI
3. 测试图谱节点大小是否按连接数差异化显示

---

# 阶段复盘：RAG 软约束自启动 + 闲置/内存感知退出
- 时间：2026-11-02 03:35
- 状态：✅ 完成（V1~V7 全部验证通过）

## ✅ 做得好的点
- 定位到"设计存在但从未生效"的**真正根因是部署漂移**（源码 07-08 版 vs 部署 06-24 版），而非功能没写
- 全程 TDD：先写 12 个测试（RED）再实现（GREEN），看门狗逻辑抽成纯函数 `should_shutdown`
- 低内存下用"真实 app/中间件/看门狗 + 跳过 Embedding 预加载"做快速端到端验证（避免 1.2GB 换页抖动）
- 发现并规避两个环境坑：低内存时 PowerShell 启动卡死；`Get-FileHash` 不可用 → 改 .NET MD5
- 顺手加了防漂移安装脚本（md5 校验），根治同类问题

## 📝 未完成事项
- ⚠️ 需用户在 pi 中执行 `/reload` 才能真正加载新扩展（我无法代劳）
- ⚠️ KB 中 `troubleshooting.md` 快照需再次同步（本次又更新了源文件）
- ⚠️ 无自动同步机制（troubleshooting.md → KB 仍靠手动）

## 🐛 遇到的问题
- **部署漂移**：源码更新未部署 → 功能形同虚设（4 层断裂）
- **测试轮询干扰**：用 `/health` 轮询观测"是否自动退出"，结果轮询本身重置了计时器 → 须完全静默后观测
- 既有失败 9 个（测试隔离缺陷 / 活体 LLM / 环境缺失），与本改动无关

## 📦 产出物
- 🆕 `rag_core/idle_watchdog.py` + `tests/test_idle_watchdog.py`（12 tests）
- 🆕 `scripts/start_rag_server.ps1`（参数化，唯一配置源）
- 🆕 `scripts/install_rag_extension.ps1`（防漂移，md5 校验）
- ✏️ `scripts/rag_server_v2.py`（看门狗线程 + `/api/shutdown` + 中间件 touch）
- ✏️ `rag_extension/pi_rag_tool.ts`（修复路径/python/ps1 + 走 RAG_HOME）
- ✏️ `~/.pi/agent/extensions/pi_rag_tool.ts`（已部署，md5 一致）
- ✏️ `README.md`（服务管理章节重写）
- ✏️ `docs/plans/2026-10-31-rag-autostart-{design,plan}.md`

## 🔬 验收实测
| 项 | 结果 |
|---|---|
| V2 持续请求不退出 | ✅ 16s 轮询全程存活 |
| VS `POST /api/shutdown` | ✅ 1.0s 退出 |
| V3 闲置自动退出 | ✅ 15.1s（harness）/ **137s（真实服务 idle>120s）** |
| V5 `IDLE=0` 常驻 | ✅ 20s 未退出 |
| V1 ps1 → 真实服务 → 搜索 | ✅ http=200 + 正确答案（LLM 链路通）|
| V6 安装脚本 | ✅ in sync / deployed 两分支 |
| V7 测试 | ✅ 新增 12 passed（既有 9 失败无关）|
| 内存释放 | ✅ 82MB → 575MB（释放 ~500MB）|

## ➡️ 下一步
- 用户在 pi 执行 `/reload` → 验证 `search_knowledge_base` 自动拉起
- 建议：写 `sync_kb.ps1` 一键同步 troubleshooting.md 到 KB（并考虑加计划任务）

---

# 阶段复盘：RAG 自动启动快速失败（避免阻塞 pi 主循环）
- 时间：2026-11-02 12:20
- 状态：✅ 完成

## ✅ 做得好的点
- 快速定位根因：不是 spawn 失败（`pwsh` 已安装），而是「spawn 成功但冷启动慢 + waitForService 360s 死等 + 未接 AbortSignal」
- 用 probeShell 前置探测 shell 可用性，避免未来换机没装 `pwsh` 又卡（快速失败）
- spawn error 纳入 Promise（宽限期 3s），不再静默返回 true（快速失败）
- `waitForService` 缩短预算到 30s 可配，接 AbortSignal 可中断 sleep（不再傻等到预算耗尽）
- `ragFetchWithAutoStart` 透传 signal、超时不再二次 spawn（避免重复拉起竞争）
- 测试零 npm 安装：node 24 原生 strip-types + node:test + `node_modules/typebox` symlink（指向 pi 全局包）

## 📝 未完成事项
- 无（全部按设计落地）

## 🐛 遇到的问题
- **测试环境 typebox 解析**：jiti + virtualModules 在测试中因路径分隔符问题失败 → 改用 node 24 原生 strip-types + `node_modules/typebox` symlink（指向 pi 全局包）

## 📦 产出物
- ✏️ `rag_extension/pi_rag_tool.ts`（8 处改动：常量 30s/1s 可配 + probeShell + spawn error Promise + waitForService AbortSignal + ragFetchWithAutoStart signal 透传）
- 🆕 `rag_extension/test_pi_rag_tool.mts`（8 条测试全过：覆盖设计文档 7 条 TDD + default 导出可加载）
- ✏️ `docs/plans/2026-11-02-rag-autostart-fastfail-design.md`（设计文档）

## 🔬 验收实测
| 项 | 结果 |
|---|---|
| 单测（8 条） | ✅ 全过（node:test + node 24 原生 TS） |
| 部署 md5 校验 | ✅ src/dst 一致（D2EB3B21...） |
| RAG 未运行时 ragFetchWithAutoStart | ✅ 33.7s 内快速失败（≤40s 阈值），返回「冷启动较慢，请手动启动 / RAG_IDLE_TIMEOUT_SEC=0」，不再阻塞 360s |

## ➡️ 下一步
- 用户在 pi 执行 `/reload` → 验证 `search_knowledge_base` 真实调用时不再阻塞 pi 主循环
- 按需更新 `troubleshooting.md`（如需记录本条踩坑）

---

# 阶段复盘：RAG 搜索快速化 — Brainstorm
- 时间：2026-11-03 03:01
- 状态：✅ 完成

## ✅ 做得好的点
- 用户最初描述"效果不明显"，通过追问（A/B/C/D/E 选项）澄清为**性能问题（慢/卡）**而非检索质量问题 —— 避免走错方向
- 用代码证据定位根因（非猜测）：`/api/search` 同步 def + 单 worker + `kb.search()` 内嵌远程 LLM + 已有未启用的 `search_raw()`
- 发现 `pi` 官方**明确不支持内置 MCP**（`docs/usage.md:275`）→ 一票否决所有 MCP 类候选方案
- GitHub 调研 5 轮，形成成熟方案对比表并给出**适配性**判断（低内存 + pi 不支持 MCP）
- 关键判断：**不换引擎**（换引擎需重算 12,572 chunks 向量），改架构（检索/生成分离）成本低得多
- 向用户讲透 C（异步化）的原理：FastAPI `def` vs `async def`、threadpool、GIL、多 worker OOM —— 用户据此选择 C1（轻量版）

## 📝 未完成事项
- 内容质量问题（知识库 80% 是小说/教程，项目规范未入库）——本次不处理，另行立项
- 换引擎方案（swarmvault 等）——暂不采用

## 🐛 遇到的问题
- 无（本轮为方案设计，未执行改动）

## 📦 产出物
- 🆕 `docs/plans/2026-11-03-rag-fastsearch-design.md`（设计文档，已 commit 8fc4594）

## ➡️ 下一步
- 进入 Plan 阶段（writing-plans）：把设计拆成可执行步骤
- 再进入 Execute 阶段（TDD）：服务端 pytest → pi 扩展 node:test

---

# 阶段复盘：RAG 自启动「真·修复」+ pi 崩溃事故（2026-11-03）

- 时间：2026-11-03 10:51
- 状态：✅ 完成（E2E 复验待用户 `/reload` 后执行）

## ✅ 做得好的点
- **崩溃现场用会话 jsonl 定位**（`~/.pi/agent/sessions/**/*.jsonl` 尾部）—— pi 崩溃不留 WER/事件日志，这是唯一可靠手段；4 条独立证据交叉验证
- **0 字节源文件无损恢复**：用「写临时文件 → 设旧 mtime → 原子 replace」绕开仍在运行的看门狗，全程 pi 未再崩
- **隔离复现技巧**：`node -e "import('./rag_extension/pi_rag_tool.ts').then(m=>m.startRagService())"` 绕开 pi/`/reload`，秒级验证 spawn 路径 —— 避免每轮都烧一次 `/reload`
- **TDD**：先写 4 条 RED（`shellProbeArgs`/`shellCandidates`/`RAG_SHELL`/`shellStartArgs`）再实现；另加 2 条崩溃回归防护（断言无 `decideReload`、无 `fs.watch`/`tool_call` 触发）
- **对照实验定位**：`detached+fd-stdio` vs `stdio:inherit` 两组跑同一脚本 → 一眼看出是 spawn 选项而非脚本问题
- **可观测性补齐**：`stdio:"ignore"` 曾导致零诊断 → 落盘 `logs/extension_start.log`（spawn 行 + 结果）

## 🐛 遇到的问题
1. **pi 进程崩溃 + 源文件被截断为 0 字节** —— 根因：自建 `rag_autoreload` 用 `fs.watch` 监视源文件并在 `tool_call` 里自动 `ctx.reload()`，恰好在 LLM 用 edit 改该文件时打断写入。已根除（改为只提醒 + 手动 `/rag-reload`）
2. **auto-start 第二次从未生效** —— 根因：`probeShell` 用 `-v` 探活，WinPS 5.1 把 `-v` 当 `-Version`（需参数）报错 → 恒失败 → `startRagService` 直接返回 false → **从不 spawn**；且 pwsh 不在 pi 的 PATH 里。已修（`-Command exit 0` + 绝对路径候选表）
3. **`detached: true` + fd-stdio 让子进程秒退** —— 实测 pwsh 3s 内 code=0 退出且零输出。已改为 `stdio:"ignore"` + 非 detached + `unref()`

## 📝 未完成事项
- **E2E 复验 V1**（首次调用即成功 + 进度提示）—— 阻塞于用户执行 `/reload`
- V3 闲置退出验证（服务最后活动 ~10:48，预计 10:53~10:54 自动退出）
- 建议项未做：`scripts/sync_kb.ps1` 一键同步 / pytest 独立临时库根治污染 / 启动前低内存警告
- **另有一条线**：`docs/plans/2026-11-03-rag-fastsearch-design.md`（检索/生成分离，C1 轻量版，commit `8fc4594`）设计已完成，待进入 Plan 阶段

## 📦 产出物
- ✏️ `rag_extension/pi_rag_tool.ts`（120s 预算 + `progressMessage`/`onProgress` 进度提示 + shell 探测与 spawn 修复）
- ✏️ `rag_extension/rag_autoreload.ts`（移除危险自动重载 → 只提醒 + 手动 `/rag-reload`）
- ✏️ `rag_extension/test_pi_rag_tool.mts`（14 tests，含 4 条本轮 TDD + 2 条崩溃回归防护）
- ✏️ `tests/test_rag_autoreload.mjs`（6 tests）
- ✏️ `scripts/install_rag_extension.ps1`（双文件覆盖 + `-Check` exit 1）
- ✏️ `D:/class/project-config/troubleshooting.md`（1960 → 2066 行，+2 条，**不提交**）

## ➡️ 下一步
- 用户 `/reload` → 我调 `search_knowledge_base` 做 E2E 复验（服务停掉状态下应"首次调用即成功"并显示进度）
- 验证 V3 闲置退出
- 视情况处理 fastsearch（Plan 阶段）与 3 条建议项

---

# 阶段复盘：RAG fastsearch 验收（Verify 阶段，2026-11-03 12:40）

- 时间：2026-11-03 12:40
- 状态：⚠️ 部分通过（功能全绿；性能目标 <2s 实测 2.2s，差 ~15%）

## 🔎 关键发现：设计早已实现
崩溃前那轮会话**已把 `2026-11-03-rag-fastsearch-design.md` 全部实现并提交**：
`d7fc865`（/api/search_raw）→ `4845c85`（LLM 15s 超时+降级）→ `20225a9`（端点异步化）→ `45104ff`（扩展改调 search_raw）。
所以「继续待续计划」的真身是 **Verify**，不是 Plan。

## ✅ 验收证据（全部新鲜实测）
| # | 项 | 命令/方法 | 结果 |
|---|----|----------|------|
| 1-4 | 服务端 4 条测试 | `pytest tests/test_rag_server_search.py -q` | ✅ **6 passed**, exit 0 |
| — | **无污染自证** | `chunks` 计数前后对比 | ✅ **12572 = 基线** |
| 5-6 | 扩展测试 | `node --test`（3 个文件） | ✅ **24 passed / 0 fail** |
| 7 | `/api/search_raw` 性能 | node fetch ×3 | ⚠️ **2.278 / 2.165 / 2.293s**（目标 <2s）|
| 7b | 响应结构 | 同上 | ✅ `keys=query,sources`、`hasAnswer=false`、sources=6 |
| 8 | `/api/search` 回归 | node fetch | ✅ 14.2s http=200、`keys=query,answer,sources,route,degraded`、answer 857 字 |
| — | 自动启动 E2E | 冷服务下直接调用 | ✅ 3 次全部成功（冷启动 14s）|
| — | 闲置退出 | 非轮询单次检查 | ✅ idle=330s 自动退出（两次印证）|

## 🐛 遇到的问题
- **curl 传中文 JSON body → HTTP 400 `There was an error parsing the body`** —— shell/控制台编码把 UTF-8 body 搞坏。改用 `--data-binary @file.json`
- **node 读 `/tmp/xxx.json` → `ENOENT: D:\tmp\xxx.json`** —— git-bash 的 `/tmp` 与 node 的路径解析不一致。改用项目相对路径
- 性能目标差 15%：`search_raw` 两段各 ~1.1s（多路召回 / 融合+父子检索）；内存紧张（free 703MB、服务 Private 922MB）会加剧

## 📝 未完成事项
- **性能 <2s 目标未达**（实测 2.2s）—— 待用户决定：接受 / 优化（如 graph `hops=2`→1、候选 48 收敛）
- 3 条既有建议项（sync_kb.ps1 / pytest 独立临时库 / 低内存启动警告）

## ➡️ 下一步
- 用户裁决性能项 → 若优化则走 brainstorming（会改变检索质量，属设计级变更）
- 之后进入 Review / Finish 阶段

---

# 阶段复盘：Execute（P0 地基修复）
- 时间：2026-11-04 01:30
- 状态：✅ 完成

## ✅ 做得好的点
- **TDD 全程守规矩**：P0-1a 用「DB 文件指纹」而非「chunk 计数」做守卫（计数法漏掉了 `INSERT OR REPLACE` 的污染）；P0-2 先 RED（0.520s）后 GREEN（0.239s）
- **追根因而非打补丁**：`VectorStoreManager.__init__` 忽略 `persist_dir` 才是污染根因，不是测试写错了
- **主动更正自己的错误结论**：发现"150×"是内存压力抖动后，立即更正 2 份文档 + 记入 troubleshooting.md，而不是继续沿用
- **隔离升级**：从只隔离 DB，扩展到 LSH/index/id_map 全量，并发现测试确实在写生产索引

## 📝 未完成事项
- Phase 1（记忆系统）尚未开始 — 原因：先做 P0 是用户选定的顺序
- `storage/knowledge_base.db.pre-cleanup-20261104`（118MB 备份）未处置 — 待用户决定保留/删除

## 🐛 遇到的问题
- **生产 KB 被 pytest 打成 690 chunks** — 解决：git stash 定向提取恢复 + 新增 conftest 双防线
- **性能结论被内存压力误导（150×）** — 解决：拆阶段复测 + 热态/多测/中位数；已更正文档与教训
- **`.gitignore` 漏 add 导致 amend** — 解决：`git commit --amend`
- **两个扩展测试文件从未提交** — 解决：`afc9fe2` 补提交

## 📦 产出物
- `tests/conftest.py`（双防线：路径重定向 + 多文件指纹守卫）
- `tests/test_vector_search_perf.py`（正确性 + 性能，N=20000 < 0.35s）
- `rag_core/vector_store_libsql.py`（向量化余弦检索）
- `.gitignore`（storage/ 全量忽略）
- 提交：`730c93c` / `922f137` / `6ef1727` / `afc9fe2`

## ➡️ 下一步
- Phase 1：`Chunk` 模型扩展 + `rag_core/memory_scoring.py` 纯函数 + `RAG_MEMORY_ENABLED` 开关 + `/api/memories/stats`

---

# 阶段复盘：Execute（Phase 1 脑启发性记忆层）
- 时间：2026-11-04 02:15
- 状态：✅ 完成

## ✅ 做得好的点
- **纯函数先行**：`memory_scoring.py` 零 IO、零全局状态，35 项单测覆盖长度/关键词/来源权重/半衰期/封顶边界，测试 2 秒跑完
- **零侵入迁移**：`ALTER TABLE ADD COLUMN` + 幂等 + 有默认值 → 可回滚；专门测了「旧库升级不丢数据」（事故教训直接变成测试）
- **开关隔离彻底**：`RAG_MEMORY_ENABLED` 关闭时不重排/不加 metadata/**不写库**，三点都有测试
- **主动标注偏离**：半衰期语义（`exp(-Δ/H)` → `2^(-Δ/H)`）与返回分数语义两处偏离设计，已在计划文档明确记录

## 📝 未完成事项
- Phase 2 剩余项（向量预归一化 / `_query_cache` 命中率 / 接入 `HybridRetriever`）
- Phase 3（HNSW / int8 量化 / 双轨存储）— 可选长期
- `stash@{0}` 仍未裁决
- 情景记忆（episodic）当前为 0 —— 须先有「重要时刻」写入方（Phase 3）

## 🐛 遇到的问题
- **测试输入长度踩到自己的阈值**：`test_very_short_text_is_penalized` 的「正常文本」只有 42 字，同样落入 `<50` 罚分 → 修正为 70 字（测试输入问题，非实现问题）
- **多行 edit 因一个不匹配的 oldText 整体失败**：工具是原子的 → 去掉多余的第三个 edit 重发

## 📦 产出物
- `rag_core/memory_scoring.py`（新，纯函数）
- `rag_core/vector_store_libsql.py`（迁移 + 记忆重排 + 统计）
- `scripts/rag_server_v2.py`（`GET /api/memories/stats`）
- 测试：`test_memory_scoring.py`(35) / `test_memory_schema.py`(7) / `test_memory_retrieval.py`(12) / `test_memory_stats.py`(10)
- 验收：V1–V7 全部通过（node 25 / pytest 116）

## ➡️ 下一步
- Review 阶段（派发 code-reviewer 子代理）
- 或先做 Phase 2/3
