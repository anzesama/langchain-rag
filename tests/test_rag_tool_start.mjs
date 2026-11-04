/**
 * pi_rag_tool 启动预算 / 进度提示 测试（TDD）
 *
 * 运行：node --test tests/test_rag_tool_start.mjs
 *
 * 背景：冷启动（torch + 模型加载）典型 40~90s。
 *   旧版预算被收紧到 30s → 首次调用必然超时失败。
 *   本测试锁定「预算 ≥ 120s」+ 进度提示文案，防止回归。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  START_BUDGET_SEC,
  progressMessage,
  PROGRESS_EVERY_SEC,
} from "../rag_extension/pi_rag_tool.ts";

test("START_BUDGET_SEC 必须 ≥ 120s（冷启动 40~90s，防止再次收紧到 30s）", () => {
  assert.ok(
    START_BUDGET_SEC >= 120,
    `预算仅 ${START_BUDGET_SEC}s，短于冷启动时间，首次调用会必然失败`
  );
});

test("progressMessage 包含已等待秒数", () => {
  const m = progressMessage(45);
  assert.match(m, /45s/);
  assert.match(m, /启动/);
});

test("progressMessage 在等待初期不出现超时/失败字样", () => {
  assert.ok(!/超时|失败|错误/.test(progressMessage(0)));
  assert.ok(!/超时|失败|错误/.test(progressMessage(60)));
});

test("PROGRESS_EVERY_SEC 是合理正整数（避免刷屏）", () => {
  assert.ok(Number.isInteger(PROGRESS_EVERY_SEC));
  assert.ok(PROGRESS_EVERY_SEC >= 2 && PROGRESS_EVERY_SEC <= 15);
});
