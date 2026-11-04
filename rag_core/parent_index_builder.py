"""
后台异步构建父子索引

功能：
1. 在后台线程中异步构建父子索引
2. 不阻塞主流程
3. 支持进度回调和状态追踪
"""
import threading
import time
import hashlib
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, Future

from langchain_core.documents import Document

from rag_config import logger
from rag_core.document_loader import load_document, RecursiveCharacterTextSplitter
from rag_core.parent_document_retriever import ParentDocumentRetriever
from rag_core.vector_store_libsql import VectorStoreManager
from langchain_core.documents import Document


class VectorStoreWithParentRetriever:
    """
    父子向量存储（简化版，用于索引构建）
    """
    
    def __init__(self, persist_dir: str, embedding_model: str, embedding_device: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store = VectorStoreManager()
        self.embedding_model = embedding_model
        self.embedding_device = embedding_device
    
    def add_chapter(self, text: str, chapter_id: str, chapter_num: int):
        """
        添加父块（章节）
        
        Args:
            text: 章节文本
            chapter_id: 章节 ID
            chapter_num: 章节编号
        """
        doc = Document(
            page_content=text,
            metadata={
                "type": "parent",
                "chapter_id": chapter_id,
                "chapter_num": chapter_num
            }
        )
        self.vector_store.add_documents([doc])


class ParentIndexBuilder:
    """
    父子索引构建器
    
    支持：
    - 异步构建
    - 进度追踪
    - 单文件/批量构建
    """
    
    def __init__(self, persist_dir: str = None):
        self.persist_dir = Path(persist_dir) if persist_dir else Path("storage/knowledge_base")
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="parent_builder")
        self._futures: Dict[str, Future] = {}
        self._progress: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, Callable] = {}
        logger.info("ParentIndexBuilder 初始化完成")
    
    def build_single_file(self, filepath: str, callback: Callable = None) -> str:
        """
        异步构建单个文件的父子索引
        
        Args:
            filepath: 文件路径
            callback: 进度回调函数
            
        Returns:
            任务 ID
        """
        task_id = hashlib.md5(filepath.encode()).hexdigest()[:12]
        self._progress[task_id] = {
            "status": "pending",
            "progress": 0,
            "total_steps": 3,
            "current_step": 0,
            "error": None,
        }
        
        if callback:
            self._callbacks[task_id] = callback
        
        future = self._executor.submit(
            self._build_single_file_task,
            filepath,
            task_id
        )
        self._futures[task_id] = future
        
        logger.info(f"📝 开始构建父子索引: {filepath} (任务 ID: {task_id})")
        return task_id
    
    def build_multiple_files(self, filepaths: list, callback: Callable = None) -> list:
        """
        异步构建多个文件的父子索引
        
        Args:
            filepaths: 文件路径列表
            callback: 进度回调函数
            
        Returns:
            任务 ID 列表
        """
        task_ids = []
        for filepath in filepaths:
            task_id = self.build_single_file(filepath, callback)
            task_ids.append(task_id)
        
        logger.info(f"📝 开始批量构建父子索引: {len(filepaths)} 个文件")
        return task_ids
    
    def _build_single_file_task(self, filepath: str, task_id: str):
        """
        构建单个文件的父子索引（后台任务）
        """
        try:
            # Step 1: 加载文档
            self._update_progress(task_id, "loading", 1, 3)
            logger.info(f"[{task_id}] Step 1/3: 加载文档")
            
            doc_path = Path(filepath)
            if not doc_path.exists():
                raise FileNotFoundError(f"文件不存在: {filepath}")
            
            # 加载文档
            from rag_core.document_loader import load_document
            documents = load_document(doc_path)
            if not documents:
                raise ValueError(f"未从 {filepath} 加载到任何内容")
            
            # Step 2: 切分为父块
            self._update_progress(task_id, "splitting", 2, 3)
            logger.info(f"[{task_id}] Step 2/3: 切分为父块")
            
            # 使用粗粒度切分器（2000 字符/块）
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=2000,
                chunk_overlap=200,
                separators=["\n\n", "\n", "。", "!", "?", ";", "...", ", ", ",", ". ", ".", " ", ""]
            )
            
            parent_docs = parent_splitter.split_documents(documents)
            logger.info(f"[{task_id}] 切分为 {len(parent_docs)} 个父块")
            
            # Step 3: 构建父子索引
            self._update_progress(task_id, "building_index", 3, 3)
            logger.info(f"[{task_id}] Step 3/3: 构建父子索引")
            
            # 初始化 VectorStoreWithParentRetriever
            parent_vs = VectorStoreWithParentRetriever(
                persist_dir=self.persist_dir,
                embedding_model="BAAI/bge-small-zh-v1.5",
                embedding_device="cpu"
            )
            
            # 为每个父块添加
            total_added = 0
            for i, parent_doc in enumerate(parent_docs):
                parent_id = f"parent_{task_id}_{i}"
                parent_vs.add_chapter(
                    text=parent_doc.page_content,
                    chapter_id=parent_id,
                    chapter_num=i
                )
                total_added += 1
                
                # 更新进度
                if (i + 1) % 10 == 0 or i == len(parent_docs) - 1:
                    progress = (i + 1) / len(parent_docs) * 100
                    self._update_progress(task_id, "building_index", 3, 3, progress)
            
            # 完成
            self._update_progress(task_id, "completed", 3, 3, 100)
            logger.info(f"✅ 父子索引构建完成: {filepath} ({total_added} 个父块)")
            
        except Exception as e:
            logger.error(f"❌ 父子索引构建失败: {filepath} - {e}")
            self._update_progress(task_id, "error", 0, 3, error=str(e))
    
    def _update_progress(self, task_id: str, status: str, current_step: int, total_steps: int, progress: float = None, error: str = None):
        """更新任务进度"""
        self._progress[task_id]["status"] = status
        self._progress[task_id]["current_step"] = current_step
        self._progress[task_id]["total_steps"] = total_steps
        if progress is not None:
            self._progress[task_id]["progress"] = progress
        if error is not None:
            self._progress[task_id]["error"] = error
        
        # 调用回调函数
        if task_id in self._callbacks:
            try:
                self._callbacks[task_id](self._progress[task_id])
            except Exception as e:
                logger.warning(f"回调函数执行失败: {e}")
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        return self._progress.get(task_id, {"status": "not_found"})
    
    def wait_for_completion(self, task_id: str, timeout: int = 3600) -> bool:
        """
        等待任务完成
        
        Args:
            task_id: 任务 ID
            timeout: 超时时间（秒）
            
        Returns:
            是否成功
        """
        if task_id not in self._futures:
            logger.warning(f"任务 ID 不存在: {task_id}")
            return False
        
        try:
            future = self._futures[task_id]
            future.result(timeout=timeout)
            return self._progress.get(task_id, {}).get("status") == "completed"
        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            return False
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self._futures:
            return self._futures[task_id].cancel()
        return False
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务状态"""
        return self._progress.copy()


# 全局实例
_parent_index_builder: Optional[ParentIndexBuilder] = None


def get_parent_index_builder() -> ParentIndexBuilder:
    """获取全局构建器实例"""
    global _parent_index_builder
    if _parent_index_builder is None:
        _parent_index_builder = ParentIndexBuilder()
    return _parent_index_builder


def build_parent_index_async(filepath: str, callback: Callable = None) -> str:
    """
    异步构建父子索引（便捷函数）
    
    Args:
        filepath: 文件路径
        callback: 进度回调函数
        
    Returns:
        任务 ID
    """
    builder = get_parent_index_builder()
    return builder.build_single_file(filepath, callback)


def build_parent_index_sync(filepath: str) -> bool:
    """
    同步构建父子索引（阻塞）
    
    Args:
        filepath: 文件路径
        
    Returns:
        是否成功
    """
    builder = get_parent_index_builder()
    task_id = builder.build_single_file(filepath)
    return builder.wait_for_completion(task_id)
