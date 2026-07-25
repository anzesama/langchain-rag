"""
RAG 主流程 — 检索增强生成（支持混合检索路由）
"""
import os
from typing import List, Tuple

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from rag_config import (
    RAG_SYSTEM_PROMPT, TOP_K, SCORE_THRESHOLD,
    LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    OPENAI_API_KEY, OPENAI_BASE_URL,
    AGNES_API_KEY, AGNES_API_BASE, logger,
    LSH_RECALL_MIN_COUNT, LSH_RECALL_MIN_SCORE,
)
from rag_core.vector_store import VectorStoreManager
from rag_core.hybrid_router import hybrid_search
from rag_core.causal_sorter import CausalSorter
from rag_core.hybrid_retriever import HybridRetriever
from rag_core.wiki_router import get_wiki_router
from rag_core.wiki_db import get_wiki_db


def get_llm() -> ChatOpenAI:
    """创建 LLM 实例（默认使用 Agnes API）"""
    kwargs = {
        "model": LLM_MODEL,
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
    }
    
    # 优先级 1: Agnes API（默认）
    agnes_api_key = os.getenv("RAG_AGNES_API_KEY", AGNES_API_KEY)
    agnes_base_url = os.getenv("RAG_AGNES_API_BASE", AGNES_API_BASE)
    
    if agnes_api_key:
        kwargs["api_key"] = agnes_api_key
        kwargs["base_url"] = agnes_base_url
        logger.info(f"使用 Agnes API: {LLM_MODEL}")
    else:
        # 优先级 2: 自定义 OpenAI 兼容 API（环境变量）
        custom_api_key = os.getenv("RAG_OPENAI_API_KEY", "")
        custom_base_url = os.getenv("RAG_OPENAI_BASE_URL", None)
        
        if custom_api_key:
            kwargs["api_key"] = custom_api_key
            if custom_base_url:
                kwargs["base_url"] = custom_base_url
            logger.info(f"使用自定义 OpenAI 兼容 API: {custom_base_url or 'default'}")
        else:
            logger.warning(
                "未设置任何 LLM API Key，将返回检索结果而非生成回答。\n"
                "请设置环境变量: RAG_AGNES_API_KEY"
            )
    
    return ChatOpenAI(**kwargs)


