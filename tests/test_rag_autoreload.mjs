/**
 * rag_autoreload 测试（TDD）
 *
 * 事故背景（2026-11-03）：
 *   旧版用 `fs.watch` + `tool_call` 自动触发 `ctx.reload()`，
 *   在 tool 执行中被调用 → pi 进程崩溃 + 源文件被截断为 0 字节。
 *   pi 文档明确：reload 是「终止操作」，工具执行期间不可 reload。
 *
 * 现行策略：**只提醒，不自动 reload**（用户在安全时刻手动 /rag-reload）。
 *
 * 运行：node --test tests/test_rag_autoreload.mjs
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { needsReload } from "../rag_extension/rag_autoreload.ts";

test("源码比部署新 → 需要提醒", () => {
  assert.equal(needsReload(2000, 1000), true);
});

test("部署比源码新（已 install）→ 不提醒", () => {
  assert.equal(needsReload(1000, 2000), false);
});

test("时间戳几乎相同（<1ms 抖动）→ 不提醒", () => {
  assert.equal(needsReload(1000.5, 1000), false);
});

test("任一文件缺失 → 不打扰用户", () => {
  assert.equal(needsReload(null, 1000), false);
  assert.equal(needsReload(1000, null), false);
  assert.equal(needsReload(null, null), false);
});

test("回归防护：不得再有 decideReload（曾在 tool 执行中自动 reload → 崩溃）", async () => {
  const m = await import("../rag_extension/rag_autoreload.ts");
  assert.equal(
    m.decideReload,
    undefined,
    "decideReload 回归了！它会自动触发 ctx.reload()，必须保持移除状态"
  );
});

test("回归防护：不得再注册 tool_call / fs.watch 自动触发（源码级检查）", async () => {
  const { readFileSync } = await import("node:fs");
  const raw = readFileSync(
    new URL("../rag_extension/rag_autoreload.ts", import.meta.url),
    "utf8"
  );
  // 剥离注释后再检查 —— 注释里说明历史事故时会提到这些名字
  const src = raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
  assert.ok(!/fs\.watch|\.watch\(/.test(src), "不得使用 fs.watch 自动触发重载");
  assert.ok(
    !/on\(\s*["']tool_call["']/.test(src),
    "不得在 tool_call 事件里触发重载（会 crash pi）"
  );
});
