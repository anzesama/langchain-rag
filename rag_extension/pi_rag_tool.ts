/**
 * pi Extension — RAG 知识库工具（软约束自启动版）
 *
 * 设计：首次调用工具时若服务未运行 → 自动 spawn scripts/start_rag_server.ps1
 *       → 轮询 /health 直至就绪 → 执行请求。服务端自带闲置/内存感知退出。
 *
 * 单一配置源：
 *   - 启动配置（python 路径 / LLM 端点 / 阈值）全在 scripts/start_rag_server.ps1
 *   - 本扩展只认一个 RAG_HOME 常量（可用环境变量覆盖）
 *
 * 安装（防漂移，务必用安装脚本，别手抄）：
 *   powershell -ExecutionPolicy Bypass -File scripts\install_rag_extension.ps1
 *   然后 pi 里执行 /reload
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "fs";
import * as path from "path";
// 注：/rag-reload 命令由独立扩展 rag_autoreload.ts 注册（它会被 pi 自动加载），
//     此处不再 import，避免重复注册。

const RAG_API_BASE = process.env.RAG_API_BASE || "http://localhost:8765";
const RAG_PORT =
  Number(process.env.RAG_PORT) || 8765;
const RAG_HOME =
  process.env.RAG_HOME || "D:/class/project-config/langchain-rag";
const RAG_START_SCRIPT = path.join(RAG_HOME, "scripts", "start_rag_server.ps1");
// ── shell 解析（2026-11-03 修复）─────────────────────────────────────────
// 事故根因：probeShell 曾用 `-v` 探活 → WinPS 5.1 把 `-v` 当 `-Version`（要参数）
//   → 报错 → 永远探测失败 → startRagService 直接 return false → **从不 spawn**。
//   且 PowerShell 7 不在 pi 进程的 PATH 里 → 必须用绝对路径。
const PWSH_ABS = "C:\\Program Files\\PowerShell\\7\\pwsh.exe";
const WINPS_ABS =
  "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe";

/** 候选 shell（有序）：显式覆盖 > pwsh 绝对路径 > 裸名 > WinPS 绝对路径 > 裸名 */
export function shellCandidates(): string[] {
  const override = process.env.RAG_SHELL;
  return [
    ...(override ? [override] : []),
    PWSH_ABS,
    "pwsh",
    WINPS_ABS,
    "powershell",
  ];
}

/** 探活参数：`-Command exit 0` 对 pwsh 7 与 WinPS 5.1 通吃（绝不用 `-v`） */
export function shellProbeArgs(): string[] {
  return ["-NoProfile", "-NoLogo", "-Command", "exit 0"];
}

/** 启动参数：-File 指向唯一配置源脚本 */
export function shellStartArgs(scriptPath: string): string[] {
  return [
    "-NoProfile",
    "-NoLogo",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    scriptPath,
  ];
}

// 冷启动（torch + 模型加载）典型 40~90s；预算给到 120s 以保证首次调用即成功。
// 等待期间通过 onProgress 上报进度（避免「静默卡住」的错觉）。
// （可被 AbortSignal 提前取消；可用 RAG_START_MAX_RETRIES / RAG_START_DELAY_MS 覆盖）
/**
 * 「找不到可用 shell」的错误文案（纯函数 → 可测）。
 * 事故：旧版在模板串里插值 `${RAG_SHELL}`，但该标识符重构后已不存在 →
 *   恰在需要这条提示时抛 ReferenceError，把友好提示吃掉。
 * 现改为「列出真实尝试过的候选」，既不引用未声明标识符，排查信息也更多。
 */
export function noShellMessage(): string {
  return (
    "[ERROR] 未找到可用 shell，无法自动启动 RAG。" +
    `已尝试: ${shellCandidates().join(", ")}. ` +
    `请安装 PowerShell 7、或用 RAG_SHELL 指定可用的 shell，或手动运行 ${RAG_START_SCRIPT}`
  );
}

export const START_MAX_RETRIES = Number(process.env.RAG_START_MAX_RETRIES) || 120;
export const START_DELAY_MS = Number(process.env.RAG_START_DELAY_MS) || 1000;
export const START_BUDGET_SEC = (START_MAX_RETRIES * START_DELAY_MS) / 1000;
// 进度上报节流：每 N 秒提示一次（避免刷屏）
export const PROGRESS_EVERY_SEC = Number(process.env.RAG_PROGRESS_EVERY_SEC) || 5;

/**
 * 冷启动进度提示文案（纯函数，可测）。
 * 不含「超时/失败」字样 —— 等待期间不该让用户以为已经废了。
 */
