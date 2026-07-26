/**
 * pi Extension — RAG 知识库工具
 * 
 * 将 RAG 知识库封装为 pi Agent 可调用的自定义 Tool。
 * 通过 HTTP API 调用本地运行的 RAG 服务。
 * 
 * 安装方式：
 *   1. 确保 RAG 服务正在运行: python rag_server.py
 *   2. 复制此文件到: C:/Users/Administrator/.pi/agent/extensions/rag_tool.ts
 *   3. 在 pi 中执行 /reload 加载扩展
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "fs";
import * as path from "path";

const RAG_API_BASE = "http://localhost:8765";
const RAG_SERVER_SCRIPT = path.join(__dirname, "..", "rag_server.py");

// 检查端口是否被占用
function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const net = require("net");
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

// 启动 RAG 服务
async function startRagService(): Promise<boolean> {
  if (!fs.existsSync(RAG_SERVER_SCRIPT)) {
    console.warn(`[WARN] 找不到服务器脚本: ${RAG_SERVER_SCRIPT}`);
    return false;
  }

  try {
    const { spawn } = await import("child_process");
    const pythonPath = process.env.PYTHON_PATH || "python";
    
    const child = spawn(pythonPath, [RAG_SERVER_SCRIPT], {
      cwd: path.join(__dirname, ".."),
      stdio: "ignore",
      detached: true,
    });

    child.unref(); // 不等待子进程结束
    console.log(`[INFO] RAG 服务已启动 (PID: ${child.pid})`);
    return true;
  } catch (err) {
    console.error(`[ERROR] 启动 RAG 服务失败:`, err);
    return false;
  }
}

// 等待服务就绪
async function waitForService(maxRetries: number = 10, delayMs: number = 1000): Promise<boolean> {
  for (let i = 0; i < maxRetries; i++) {
    const inUse = await isPortInUse(8765);
    if (inUse) {
      // 尝试连接 API
      try {
        const resp = await fetch(`${RAG_API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
        if (resp.ok) {
          console.log(`[OK] RAG 服务已就绪 (${i + 1}秒)`);
          return true;
        }
      } catch {
        // 端口占用但 API 未就绪，继续等待
      }
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  console.warn(`[WARN] 服务启动超时 (${maxRetries}秒)`);
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

async function ragFetchWithAutoStart(path: string, options?: RequestInit): Promise<Response> {
  // 检查服务是否运行
  const inUse = await isPortInUse(8765);
  if (!inUse) {
    console.log(`[INFO] RAG 服务未运行，正在启动...`);
    const started = await startRagService();
    if (!started) {
      throw new Error("无法启动 RAG 服务");
    }
    // 等待服务就绪
    const ready = await waitForService();
    if (!ready) {
      throw new Error("RAG 服务启动超时");
    }
  }
  return ragFetch(path, options);
}

export default function (pi: ExtensionAPI) {
  // ========== Tool: search_knowledge_base ==========
  pi.registerTool({
    name: "search_knowledge_base",
    label: "Search Knowledge Base",
    description:
      "搜索本地知识库，从文档中检索相关信息并生成回答。" +
      "当用户询问关于文档内容、员工信息、技术规范、项目资料等问题时使用此工具。" +
      "支持自然语言查询，返回 LLM 生成的回答和相关文档来源。",
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
        const resp = await ragFetchWithAutoStart("/api/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: params.query, top_k }),
          signal,
        });

        if (!resp.ok) {
          const errText = await resp.text();
          return {
            content: [{ type: "text", text: `搜索失败: ${errText}` }],
            isError: true,
          };
        }

        const data = await resp.json();
        
        // 格式化结果
        let result = `**回答**: ${data.answer}\n\n`;
        result += `**来源**:\n`;
        for (const src of data.sources || []) {
          result += `- [${src.source}] (相似度: ${src.score})\n`;
          result += `  ${src.content.substring(0, 150)}\n`;
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
              text: `无法连接到 RAG 服务 (${RAG_API_BASE})。请确保服务正在运行: python rag_server.py\n错误: ${err.message}`,
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
        const resp = await ragFetchWithAutoStart("/api/add_document", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_path: params.file_path }),
          signal,
        });

        const data = await resp.json();
        
        if (data.success) {
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
              text: `无法连接到 RAG 服务。错误: ${err.message}`,
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
    description:
      "列出知识库中所有已入库的文档及其统计信息。",
    promptSnippet: "查看知识库中已入库的文档列表",
    promptGuidelines: [
      "Use list_knowledge_base to see what documents are available in the knowledge base.",
    ],
    parameters: Type.Object({}),
    async execute(toolCallId, params, signal, onUpdate, ctx) {
      try {
        const resp = await ragFetchWithAutoStart("/api/documents");
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
            { type: "text", text: `无法连接到 RAG 服务。错误: ${err.message}` },
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
        const resp = await ragFetchWithAutoStart("/api/rebuild", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
          signal,
        });

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
          content: [
            { type: "text", text: `重建失败: ${err.message}` },
          ],
          isError: true,
        };
      }
    },
  });
}
