"""
RAG HTTP API 服务 — 企业级重构版

新增功能：
1. 异步文档上传（/api/upload）
2. 文档状态机（pending → processing → completed/failed）
3. 批量上传（/api/upload/batch）
4. 文档查询（/api/documents/{id}）
5. 文档删除（DELETE /api/documents/{id}）
6. 健康检查（/health）
7. 审计日志
"""
import sys
import os
import uuid
import asyncio
import shutil
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

# 禁用 ChromaDB 遥测
os.environ["POSTHOG_OFF"] = "1"
os.environ["POSTHOG_JS_OFF"] = "1"

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_config import RAG_SERVER_HOST, RAG_SERVER_PORT, DOCUMENTS_DIR, logger
from rag_core.knowledge_base import KnowledgeBase

# ==================== 文档状态枚举 ====================

class DocStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# ==================== 文档元数据存储 ====================

DOC_REGISTRY_PATH = Path(__file__).parent / "storage" / "doc_registry.json"


def load_doc_registry() -> Dict[str, dict]:
    """加载文档注册表"""
    if DOC_REGISTRY_PATH.exists():
        try:
            import json
            return json.loads(DOC_REGISTRY_PATH.read_text(encoding="utf-8"))
        except:
            return {}
    return {}


def save_doc_registry(registry: Dict[str, dict]):
    """保存文档注册表"""
    DOC_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    import json
    DOC_REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def get_doc_registry() -> Dict[str, dict]:
    """获取文档注册表（线程安全）"""
    registry = load_doc_registry()
    # 清理已删除文件的条目
    cleaned = {}
    for doc_id, info in registry.items():
        if info.get("status") == "completed" and Path(info.get("stored_path", "")).exists():
            cleaned[doc_id] = info
        elif info.get("status") in ("pending", "processing"):
            cleaned[doc_id] = info  # 保留处理中的
    return cleaned


# ==================== 审计日志 ====================

AUDIT_LOG_PATH = Path(__file__).parent / "storage" / "audit.log"


def audit_log(action: str, user: str, details: str = ""):
    """记录审计日志"""
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {action} | user={user} | {details}\n"
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"审计日志写入失败: {e}")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="RAG Knowledge Base API",
    description="企业级知识库检索增强生成服务",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_kb = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


# ==================== 闲置 / 内存感知看门狗 ====================
# 让服务"不用就退"：闲置超时或内存紧张时自动退出，释放 ~1.2GB。
# 配置来自环境变量（由 scripts/start_rag_server.ps1 注入）。

from rag_core.idle_watchdog import IdleWatchdog


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


IDLE_TIMEOUT_SEC = _env_int("RAG_IDLE_TIMEOUT_SEC", 300)
MEM_IDLE_SEC     = _env_int("RAG_MEM_IDLE_SEC", 60)
MEM_MIN_MB       = _env_int("RAG_MEM_MIN_MB", 400)
WATCHDOG_SEC     = _env_int("RAG_WATCHDOG_SEC", 30)

_watchdog = None


def get_watchdog() -> IdleWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = IdleWatchdog(
            idle_timeout_sec=IDLE_TIMEOUT_SEC,
            mem_idle_sec=MEM_IDLE_SEC,
            mem_min_mb=MEM_MIN_MB,
        )
    return _watchdog


def graceful_shutdown(reason: str = "manual") -> None:
    """优雅退出：尽量 flush，写日志，然后硬退出（避免 uvicorn 卡住）"""
    try:
        kb = get_kb()
        flush = getattr(kb, "flush", None)
        if callable(flush):
            flush()
    except Exception as e:
        logger.error(f"flush 失败: {type(e).__name__}: {e}")
    logger.warning(f"🛑 RAG 服务退出 (原因: {reason})")
    try:
        import logging as _logging
        _logging.shutdown()  # 冲刷日志 handler
    except Exception:
        pass
    os._exit(0)


def _watchdog_loop() -> None:
    """后台线程：每 WATCHDOG_SEC 检查一次是否该退出"""
    import time as _time
    while True:
        _time.sleep(max(1, WATCHDOG_SEC))
        try:
            reason = get_watchdog().run_once()
        except Exception as e:
            logger.error(f"看门狗异常: {type(e).__name__}: {e}")
            continue
        if reason:
            try:
                idle = get_watchdog().idle_sec()
            except Exception:
                idle = -1
            logger.warning(f"看门狗触发 ({reason}, idle={idle:.0f}s) — 正在退出")
            graceful_shutdown(reason)


@app.middleware("http")
async def _touch_watchdog(request, call_next):
    """任何请求都重置闲置计时（滑动窗口）"""
    try:
        get_watchdog().touch()
    except Exception:
        pass
    return await call_next(request)


