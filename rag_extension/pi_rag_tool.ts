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
// 导入热重载守护（注册 /rag-reload 命令）
import rag_autoreload from "./rag_autoreload.ts";

const RAG_API_BASE = process.env.RAG_API_BASE || "http://localhost:8765";
const RAG_PORT =
  Number(process.env.RAG_PORT) || 8765;
const RAG_HOME =
  process.env.RAG_HOME || "D:/class/project-config/langchain-rag";
const RAG_START_SCRIPT = path.join(RAG_HOME, "scripts", "start_rag_server.ps1");
// shell 可覆盖（测试用）：默认 pwsh，探测失败回退 powershell 5.1
const RAG_SHELL = process.env.RAG_SHELL || "pwsh";

// 冷启动（torch + 模型加载）典型 40~90s；轮询预算收紧到 30s，避免死等阻塞 pi 主循环
// （可被 AbortSignal 提前取消；可用 RAG_START_MAX_RETRIES 覆盖）
const START_MAX_RETRIES = Number(process.env.RAG_START_MAX_RETRIES) || 30;
const START_DELAY_MS = Number(process.env.RAG_START_DELAY_MS) || 1000;
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
  const candidates = shell ? [shell] : [RAG_SHELL, "powershell"];
  for (const s of candidates) {
    try {
      await new Promise<void>((resolve, reject) => {
        const p = execFile(s, ["-v"], { timeout: 3000 }, (err) =>
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
    console.error(
      `[ERROR] 未找到可用 shell（${RAG_SHELL}/powershell），无法自动启动 RAG。请安装 PowerShell 7 或手动运行 ${RAG_START_SCRIPT}`
    );
    return false;
  }

  try {
    const { spawn } = await import("child_process");
    const child = spawn(
      shell,
      ["-ExecutionPolicy", "Bypass", "-File", RAG_START_SCRIPT],
      {
        cwd: RAG_HOME,
        stdio: "ignore",
        // 不再 detached/unref：需被父进程观察 error/exit 以快速失败；
        // 服务实际生命周期由 start_rag_server.ps1 的 idle 退出机制自管。
      }
    );

    return await new Promise<boolean>((resolve) => {
      let settled = false;
      const finish = (ok: boolean, why: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(grace);
        ok
          ? console.log(`[INFO] RAG 服务已启动 (PID: ${child.pid}) ${why}`)
          : console.error(`[ERROR] RAG 启动失败: ${why}（见上方日志）`);
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

// 等待服务就绪（轮询 /health）；预算 30s 可配 + 可被 signal 提前取消
export async function waitForService(
  maxRetries: number = START_MAX_RETRIES,
  delayMs: number = START_DELAY_MS,
  signal?: AbortSignal
): Promise<boolean> {
  for (let i = 0; i < maxRetries; i++) {
    if (signal?.aborted) {
      console.log(`[INFO] waitForService 被中断（第 ${i + 1} 轮前）`);
      return false;
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
  signal?: AbortSignal
): Promise<Response> {
  const inUse = await isPortInUse(RAG_PORT);
  if (!inUse) {
    console.log(`[INFO] RAG 服务未运行，正在启动...`);
    const started = await startRagService();
    if (!started) {
      throw new Error(
        `无法启动 RAG 服务（缺 ${RAG_START_SCRIPT} 或无可用 shell，详见日志）` +
          `。请手动运行：pwsh -File ${RAG_START_SCRIPT}`
      );
    }
    const ready = await waitForService(START_MAX_RETRIES, START_DELAY_MS, signal);
    if (!ready) {
      // 快速失败：不再后台二次 spawn（避免重复拉起竞争），直接提示冷启动中/请手动常驻
      throw new Error(
        `RAG 服务冷启动较慢（超过 ${START_MAX_RETRIES * START_DELAY_MS / 1000}s 未就绪）` +
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
          signal
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
          signal
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
        const resp = await ragFetchWithAutoStart("/api/documents", undefined, signal);
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
          signal
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

  // 注册 /rag-reload 命令 + 热重载守护
  // （修复：此前只 import 未调用 → /rag-reload 命令未注册）
  rag_autoreload(pi);
}
