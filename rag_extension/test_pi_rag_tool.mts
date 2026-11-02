/**
 * pi_rag_tool 快速失败测试
 *
 * 运行（node 24 原生 TS + node:test，零 npm 安装）:
 *   cd D:/class/project-config/langchain-rag
 *   node --test rag_extension/test_pi_rag_tool.mts
 *
 * 依赖：typebox 经 node_modules/typebox symlink 解析（symlink 指向
 *   C:/Users/Administrator/AppData/Roaming/npm/node_modules/@mariozechner/pi-coding-agent/node_modules/typebox）
 *   该 symlink 在 node_modules/ 内（被 .gitignore 忽略），生产 pi 用 jiti virtualModules 不受影响。
 *
 * 覆盖设计文档 7 条 TDD：
 *  1. startRagService: 缺启动脚本 → false（快速失败，不 spawn）
 *  2. probeShell: 不可用 shell → null（前置探测失败）
 *  3. waitForService: 预算内 /health 200 → true
 *  4. waitForService: signal 提前 abort → 立即 false（可中断，不傻等）
 *  5. waitForService: 永不 200 且预算耗尽 → false
 *  6. ragFetchWithAutoStart: 未起且 !ready → 抛「冷启动超时」
 *  7. ragFetchWithAutoStart: 服务已在跑(ready) → 透传 ragFetch
 */
import { test, before } from "node:test";
import assert from "node:assert/strict";
import * as net from "node:net";

// ---- 测试前置：RAG 常量按测试预期（独立端口 18765，避免打到真实 8765） ----
process.env.RAG_PORT = "18765";
process.env.RAG_API_BASE = "http://localhost:18765";
process.env.RAG_START_MAX_RETRIES = "3";
process.env.RAG_START_DELAY_MS = "100";
process.env.RAG_SPAWN_GRACE_MS = "120";
// RAG_HOME 指向不存在 → startRagService 的 existsSync 直接 false（不真正 spawn）
process.env.RAG_HOME = "/tmp/rag-test-home-does-not-exist";

// 直接 import 被测模块（node 24 strip-types；typebox 经 symlink 解析）
const ext = await import("./pi_rag_tool.ts");
const helper: any = ext; // 含 default + named exports

// ---- 工具：stub 全局 fetch ----
function stubFetch(handler: (url: string) => Response | Promise<Response>) {
  const orig = globalThis.fetch;
  globalThis.fetch = ((input: any) =>
    Promise.resolve(handler(String(input)))) as typeof fetch;
  return () => {
    globalThis.fetch = orig;
  };
}
const okResp = () =>
  ({ ok: true, json: async () => ({ answer: "A", sources: [] }) }) as Response;
const badResp = () =>
  ({
    ok: false,
    status: 500,
    json: async () => ({}),
    text: async () => "500",
  }) as unknown as Response;

// 占住 18765（让 isPortInUse=true），返回 server（测试结束 close）
function occupyPort(): Promise<net.Server> {
  return new Promise((res, rej) => {
    const s = net.createServer(() => {});
    s.on("error", rej);
    s.listen(18765, () => res(s));
  });
}

test("1. startRagService: 缺启动脚本 → false（快速失败）", async () => {
  const r = await helper.startRagService();
  assert.equal(r, false, "脚本不存在应返回 false（不 spawn、不傻等）");
});

test("2. probeShell: 不可用 shell → null", async () => {
  const r = await helper.probeShell("definitely-not-a-real-shell-xyz");
  assert.equal(r, null, "不存在的 shell 应返回 null");
});

test("3. waitForService: 预算内 /health 200 → true", async () => {
  const server = await occupyPort();
  const unstub = stubFetch((url) =>
    url.includes("/health") ? okResp() : badResp()
  );
  try {
    const r = await helper.waitForService(3, 100);
    assert.equal(r, true, "预算内 /health 200 应 true");
  } finally {
    unstub();
    server.close();
  }
});

test("4. waitForService: signal 提前 abort → 立即 false（可中断）", async () => {
  const ac = new AbortController();
  const t0 = Date.now();
  const p = helper.waitForService(1000, 500, ac.signal); // 预算 500s
  setTimeout(() => ac.abort(), 200); // 200ms 后中断
  const r = await p;
  const elapsed = Date.now() - t0;
  assert.equal(r, false, "abort 后应 false");
  assert.ok(
    elapsed < 4000,
    `应 abort 后立即结束（实际 ${elapsed}ms），而非傻等到 500s 预算`
  );
});

test("5. waitForService: 永不 200 且预算耗尽 → false", async () => {
  const unstub = stubFetch(() => badResp());
  try {
    const r = await helper.waitForService(3, 50);
    assert.equal(r, false, "预算耗尽未就绪 → false");
  } finally {
    unstub();
  }
});

test("6. ragFetchWithAutoStart: 未起且 !ready → 快速失败（不阻塞）", async () => {
  const unstub = stubFetch((url) =>
    url.includes("/health") ? badResp() : okResp()
  );
  try {
    const t0 = Date.now();
    await assert.rejects(
      () => helper.ragFetchWithAutoStart("/api/search", { method: "GET" }),
      (err: Error) => /无法启动 RAG 服务|冷启动较慢|未就绪|手动启动/.test(err.message)
    );
    const elapsed = Date.now() - t0;
    // 关键回归：必须在预算+宽限期内快速失败，绝不傻等到 30s/360s
    assert.ok(
      elapsed < 5000,
      `ragFetchWithAutoStart 应快速失败（实际 ${elapsed}ms），而非阻塞数十秒`
    );
  } finally {
    unstub();
  }
});

test("7. ragFetchWithAutoStart: 服务已在跑 → 透传 ragFetch", async () => {
  const server = await occupyPort(); // isPortInUse=true → 跳过 auto-start
  const unstub = stubFetch((url) => (url.includes("/api/echo") ? okResp() : badResp()));
  try {
    const resp = await helper.ragFetchWithAutoStart("/api/echo", {
      method: "GET",
    });
    assert.equal(resp.ok, true, "服务在跑时应透传成功响应");
  } finally {
    unstub();
    server.close();
  }
});

test("default export 可加载且为函数", () => {
  assert.equal(typeof ext.default, "function");
});

test("8. search_knowledge_base 请求 /api/search_raw（不再调 /api/search）", async () => {
  const server = await occupyPort(); // isPortInUse=true → 跳过 auto-start
  let capturedUrl = "";
  const restore = stubFetch((url) => {
    capturedUrl = url;
    return {
      ok: true,
      json: async () => ({
        query: "q",
        sources: [{ source: "a.md", content: "片段内容", score: 0.9 }],
      }),
    } as Response;
  });
  try {
    const tools: any[] = [];
    const fakePi = {
      registerTool: (t: any) => tools.push(t),
      registerCommand: () => {},
      on: () => {},
      sendUserMessage: () => {},
    };
    (ext.default as any)(fakePi);
    const searchTool = tools.find((t) => t.name === "search_knowledge_base");
    assert.ok(searchTool, "search_knowledge_base 应已注册");

    const out = await searchTool.execute(
      "id",
      { query: "q", top_k: 3 },
      undefined,
      undefined,
      {}
    );
    assert.match(
      capturedUrl,
      /\/api\/search_raw$/,
      `应请求 /api/search_raw，实际 ${capturedUrl}`
    );
    const text = out.content[0].text;
    assert.doesNotMatch(text, /\*\*回答\*\*/, "输出不应再含 **回答**");
    assert.match(text, /检索片段/, "输出应含检索片段标题");
  } finally {
    restore();
    server.close();
  }
});