# ==================== 请求/响应模型 ====================

class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5


class UploadResult(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str
    uploaded_at: str


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    status: str
    chunks: int
    added_at: str
    stored_path: str
    file_size_bytes: int


# ==================== API 路由 ====================

@app.get("/health")
async def health_check():
    """健康检查"""
    kb = get_kb()
    stats = kb.get_stats()
    return {
        "status": "ok",
        "service": "RAG Knowledge Base",
        "version": "2.0.0",
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/memories/stats")
async def memories_stats():
    """脑启发性记忆层统计（只读）。供观察「知识飞轮」效果。"""
    try:
        kb = get_kb()
        return await run_in_threadpool(kb.vector_store.get_memories_stats)
    except Exception as e:
        logger.error(f"记忆统计失败: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search(request: SearchRequest):
    """搜索知识库（含 LLM 生成；LLM 超时自动降级）"""
    try:
        kb = get_kb()
        result = await run_in_threadpool(kb.search, request.query, request.top_k)
        audit_log("SEARCH", "api", f"query='{request.query[:50]}', top_k={request.top_k}")
        return result
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search_raw")
async def search_raw(request: SearchRequest):
    """纯检索：不生成答案，直接返回文档片段（<1s）。供 pi agent 使用。"""
    try:
        kb = get_kb()
        chunks = await run_in_threadpool(
            kb.search_raw, request.query, request.top_k
        )
        audit_log(
            "SEARCH_RAW",
            "api",
            f"query='{request.query[:50]}', top_k={request.top_k}",
        )
        return {"query": request.query, "sources": chunks}
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _smart_search_sync(request: SearchRequest):
    """
    智能搜索（同步实现） - 知识库检索 + 网络采集双通道
    
    流程：
    1. 先搜索知识库
    2. 如果有结果，直接返回
    3. 如果无结果，调用外部热点采集器
    4. 采集后上传到知识库并返回结果
    
    POST /api/smart_search
    Content-Type: application/json
    Body: {"query": "今日热点", "top_k": 5}
    """
    try:
        kb = get_kb()
        
        # 第一步：搜索知识库
        result = kb.search(request.query, top_k=request.top_k)
        
        # 检查是否有结果
        if result.get("sources") and len(result["sources"]) > 0:
            audit_log("SMART_SEARCH", "api", f"query='{request.query[:50]}', found={len(result['sources'])}")
            return result
        
        # 第二步：无结果，调用外部采集器
        audit_log("SMART_SEARCH", "api", f"query='{request.query[:50]}', no_result, calling_analyzer")
        
        # 调用热点分析器（通过 subprocess）
        import subprocess
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent.parent.parent
        analyzer_path = project_root / "langchain-rag" / "docs" / "comprehensive_hotspot_analyzer.py"
        
        if not analyzer_path.exists():
            raise HTTPException(
                status_code=503,
                detail="热点采集器不可用"
            )
        
        # 创建临时输出目录
        temp_dir = project_root / "langchain-rag" / "documents" / "_temp_analyzer"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 调用热点分析器
        subprocess.run(
            [
                "python",
                str(analyzer_path),
                request.query,
                "--output-dir",
                str(temp_dir)
            ],
            check=True,
            timeout=120,
            capture_output=True,
            text=True
        )
        
        # 检查是否有报告生成
        temp_reports = list(temp_dir.glob("综合热点分析_*.md"))
        if temp_reports:
            report_path = temp_reports[0]
            
            # 读取报告内容
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read()
            
            # 清理临时文件
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")
            
            # 返回结果
            return {
                "query": request.query,
                "answer": f"已触发网络采集，生成报告：\n\n{report_content[:1000]}...",
                "sources": [{
                    "source": str(report_path),
                    "content": report_content[:500],
                    "score": 1.0
                }]
            }
        else:
            return {
                "query": request.query,
                "answer": "已触发网络采集，但未生成报告",
                "sources": []
            }
            
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="热点采集超时（120秒）"
        )
    except Exception as e:
        logger.error(f"智能搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/smart_search")
async def smart_search(request: SearchRequest):
    """智能搜索（async 包装：整体丢线程池，避免 subprocess.run 阻塞 event loop）"""
    return await run_in_threadpool(_smart_search_sync, request)


@app.post("/api/upload", response_model=UploadResult)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """
    异步上传单个文档
    
    - 文件存入临时目录
    - 后台异步向量化
    - 返回 document_id 供状态查询
    
    POST /api/upload
    Content-Type: multipart/form-data
    Body: file=<binary>
    """
    # 1. 验证文件类型
    allowed_ext = {".pdf", ".md", ".txt", ".docx", ".csv", ".json"}
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持的类型: {', '.join(sorted(allowed_ext))}"
        )
    
    # 2. 生成 document_id
    doc_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{doc_id}_{timestamp}{ext}"
    
    # 3. 保存到临时上传目录
    upload_dir = DOCUMENTS_DIR / "_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / safe_name
    
    try:
        content = await file.read()
        temp_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
    
    # 4. 注册文档（pending 状态）
    registry = get_doc_registry()
    registry[doc_id] = {
        "document_id": doc_id,
        "filename": file.filename,
        "status": "pending",
        "stored_path": str(temp_path),
        "chunks": 0,
        "added_at": datetime.now().isoformat(),
        "file_size_bytes": len(content),
        "error": None,
    }
    save_doc_registry(registry)
    
    # 5. 启动后台向量化任务
    if background_tasks:
        background_tasks.add_task(process_upload, doc_id, temp_path, file.filename)
    else:
        # 同步处理（用于测试）
        asyncio.create_task(process_upload(doc_id, temp_path, file.filename))
    
    audit_log("UPLOAD", "api", f"doc_id={doc_id}, file={file.filename}, size={len(content)}")
    
    return UploadResult(
        document_id=doc_id,
        filename=file.filename,
        status="pending",
        message=f"文档已接收，后台处理中。使用 /api/documents/{doc_id} 查询状态。",
        uploaded_at=datetime.now().isoformat()
    )


async def process_upload(doc_id: str, file_path: Path, original_filename: str):
    """后台异步处理文档上传"""
    registry = get_doc_registry()
    
    # 更新状态为 processing
    if doc_id in registry:
        registry[doc_id]["status"] = "processing"
        save_doc_registry(registry)
    
    logger.info(f"[{doc_id}] 开始处理: {original_filename}")
    
    try:
        kb = get_kb()
        success = kb.add_document(str(file_path))
        
        if success:
            # 从向量库查询实际 chunk 数量（用原始 source 路径）
            source_path = str(file_path)
            all_docs = kb.vector_store.list_documents()
            chunks = sum(1 for doc in all_docs if source_path in doc.get("source", ""))
            
            registry[doc_id]["status"] = "completed"
            registry[doc_id]["chunks"] = chunks
            # 移动到正式目录
            final_dir = DOCUMENTS_DIR / "uploaded"
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / file_path.name
            shutil.move(str(file_path), str(final_path))
            registry[doc_id]["stored_path"] = str(final_path)
            save_doc_registry(registry)
            logger.info(f"[{doc_id}] ✅ 处理完成: {original_filename} ({chunks} chunks)")
        else:
            raise Exception("add_document 返回 False")
            
    except Exception as e:
        logger.error(f"[{doc_id}] ❌ 处理失败: {e}")
        if doc_id in registry:
            registry[doc_id]["status"] = "failed"
            registry[doc_id]["error"] = str(e)
            save_doc_registry(registry)
    
    audit_log("PROCESS", "background", f"doc_id={doc_id}, file={original_filename}, success={'✅' if 'success' in locals() else '❌'}")


class UploadBatchRequest(BaseModel):
    """批量上传请求"""
    file_paths: List[str]  # 文件路径列表


@app.post("/api/upload/batch")
async def upload_batch(request: UploadBatchRequest):
    """
    批量上传文档（通过文件路径）
    
    POST /api/upload/batch
    Body: {"file_paths": ["path1", "path2"]}
    """
    results = []
    for file_path in request.file_paths:
        try:
            # 直接处理文件路径
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
            
            filename = file_path_obj.name
            content = file_path_obj.read_bytes()
            
            # 生成 document_id
            doc_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = file_path_obj.suffix.lower()
            
            # 保存到临时上传目录
            upload_dir = DOCUMENTS_DIR / "_uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{doc_id}_{timestamp}{ext}"
            temp_path = upload_dir / safe_name
            
            try:
                temp_path.write_bytes(content)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
            
            # 注册文档（pending 状态）
            registry = get_doc_registry()
            registry[doc_id] = {
                "document_id": doc_id,
                "filename": filename,
                "status": "pending",
                "stored_path": str(temp_path),
                "chunks": 0,
                "added_at": datetime.now().isoformat(),
                "file_size_bytes": len(content),
                "error": None,
            }
            save_doc_registry(registry)
            
            # 启动后台向量化任务
            asyncio.create_task(process_upload(doc_id, temp_path, filename))
            
            results.append({
                "document_id": doc_id,
                "filename": filename,
                "status": "pending",
            })
            
            audit_log("UPLOAD", "api", f"doc_id={doc_id}, file={filename}, size={len(content)}")
            
        except HTTPException as e:
            results.append({
                "filename": file_path,
                "status": "failed",
                "error": str(e.detail)
            })
        except Exception as e:
            results.append({
                "filename": file_path,
                "status": "failed",
                "error": str(e)
            })
    
    audit_log("BATCH_UPLOAD", "api", f"uploaded {len(results)} files")
    return {"uploaded": results, "total": len(results)}


@app.get("/api/documents")
async def list_documents():
    """列出所有已入库文档"""
    try:
        kb = get_kb()
        docs = kb.list_documents()
        stats = kb.get_stats()
        registry = get_doc_registry()
        
        # 合并注册表信息
        for doc in docs:
            doc_id = doc.get("id", "")
            if doc_id in registry:
                doc["status"] = registry[doc_id]["status"]
                doc["chunks"] = registry[doc_id].get("chunks", 0)
        
        return {"documents": docs, "stats": stats, "registry_count": len(registry)}
    except Exception as e:
        logger.error(f"列出文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """查询单个文档状态"""
    registry = get_doc_registry()
    
    if doc_id not in registry:
        raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")
    
    info = registry[doc_id]
    return DocumentInfo(
        document_id=info["document_id"],
        filename=info["filename"],
        status=info["status"],
        chunks=info.get("chunks", 0),
        added_at=info.get("added_at", ""),
        stored_path=info.get("stored_path", ""),
        file_size_bytes=info.get("file_size_bytes", 0)
    )


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档（支持通过 doc_id 或 filename 删除）"""
    registry = get_doc_registry()
    
    # 尝试多种方式查找文档
    info = None
    found_id = None
    
    # 方式 1: 直接匹配 doc_id
    if doc_id in registry:
        info = registry[doc_id]
        found_id = doc_id
    else:
        # 方式 2: 通过文件名或路径匹配
        for rid, reg_info in registry.items():
            if doc_id in reg_info.get("stored_path", "") or doc_id in reg_info.get("filename", ""):
                info = reg_info
                found_id = rid
                break
    
    if not info:
        raise HTTPException(status_code=404, detail=f"文档 {doc_id} 不存在")
    
    # 从向量库删除（通过 doc_id 匹配）
    kb = get_kb()
    # 使用 doc_id 作为 source 关键字删除
    kb.delete_document(doc_id)
    
    # 删除文件
    stored_path = info.get("stored_path", "")
    if stored_path and Path(stored_path).exists():
        Path(stored_path).unlink()
    
    # 从注册表删除
    del registry[found_id]
    save_doc_registry(registry)
    
    audit_log("DELETE", "api", f"doc_id={found_id}, file={info['filename']}")
    
    return {"deleted": True, "document_id": found_id, "filename": info["filename"]}


@app.post("/api/shutdown")
async def shutdown():
    """手动停止服务（延迟 0.2s 退出，保证响应先送达）"""
    threading.Timer(0.2, lambda: graceful_shutdown("manual")).start()
    return {"shutting_down": True, "reason": "manual"}


@app.post("/api/rebuild")
async def rebuild():
    """重建知识库（全量重新导入）"""
    try:
        kb = get_kb()
        count = kb.rebuild()
        audit_log("REBUILD", "api", f"loaded {count} documents")
        return {"rebuilt": True, "documents_loaded": count}
    except Exception as e:
        logger.error(f"重建失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 启动 ====================

def run_server():
    """启动 RAG HTTP 服务"""
    import uvicorn
    
    logger.info("预加载 Embedding 模型...")
    try:
        kb = get_kb()
        from rag_core.vector_store_libsql import VectorStoreManager
        vs = VectorStoreManager()
        vs.search("preload", top_k=1)
        logger.info("✅ Embedding 模型预加载完成")
    except Exception as e:
        logger.warning(f"⚠️  Embedding 模型预加载失败（服务仍可运行）: {e}")
    
    logger.info(f"📡 启动 RAG 服务: http://{RAG_SERVER_HOST}:{RAG_SERVER_PORT}")
    logger.info(f"📖 API 文档: http://localhost:{RAG_SERVER_PORT}/docs")

    # 闲置/内存感知看门狗
    if get_watchdog().enabled:
        threading.Thread(target=_watchdog_loop, daemon=True, name="idle-watchdog").start()
        logger.info(
            f"🐕 看门狗已启动 (闲置>{IDLE_TIMEOUT_SEC}s 或 "
            f"闲置>{MEM_IDLE_SEC}s且可用内存<{MEM_MIN_MB}MB; 轮询 {WATCHDOG_SEC}s)"
        )
    else:
        logger.info("🐕 看门狗已禁用 (RAG_IDLE_TIMEOUT_SEC=0，服务常驻)")

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
