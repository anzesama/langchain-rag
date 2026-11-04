/**
 * rag-autoreload.ts — RAG 扩展「源码更新提醒」
 *
 * ⚠️ 事故记录（2026-11-03）：
 *   旧版用 `fs.watch` + `tool_call` 自动触发 `ctx.reload()`。当 LLM 正在用 edit 工具
 *   修改被监视的源文件时，watch 回调在 **tool 执行中途** 调用 reload →
 *   pi 进程崩溃，且源文件被截断为 **0 字节**（写一半被打断）。
 *   pi 官方文档亦明确：`ctx.reload()` 是**终止操作**，工具执行期间不可调用。
 *
 * 现行策略（安全）：
 *   1. 提供 `/rag-reload` 命令 —— 由用户在最安全的时刻主动触发；
 *   2. 仅在 `session_start`（安全点）检查一次源码/部署的 mtime 差异，
 *      有差异就 **提醒**（notify），**绝不自动 reload**。
 */
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";

const RAG_HOME = process.env.RAG_HOME || "D:/class/project-config/langchain-rag";

/** 源码位置（开发时改这里） */
export const SRC_EXT = join(RAG_HOME, "rag_extension", "pi_rag_tool.ts");
/** 部署副本位置（pi 实际加载这里） */
export const DST_EXT = join(
  process.env.USERPROFILE || "",
  ".pi",
  "agent",
  "extensions",
  "pi_rag_tool.ts"
);

/**
 * 纯函数：部署副本是否落后于源码（可测）。
 * 任一文件缺失 → 视为「无法判定」，返回 false（不打扰用户）。
 * 容差 1ms：避免同一次写入产生的时间戳抖动导致误报。
 */
export function needsReload(
  srcMtime: number | null,
  dstMtime: number | null
): boolean {
  if (srcMtime === null || dstMtime === null) return false;
  return srcMtime > dstMtime + 1;
}

function mtimeOf(p: string): number | null {
  return existsSync(p) ? statSync(p).mtimeMs : null;
}

export default function (pi: ExtensionAPI) {
  // 手动重载入口（安全）：由用户主动执行
  pi.registerCommand("rag-reload", {
    description: "重载 pi 扩展（安全：由用户主动触发，不会在工具执行中打断）",
    handler: async (_args, ctx) => {
      await ctx.reload();
      return; // reload 是终止操作，之后不得再引用旧状态
    },
  });

  // 仅在会话启动（安全点）检查一次：有差异 → 提醒，绝不自动 reload
  pi.on("session_start", async (_event, ctx) => {
    try {
      if (needsReload(mtimeOf(SRC_EXT), mtimeOf(DST_EXT))) {
        ctx.ui?.notify?.(
          "RAG 扩展源码比部署副本新：请先运行 scripts/install_rag_extension.ps1，再执行 /rag-reload",
          "info"
        );
      }
    } catch {
      // 提醒失败不影响主功能
    }
  });
}