class RagPipeline:
    """
    RAG 检索增强生成管道（LSH 优先 + 因果排序）
    
    流程：
    1. 用户提问
    2. 从 LSH 索引检索（高速）
    3. 如果召回不足，回退到 ChromaDB HNSW
    4. 对小说类文档应用因果排序
    5. 构建 prompt（检索内容 + 问题）
    6. 调用 LLM 生成回答
    """
    
    def __init__(self, vector_store: VectorStoreManager = None, llm=None, lsh_manager=None):
        self.vector_store = vector_store or VectorStoreManager()
        self.llm = llm  # 允许外部传入 LLM 实例
        self.lsh_manager = lsh_manager  # LSH 管理器（可选）
        
        # P0+P1: 混合检索器（LSH + HNSW + BM25 + CrossEncoder 重排）
        self._hybrid_retriever = None
    
    def _ensure_llm(self):
        """懒加载 LLM（首次调用时初始化）"""
        if self.llm is None:
            self.llm = get_llm()
    
    def _warmup_vector_store(self):
        """预热 ChromaDB，避免首次搜索慢"""
        if not hasattr(self, '_vector_store_warmed'):
            self._vector_store_warmed = False
        if not self._vector_store_warmed and self.vector_store:
            try:
                # 执行一次空搜索预热
                self.vector_store.search("test", top_k=1)
                self._vector_store_warmed = True
                logger.info("ChromaDB 预热完成")
            except Exception as e:
                logger.warning(f"ChromaDB 预热失败: {e}")
                self._vector_store_warmed = True  # 即使失败也标记为已尝试
    
    def _get_hybrid_retriever(self, enable_reranker: bool = False) -> HybridRetriever:
        """懒加载混合检索器（P0+P1）
        
        Args:
            enable_reranker: 是否启用 CrossEncoder 重排器（默认关闭，因为太慢）
        """
        if self._hybrid_retriever is None:
            reranker = None
            if enable_reranker:
                # 创建 CrossEncoder 重排器（P0）
                from rag_core.reranker import create_reranker
                try:
                    reranker = create_reranker()
                    logger.info("CrossEncoder 重排器已加载")
                except Exception as e:
                    logger.warning(f"CrossEncoder 重排器加载失败: {e}")
                    reranker = None
            
            self._hybrid_retriever = HybridRetriever(
                lsh_manager=self.lsh_manager,
                vector_store=self.vector_store,
                reranker=reranker
            )
        return self._hybrid_retriever
    
    def retrieve(self, query: str, top_k: int = None, score_threshold: float = None, source: str = None) -> List[Tuple[Document, float]]:
        """
        从向量库检索相关文档（P0: CrossEncoder 重排 + P1: 多路召回）
        
        流程：
        1. 多路召回（LSH + ChromaDB HNSW + BM25）→ Top-50
        2. 去重合并 → 保留最高分
        3. CrossEncoder 重排 → Top-10
        4. 因果排序（仅小说类）→ Top-K
        
        Args:
            query: 查询文本
            top_k: 返回数量
            score_threshold: 相似度阈值
            source: 文档来源（可选，用于路由决策）
            
        Returns:
            (文档, 距离分数) 列表
        """
        top_k = top_k or TOP_K
        score_threshold = score_threshold or SCORE_THRESHOLD
        
        # 使用混合检索器（P0+P1）
        try:
            hybrid_results = self._get_hybrid_retriever().retrieve(
                query=query,
                top_k=top_k * 2,  # 给重排留余量
                score_threshold=score_threshold,
                source=source
            )
            
            if not hybrid_results:
                logger.warning("混合检索无结果，降级到原始逻辑")
                return self._fallback_retrieve(query, top_k, score_threshold, source)
            
            # 转换为 (Document, float) 格式
            results = []
            for doc_id, text, metadata, score in hybrid_results:
                from langchain_core.documents import Document
                doc = Document(page_content=text, metadata=metadata)
                results.append((doc, score))
            
            return results[:top_k]
        
        except Exception as e:
            logger.warning(f"混合检索失败，降级到原始逻辑: {e}")
            return self._fallback_retrieve(query, top_k, score_threshold, source)
    
    def _fallback_retrieve(self, query: str, top_k: int, score_threshold: float, source: str) -> List[Tuple[Document, float]]:
        """
        降级检索逻辑（原始 LSH + HNSW）
        当混合检索器不可用时使用
        """
        from rag_core.embedding_service import get_embeddings
        
        # 1. LSH 优先检索
        lsh_results = []
        lsh_scores = []
        if self.lsh_manager:
            query_vec = get_embeddings([query])[0]
            lsh_ids = self.lsh_manager.search(query_vec, k=top_k * 2)
            if lsh_ids:
                lsh_docs = self.lsh_manager.get_documents(lsh_ids)
                lsh_scores = self.lsh_manager.get_scores(query_vec, k=len(lsh_ids))
                lsh_results = [(doc, 0) for doc in lsh_docs]  # 临时分数
        
        # 2. 判断是否需要回退
        need_fallback = (
            len(lsh_results) < LSH_RECALL_MIN_COUNT or
            (lsh_scores and max(lsh_scores) < LSH_RECALL_MIN_SCORE)
        )
        
        if need_fallback:
            # 回退到 ChromaDB HNSW
            hnsw_results = hybrid_search(query, top_k=top_k * 2, source=source)
            # 合并去重
            all_results = self._merge_results(lsh_results, hnsw_results)
        else:
            all_results = lsh_results
        
        # 3. 条件因果排序
        all_results = self._apply_causal_sort(all_results)
        
        return all_results[:top_k]
    
    def _merge_results(self, lsh_results: List, hnsw_results: List) -> List[Tuple[Document, float]]:
        """合并 LSH 和 HNSW 结果，去重"""
        seen_ids = set()
        merged = []
        for doc, score in lsh_results + hnsw_results:
            doc_id = id(doc)
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged.append((doc, score))
        return merged
    
    def _apply_causal_sort(self, results: List[Tuple[Document, float]]) -> List[Tuple[Document, float]]:
        """
        对包含 global_order 的文档应用因果排序
        
        条件：至少 80% 的文档包含 doc_type == 'novel'
        """
        if not results:
            return results
        
        novel_count = sum(1 for doc, _ in results if doc.metadata.get("doc_type") == "novel")
        if novel_count / len(results) <= 0.8:
            return results  # 非小说类，不排序
        
        # 提取文档和分数
        docs = [doc for doc, _ in results]
        sorter = CausalSorter(context_window=5, expand_neighbors=2)
        sorted_docs = sorter.sort(docs)
        
        # 重建结果列表
        doc_map = {id(doc): (doc, score) for doc, score in results}
        sorted_results = []
        for doc in sorted_docs:
            if id(doc) in doc_map:
                sorted_results.append(doc_map[id(doc)])
            else:
                sorted_results.append((doc, 0))
        
        return sorted_results
    
    def generate_answer(self, query: str, retrieved_docs: List[Tuple[Document, float]]) -> str:
        """
        基于检索结果生成回答
        
        Args:
            query: 用户问题
            retrieved_docs: 检索到的文档列表
            
        Returns:
            LLM 生成的回答
        """
        # 关键优化：知识库为空时，调用外部采集器
        if not retrieved_docs:
            return self._call_external_analyzer(query)
        
        # 确保 LLM 已初始化
        self._ensure_llm()
        
        if self.llm is None:
            return (
                "未配置 LLM（未设置 RAG_AGNES_API_KEY 或 RAG_OPENAI_API_KEY），无法生成回答。\n"
                "检索到的相关文档如下：\n\n" + self._format_sources(retrieved_docs)
            )
        
        # 构建上下文
        context_parts = []
        for doc, score in retrieved_docs:
            source = doc.metadata.get("source", "未知")
            context_parts.append(f"[来源: {source}]\n{doc.page_content}\n")
        
        context = "\n---\n".join(context_parts)
        
        # 构建 prompt
        prompt = RAG_SYSTEM_PROMPT.format(context=context, question=query)
        
        # 调用 LLM
        response = self.llm.invoke(prompt)
        answer = response.content
        
        logger.info(f"生成回答完成，问题长度: {len(query)}, 答案长度: {len(answer)}")
        return answer
    
    @staticmethod
    def _format_sources(retrieved_docs: List[Tuple[Document, float]]) -> str:
        """格式化展示检索到的文档来源"""
        parts = []
        for doc, score in retrieved_docs:
            source = doc.metadata.get("source", "未知")
            parts.append(f"[来源: {source}] (distance: {score:.4f})\n{doc.page_content[:200]}\n")
        return "\n---\n".join(parts)

    def _call_external_analyzer(self, query: str) -> str:
        """
        当知识库无相关内容时，调用外部热点采集器（使用加固函数）
        
        Args:
            query: 用户问题
            
        Returns:
            采集器生成的回答或提示
        """
        return trigger_network_search(query)
    
    def ask(self, query: str, top_k: int = None, score_threshold: float = None, source: str = None) -> dict:
        """
        完整 RAG 流程：检索 + 生成（支持 Wiki + 混合检索路由）
        
        Args:
            query: 用户问题
            top_k: 检索数量
            score_threshold: 相似度阈值
            source: 文档来源（可选）
            
        Returns:
            {
                "answer": "LLM 回答",
                "sources": [{"source": "文件名", "content": "文档片段", "score": 0.5}],
                "query": "原始问题"
            }
        """
        # 0. Wiki 路由判断
        wiki_db = get_wiki_db()
        router = get_wiki_router()
        route = router.route(query)
        
        if route == "wiki":
            # Wiki 查询
            wiki_answer = wiki_db.get_fact_query_answer(query)
            if wiki_answer:
                logger.info(f"[Wiki] 查询成功: {query}")
                return {
                    "query": query,
                    "answer": wiki_answer,
                    "sources": [],
                    "route": "wiki"
                }
            else:
                logger.info(f"[Wiki] 查询无结果，回退到 RAG: {query}")
        
        # 1. 检索（使用混合路由）
        retrieved = self.retrieve(query, top_k, score_threshold, source)
        
        # 2. 生成
        answer = self.generate_answer(query, retrieved)
        
        # 3. 格式化来源
        sources = [
            {
                "source": doc.metadata.get("source", "未知"),
                "content": doc.page_content[:200],  # 截断显示
                "score": round(score, 4)
            }
            for doc, score in retrieved
        ]
        
        return {
            "query": query,
            "answer": answer,
            "sources": sources,
            "route": "rag"
        }


