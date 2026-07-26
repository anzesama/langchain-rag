"""
pi 扩展 — 将 RAG 知识库注册为 pi Agent 可调用的 Tool
"""
from typing import Optional
from pathlib import Path

# 延迟导入，避免非 pi 环境下出错
try:
    from rag_core.knowledge_base import KnowledgeBase
except ImportError:
    KnowledgeBase = None


_kb_instance: Optional[KnowledgeBase] = None


def _get_kb() -> KnowledgeBase:
    """获取知识库单例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance


def register_rag_tool(pi):
    """
    注册 RAG 搜索 Tool 到 pi Agent
    
    用法：将此文件放入 ~/.pi/agent/extensions/rag_tool.py
    然后 pi Agent 就可以自动调用 search_knowledge_base 工具
    
    Args:
        pi: pi ExtensionAPI 实例
    """
    if KnowledgeBase is None:
        print("警告: rag_core 未安装，跳过 RAG Tool 注册")
        return
    
    pi.registerTool({
        "name": "search_knowledge_base",
        "label": "Search Knowledge Base",
        "description": "搜索本地知识库，从文档中检索相关信息并生成回答。适合回答关于文档内容、技术规范、项目资料等问题。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的问题或关键词（自然语言）"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的最大结果数，默认 5",
                    "default": 5
                }
            },
            "required": ["query"]
        },
        "execute": lambda tool_call_id, params, signal, onUpdate, ctx: _search_knowledge_base_impl(params.get("query", ""), params.get("top_k", 5))
    })
    
    pi.registerTool({
        "name": "add_document_to_kb",
        "label": "Add Document to KB",
        "description": "添加文档到本地知识库。支持 PDF/TXT/MD/DOCX/CSV/XLSX/JSON 等格式。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文档的完整路径"
                }
            },
            "required": ["file_path"]
        },
        "execute": lambda tool_call_id, params, signal, onUpdate, ctx: _add_document_impl(params.get("file_path", ""))
    })
    
    pi.registerTool({
        "name": "list_knowledge_base",
        "label": "List Knowledge Base",
        "description": "列出知识库中所有已入库的文档。",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "execute": lambda tool_call_id, params, signal, onUpdate, ctx: _list_kb_impl()
    })


def _search_knowledge_base_impl(query: str, top_k: int = 5) -> dict:
    """搜索知识库的实现"""
    try:
        kb = _get_kb()
        result = kb.search(query, top_k=top_k)
        return result
    except Exception as e:
        return {"error": str(e)}


def _add_document_impl(file_path: str) -> dict:
    """添加文档的实现"""
    try:
        kb = _get_kb()
        success = kb.add_document(file_path)
        return {"success": success, "file": file_path}
    except Exception as e:
        return {"error": str(e)}


def _list_kb_impl() -> dict:
    """列出知识库的实现"""
    try:
        kb = _get_kb()
        docs = kb.list_documents()
        stats = kb.get_stats()
        return {"documents": docs, "stats": stats}
    except Exception as e:
        return {"error": str(e)}