export function progressMessage(elapsedSec: number): string {
  return `正在启动 RAG 服务... 已等待 ${elapsedSec}s（冷启动典型 40~90s，请稍候）`;
}
// spawn 后判定「已拉起」的宽限期（ms）：宽限期内既未 connect 成功也未 error/exit → 视为已拉起
const SPAWN_GRACE_MS = Number(process.env.RAG_SPAWN_GRACE_MS) || 3000;

// 检查端口是否被占用
async function isPortInUse(port: number): Promise<boolean> {
  const net = await import("net");
  return new Promise((resolve) => {
    const client = new net.Socket();
    client.setTimeout(1000);
    client.on("connect", () => {
      client.destroy();
      resolve(true);
    });
    client.on("error", () => resolve(false));
    client.connect(port, "127.0.0.1");
  });
}

// 前置探测：shell 是否可用（避免 spawn 静默失败后仍傻等 360s）
export async function probeShell(shell?: string): Promise<string | null> {
  const { execFile } = await import("child_process");
  const candidates = shell ? [shell] : shellCandidates();
  for (const s of candidates) {
    try {
      await new Promise<void>((resolve, reject) => {
        const p = execFile(s, shellProbeArgs(), { timeout: 5000 }, (err) =>
          err ? reject(err) : resolve()
        );
        p.unref?.();
      });
      return s;
    } catch {
      continue;
    }
  }
  return null;
}

// 启动 RAG 服务（拉起唯一配置源脚本；spawn error 纳入结果，不再静默返回 true）
export async function startRagService(): Promise<boolean> {
  if (!fs.existsSync(RAG_START_SCRIPT)) {
    console.warn(`[WARN] 找不到启动脚本: ${RAG_START_SCRIPT}`);
    return false;
  }

  // 前置探测：无可用 shell 立即 fail（避免未来换机没装 pwsh 又卡）
  const shell = await probeShell();
  if (!shell) {
    console.error(noShellMessage());
    return false;
  }

  // 只记录 spawn 行（诊断用）。**子进程自身的输出不在这里** ——
  // 服务自己落盘到 storage/rag.log（实测可靠），无需 node 侧捕获。
  const logPath = path.join(RAG_HOME, "logs", "extension_start.log");
  const logLine = (msg: string) => {
    console.log(msg);
    try {
      fs.mkdirSync(path.dirname(logPath), { recursive: true });
      fs.appendFileSync(logPath, `${msg}\n`);
    } catch {
      // 日志不可写不致命
    }
  };
  logLine(
    `[${new Date().toISOString()}] spawn: ${shell} ${shellStartArgs(RAG_START_SCRIPT).join(" ")}`
  );

  try {
    const { spawn } = await import("child_process");
    const child = spawn(shell, shellStartArgs(RAG_START_SCRIPT), {
      cwd: RAG_HOME,
      // ⚠️ 不要用 detached + fd-stdio 组合：2026-11-03 实测该组合下 pwsh 会**立刻以
      //    code=0 退出**（服务根本没起来，且零输出）。stdio:"ignore" + 非 detached
      //    实测可靠（python 长期存活）。诊断输出看 storage/rag.log。
      stdio: "ignore",
    });
    // unref：pi 退出时不必等待服务（服务生命周期由 idle 看门狗自管）
    child.unref();

    return await new Promise<boolean>((resolve) => {
      let settled = false;
      const finish = (ok: boolean, why: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(grace);
        ok
          ? logLine(`[INFO] RAG 服务已启动 (PID: ${child.pid}) ${why}`)
          : logLine(`[ERROR] RAG 启动失败: ${why}（详见 ${logPath}）`);
        resolve(ok);
      };

      child.on("error", (err) =>
        finish(false, `spawn error: ${err.code} ${err.message}`)
      );
      // 宽限期：子进程立刻非 0 退出 → 失败；宽限期到仍未退出且未 connect 成功 → 视为已拉起（交给 waitForService 判就绪）
      const grace = setTimeout(() => finish(true, "grace elapsed"), SPAWN_GRACE_MS);
      child.on("exit", (code) =>
        finish(code === 0, `child exit code=${code} in grace window`)
      );
    });
  } catch (err) {
    console.error(`[ERROR] 启动 RAG 服务失败:`, err);
    return false;
  }
}

