"""
RAG HTTP API 服务
独立运行，供 pi Agent 或其他外部工具通过 API 调用
"""
import sys
import os
from pathlib import Path

# 禁用 ChromaDB 遥测（避免阻塞）
os.environ["POSTHOG_OFF"] = "1"
os.environ["POSTHOG_JS_OFF"] = "1"

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict

from rag_config import RAG_SERVER_HOST, RAG_SERVER_PORT, logger
from rag_core.knowledge_base import KnowledgeBase

# ==================== FastAPI 应用 ====================
app = FastAPI(
    title="RAG Knowledge Base API",
    description="本地知识库检索增强生成服务",
    version="1.0.0"
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局知识库实例
_kb = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


# ==================== 请求/响应模型 ====================
class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5


class AddDocumentRequest(BaseModel):
    file_path: str


class RebuildRequest(BaseModel):
    pass


# ==================== API 路由 ====================
@app.get("/")
async def health_check():
    """健康检查"""
    kb = get_kb()
    stats = kb.get_stats()
    return {
        "status": "ok",
        "service": "RAG Knowledge Base",
        "version": "1.0.0",
        "stats": stats
    }


@app.post("/api/search")
def search(request: SearchRequest):
    """
    搜索知识库并生成回答（同步函数，uvicorn 自动放入线程池执行）
    """
    try:
        kb = get_kb()
        result = kb.search(request.query, top_k=request.top_k)
        return result
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add_document")
async def add_document(request: AddDocumentRequest):
    """
    添加文档到知识库
    
    POST /api/add_document
    {
        "file_path": "D:/path/to/document.pdf"
    }
    """
    try:
        kb = get_kb()
        success = kb.add_document(request.file_path)
        return {"success": success, "file": request.file_path}
    except Exception as e:
        logger.error(f"添加文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add_directory")
async def add_directory():
    """
    批量添加 documents 目录下所有文档
    
    POST /api/add_directory
    """
    try:
        kb = get_kb()
        count = kb.add_directory()
        return {"added_files": count}
    except Exception as e:
        logger.error(f"批量添加失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents")
async def list_documents():
    """
    列出所有已入库文档
    
    GET /api/documents
    """
    try:
        kb = get_kb()
        docs = kb.list_documents()
        stats = kb.get_stats()
        return {"documents": docs, "stats": stats}
    except Exception as e:
        logger.error(f"列出文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rebuild")
async def rebuild(request: RebuildRequest = None):
    """
    重建知识库（删除旧数据，从 documents 目录重新加载）
    
    POST /api/rebuild
    """
    try:
        kb = get_kb()
        count = kb.rebuild()
        return {"rebuilt": True, "documents_loaded": count}
    except Exception as e:
        logger.error(f"重建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 启动 ====================
def run_server():
    """启动 RAG HTTP 服务（uvicorn + h11 HTTP parser）"""
    import uvicorn
    
    logger.info("预加载 Embedding 模型...")
    try:
        kb = get_kb()
        # 触发 vector_store 初始化，预加载模型
        from rag_core.vector_store import VectorStoreManager
        vs = VectorStoreManager()
        # 执行一次空搜索以触发模型加载
        vs.search("preload", top_k=1)
        logger.info("Embedding 模型预加载完成")
    except Exception as e:
        logger.warning(f"Embedding 模型预加载失败（服务仍可运行）: {e}")
    
    logger.info(f"启动 RAG 服务: http://{RAG_SERVER_HOST}:{RAG_SERVER_PORT}")
    logger.info(f"API 文档: http://localhost:{RAG_SERVER_PORT}/docs")
    
    uvicorn.run(
        app,
        host=RAG_SERVER_HOST,
        port=RAG_SERVER_PORT,
        log_level="info",
        access_log=True,
        http="h11",
    )


if __name__ == "__main__":
    run_server()