# ==================== 加固代码：外部采集器调用 ====================

import sys
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# 基于 __file__ 的绝对路径
PROJECT_ROOT = Path(__file__).parent.parent.parent  # project-config 根目录
ANALYZER_SCRIPT = PROJECT_ROOT / "langchain-rag" / "docs" / "comprehensive_hotspot_analyzer.py"

def trigger_network_search(query: str) -> str:
    """
    触发网络采集（加固版）
    
    Args:
        query: 查询问题
        
    Returns:
        采集结果或错误信息
    """
    try:
        # 1. 创建报告目录
        report_dir = PROJECT_ROOT / "langchain-rag" / "documents" / "_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = query.replace("/", "_").replace("\\", "_")[:30]
        report_path = report_dir / f"{safe_query}_{timestamp}.md"
        
        # 2. 构建命令（使用 sys.executable 指定 Python 解释器）
        cmd = [
            sys.executable,  # 使用当前 Python 解释器
            str(ANALYZER_SCRIPT),
            query,
            "--output-dir",
            str(report_dir)
        ]
        
        # 3. 执行采集（超时 60 秒）
        logger.info(f"调用热点采集器: {query}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=60
        )
        
        # 4. 检查执行结果
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "未知错误"
            raise RuntimeError(f"采集失败：{error_msg}")
        
        # 5. 检查报告是否生成
        temp_reports = list(report_dir.glob(f"*{safe_query}*.md"))
        if not temp_reports:
            # 尝试按文件名模式查找
            temp_reports = list(report_dir.glob("综合热点分析_*.md"))
        
        if temp_reports:
            report_path = temp_reports[-1]  # 取最新的报告
            
            # 6. 上传报告到知识库（超时 30 秒）
            try:
                upload_url = "http://localhost:8765/api/upload"
                with open(report_path, "rb") as f:
                    files = {"file": (report_path.name, f, "text/markdown")}
                    upload_resp = requests.post(upload_url, files=files, timeout=30)
                    
                    if upload_resp.status_code == 200:
                        logger.info(f"报告已上传到知识库: {report_path.name}")
                    else:
                        logger.warning(f"报告上传失败: {upload_resp.text}")
                        raise RuntimeError(f"报告上传失败: {upload_resp.text}")
            except Exception as e:
                logger.warning(f"报告上传异常（不影响返回）: {e}")
                # 上传失败不影响返回结果
            
            # 7. 读取报告内容（限制长度）
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    report_content = f.read()
                
                # 限制返回内容长度（1000 字符）
                if len(report_content) > 1000:
                    report_content = report_content[:1000] + "..."
                
                return f"已触发网络采集，生成报告：\n\n{report_content}"
            except Exception as e:
                logger.warning(f"读取报告失败: {e}")
                return f"已触发网络采集，报告路径：{report_path}"
        else:
            return f"已触发网络采集，但未找到报告文件。输出：{result.stdout[:200]}"
            
    except subprocess.TimeoutExpired:
        logger.error(f"热点采集超时（60秒）")
        return "网络采集超时，请稍后重试。"
    except RuntimeError as e:
        logger.error(f"网络采集失败: {e}")
        return f"网络采集失败：{e}"
    except Exception as e:
        logger.error(f"触发网络采集异常: {e}")
        return f"网络采集异常：{e}"
