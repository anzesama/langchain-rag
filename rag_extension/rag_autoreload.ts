/**
 * rag-autoreload.ts — RAG 扩展热重载守护
 *
 * 功能：
 *   1. 注册 /rag-reload 命令（供扩展自己调用）
 *   2. 监测主扩展文件修改时间，变化时自动执行 reload
 *
 * 触发方式：
 *   - 手动：pi 中执行 /rag-reload
 *   - 自动：修改源文件 + install 后，下次 tool_call 自动检测并重载
 */
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, statSync, watch } from "node:fs";
import { join } from "node:path";

const MAIN_EXT = process.env.RAG_HOME
  ? join(process.env.RAG_HOME, "rag_extension", "pi_rag_tool.ts")
  : "D:/class/project-config/langchain-rag/rag_extension/pi_rag_tool.ts";

let lastMtime = -1; // -1 = 未初始化（首轮只记录基准，不触发）
let reloading = false;

/**
 * 纯函数：决定是否重载（可测）。
 * 首次（prevMtime<0）只记录基准，不触发 —— 避免扩展加载即自触发导致的重载循环。
 */
export function decideReload(
  prevMtime: number,
  mtime: number
): { next: number; reload: boolean } {
  if (prevMtime < 0) return { next: mtime, reload: false };
  if (mtime > prevMtime) return { next: mtime, reload: true };
  return { next: prevMtime, reload: false };
}

async function doReload(pi: ExtensionAPI): Promise<void> {
  if (reloading) return;
  reloading = true;
  try {
    console.log("[autoreload] 触发扩展重载...");
    // ctx.reload() 只能在 command handler 里调用，这里用 sendUserMessage 绕道
    pi.sendUserMessage("/rag-reload", { deliverAs: "followUp", triggerTurn: false });
  } finally {
    reloading = false;
  }
}

function checkAndSchedule(pi: ExtensionAPI) {
  if (!existsSync(MAIN_EXT)) return;
  const mtime = statSync(MAIN_EXT).mtimeMs;
  const d = decideReload(lastMtime, mtime);
  lastMtime = d.next;
  if (d.reload) {
    console.log(`[autoreload] ${MAIN_EXT} 已更新，调度重载...`);
    doReload(pi);
  }
}

export default function (pi: ExtensionAPI) {
  // 注册 /rag-reload 命令
  pi.registerCommand("rag-reload", {
    description: "重载 RAG pi 扩展（无需退出 pi）",
    handler: async (_args, ctx) => {
      await ctx.reload();
      ctx.ui.notify("RAG 扩展已重载", "info");
    },
  });

  // 会话启动时检查一次
  pi.on("session_start", () => checkAndSchedule(pi));

  // 每次工具调用前检查（最常见触发点）
  pi.on("tool_call", () => checkAndSchedule(pi));

  // 也监听文件系统变化（开发时连续改文件会多次触发）
  if (existsSync(MAIN_EXT)) {
    try {
      watch(MAIN_EXT, () => checkAndSchedule(pi));
    } catch (_) {
      // watch 失败不影响主功能
    }
  }
}