// 等待服务就绪（轮询 /health）；预算可配 + 可被 signal 提前取消 + 进度上报
export async function waitForService(
  maxRetries: number = START_MAX_RETRIES,
  delayMs: number = START_DELAY_MS,
  signal?: AbortSignal,
  onProgress?: (elapsedSec: number) => void
): Promise<boolean> {
  const progressEvery = Math.max(1, Math.round((PROGRESS_EVERY_SEC * 1000) / delayMs));
  for (let i = 0; i < maxRetries; i++) {
    if (signal?.aborted) {
      console.log(`[INFO] waitForService 被中断（第 ${i + 1} 轮前）`);
      return false;
    }
    // 每 PROGRESS_EVERY_SEC 秒上报一次已等待秒数
    if (onProgress && i > 0 && i % progressEvery === 0) {
      onProgress(Math.round((i * delayMs) / 1000));
    }
    const inUse = await isPortInUse(RAG_PORT);
    if (inUse) {
      try {
        const resp = await fetch(`${RAG_API_BASE}/health`, {
          signal: AbortSignal.timeout(2000),
        });
        if (resp.ok) {
          console.log(`[OK] RAG 服务已就绪 (~${i + 1}s)`);
          return true;
        }
      } catch {
        // 端口占用但 API 未就绪，继续等待
      }
    }
    // 可中断 sleep：abort 时立即结束等待，不再傻等到预算耗尽
    await new Promise<void>((resolve) => {
      const t = setTimeout(resolve, delayMs);
      const onAbort = () => {
        clearTimeout(t);
        resolve();
      };
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }
  console.warn(`[WARN] 服务启动超时（预算 ${maxRetries}×${delayMs}ms）`);
  return false;
}

async function ragFetch(path: string, options?: RequestInit): Promise<Response> {
  const response = await fetch(`${RAG_API_BASE}${path}`, options);
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(errText);
  }
  return response;
}

// 软约束：服务没起就自动拉起，再发请求；透传 signal 使等待可被中断
export async function ragFetchWithAutoStart(
  path: string,
  options?: RequestInit,
  signal?: AbortSignal,
  onProgress?: (elapsedSec: number) => void
): Promise<Response> {
  const inUse = await isPortInUse(RAG_PORT);
  if (!inUse) {
    console.log(`[INFO] RAG 服务未运行，正在启动...`);
    onProgress?.(0);
    const started = await startRagService();
    if (!started) {
      throw new Error(
        `无法启动 RAG 服务（缺 ${RAG_START_SCRIPT} 或无可用 shell，详见日志）` +
          `。请手动运行：pwsh -File ${RAG_START_SCRIPT}`
      );
    }
    const ready = await waitForService(
      START_MAX_RETRIES,
      START_DELAY_MS,
      signal,
      onProgress
    );
    if (!ready) {
      // 预算耗尽：不再后台二次 spawn（避免重复拉起竞争），提示手动常驻
      throw new Error(
        `RAG 服务冷启动超时（超过 ${START_BUDGET_SEC}s 未就绪）` +
          `。请手动启动：pwsh -File ${RAG_START_SCRIPT}；或设 RAG_IDLE_TIMEOUT_SEC=0 常驻。` +
          (signal?.aborted ? "（本次等待已被中断）" : "")
      );
    }
  }
  return ragFetch(path, options);
}

const CONN_ERR_HINT = `请确认启动脚本存在: ${RAG_START_SCRIPT}`;

export default function (pi: ExtensionAPI) {
  // ========== Tool: search_knowledge_base ==========
  pi.registerTool({
    name: "search_knowledge_base",
    label: "Search Knowledge Base",
    description:
      "搜索本地知识库，从文档中检索相关信息并生成回答。" +
      "当用户询问关于文档内容、员工信息、技术规范、项目资料等问题时使用此工具。" +
      "支持自然语言查询，返回原始检索片段（不含 LLM 生成答案），需由模型自行综合成回答并注明来源。",
    promptSnippet: "从本地知识库文档中检索信息并生成回答",
    promptGuidelines: [
      "Use search_knowledge_base when the user asks questions about stored documents, employee info, tech specs, or project knowledge.",
    ],
    parameters: Type.Object({
      query: Type.String({
        description: "搜索问题或关键词（自然语言）",
      }),
      top_k: Type.Optional(
        Type.Number({
          description: "返回的最大结果数，默认 5",
          minimum: 1,
          maximum: 20,
        })
      ),
    }),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      const top_k = params.top_k ?? 5;

      onUpdate?.({
        content: [{ type: "text", text: `正在搜索: "${params.query}"...` }],
      });

      try {
        const resp = await ragFetchWithAutoStart(
          "/api/search_raw",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: params.query, top_k }),
            signal,
          },
          signal,
          (sec) => onUpdate?.({ content: [{ type: "text", text: progressMessage(sec) }] })
        );

        const data = await resp.json();

        // 格式化检索片段（答案由 pi 模型自行综合）
        let result = `**检索片段（请基于以下内容回答，并注明来源）**:\n\n`;
        for (const src of data.sources || []) {
          result += `- [${src.source}] (相似度: ${src.score})\n`;
          result += `  ${src.content.substring(0, 300)}\n`;
        }
        if (!data.sources || data.sources.length === 0) {
          result += "（知识库无相关片段）\n";
        }

        return {
          content: [{ type: "text", text: result }],
          details: { result: data },
        };
      } catch (err: any) {
        return {
          content: [
            {
              type: "text",
              text: `无法连接到 RAG 服务 (${RAG_API_BASE})。${CONN_ERR_HINT}\n错误: ${err.message}`,
            },
          ],
          isError: true,
        };
      }
    },
  });

  // ========== Tool: add_document_to_kb ==========
  pi.registerTool({
    name: "add_document_to_kb",
    label: "Add Document to KB",
    description:
      "添加文档到本地知识库。支持 PDF/TXT/MD/DOCX/CSV/XLSX/JSON 等格式。" +
      "添加后文档会被向量化并存储，可用于后续搜索。",
    promptSnippet: "将文件添加到 RAG 知识库",
    promptGuidelines: [
      "Use add_document_to_kb when the user wants to add a file to the knowledge base for future searching.",
    ],
    parameters: Type.Object({
      file_path: Type.String({
        description: "文档的完整路径（绝对路径）",
      }),
    }),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      onUpdate?.({
        content: [{ type: "text", text: `正在添加文档: ${params.file_path}...` }],
      });

      try {
        const resp = await ragFetchWithAutoStart(
          "/api/upload",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_path: params.file_path }),
            signal,
          },
          signal,
          (sec) => onUpdate?.({ content: [{ type: "text", text: progressMessage(sec) }] })
        );

        const data = await resp.json();

        if (data.success || data.document_id) {
          return {
            content: [
              {
                type: "text",
                text: `✅ 文档已添加: ${params.file_path}`,
              },
            ],
          };
        } else {
          return {
            content: [
              {
                type: "text",
                text: `❌ 添加失败: ${params.file_path}`,
              },
            ],
            isError: true,
          };
        }
      } catch (err: any) {
        return {
          content: [
            {
              type: "text",
              text: `无法连接到 RAG 服务。${CONN_ERR_HINT}\n错误: ${err.message}`,
            },
          ],
          isError: true,
        };
      }
    },
  });

  // ========== Tool: list_knowledge_base ==========
  pi.registerTool({
    name: "list_knowledge_base",
    label: "List Knowledge Base",
    description: "列出知识库中所有已入库的文档及其统计信息。",
    promptSnippet: "查看知识库中已入库的文档列表",
    promptGuidelines: [
      "Use list_knowledge_base to see what documents are available in the knowledge base.",
    ],
    parameters: Type.Object({}),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      try {
        const resp = await ragFetchWithAutoStart(
          "/api/documents",
          undefined,
          signal,
          (sec) => onUpdate?.({ content: [{ type: "text", text: progressMessage(sec) }] })
        );
        const data = await resp.json();

        let result = `**知识库统计**:\n`;
        result += `- 总文档块数: ${data.stats?.total_documents ?? "N/A"}\n`;
        result += `- 存储路径: ${data.stats?.persist_dir ?? "N/A"}\n\n`;
        result += `**已入库文档**:\n`;

        for (const doc of data.documents || []) {
          result += `- [${doc.source}]\n`;
        }

        if ((data.documents || []).length === 0) {
          result += "  (知识库为空)";
        }

        return {
          content: [{ type: "text", text: result }],
        };
      } catch (err: any) {
        return {
          content: [
            {
              type: "text",
              text: `无法连接到 RAG 服务。${CONN_ERR_HINT}\n错误: ${err.message}`,
            },
          ],
          isError: true,
        };
      }
    },
  });

  // ========== Tool: rebuild_knowledge_base ==========
  pi.registerTool({
    name: "rebuild_knowledge_base",
    label: "Rebuild Knowledge Base",
    description:
      "重建知识库：删除所有已有数据，从 documents 目录重新加载所有文档。" +
      "⚠️ 此操作会清除所有已入库的文档！",
    promptSnippet: "重建知识库（删除所有数据并重新加载）",
    promptGuidelines: [
      "Use rebuild_knowledge_base only when the user explicitly requests to rebuild the knowledge base. This is a destructive operation.",
    ],
    parameters: Type.Object({}),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      onUpdate?.({
        content: [{ type: "text", text: "正在重建知识库..." }],
      });

      try {
        const resp = await ragFetchWithAutoStart(
          "/api/rebuild",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
            signal,
          },
          signal,
          (sec) => onUpdate?.({ content: [{ type: "text", text: progressMessage(sec) }] })
        );

        const data = await resp.json();
        return {
          content: [
            {
              type: "text",
              text: `✅ 知识库重建完成，加载了 ${data.documents_loaded} 个文档块`,
            },
          ],
        };
      } catch (err: any) {
        return {
          content: [{ type: "text", text: `重建失败: ${err.message}` }],
          isError: true,
        };
      }
    },
  });

}
