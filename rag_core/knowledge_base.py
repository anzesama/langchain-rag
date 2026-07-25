"""
KnowledgeBase - 统一的入口类,整合文档加载、向量化、检索

集成 LSH 索引、断点续传、因果排序的高性能知识库
"""
import threading
from pathlib import Path
from typing import List, Dict, Optional

from langchain_core.documents import Document

from rag_config import (
    DOCUMENTS_DIR, STORAGE_DIR, SUPPORTED_EXTENSIONS, logger,
    LSH_DIM, LSH_NBITS, NOVEL_CHAPTERS_DIR, SYNC_DOUBLE_WRITE,
)
from rag_core.document_loader import load_document, chunk_documents, load_directory
from rag_core.vector_store_libsql import VectorStoreManager
from rag_core.rag_pipeline import RagPipeline
from rag_core.auto_importer import AutoImportManager
from rag_core.parent_index_builder import build_parent_index_async
from rag_core.lsh_index import LSHIndexManager
from rag_core.resume_loader import ResumeLoader


class KnowledgeBase:
    """
    知识库主类(集成 LSH + 断点续传 + 因果排序)

    用法:
        kb = KnowledgeBase()
        kb.add_document("myfile.pdf")           # 普通文档
        kb.add_document("novel_chapters/章1.txt") # 小说文档(断点续传)
        result = kb.search("如何配置环境变量?")  # LSH 优先检索
    """

    def __init__(self, documents_dir=None, auto_import=True, auto_build_parent=True):
        self.documents_dir = documents_dir or DOCUMENTS_DIR
        self.vector_store = VectorStoreManager()
        self.auto_importer = AutoImportManager(
            documents_dir=self.documents_dir,
            storage_dir=STORAGE_DIR,
        ) if auto_import else None
        self.auto_build_parent = auto_build_parent
        self._pipeline = None
        self._vector_store_warmed = False

        # 新增:LSH 索引管理器
        self.lsh_manager = LSHIndexManager(dim=LSH_DIM, nbits=LSH_NBITS)

        # 加载已有的 LSH 索引
        if self.lsh_manager.load_index():
            logger.info(f"LSH 索引已加载,总向量: {self.lsh_manager._total_vectors}")
        else:
            logger.info("LSH 索引为空")

        # 新增:全局递增计数器
        self._global_order_counter = 0
        self._load_global_counter()

    def _load_global_counter(self):
        """从 LSH 索引加载已有的 global_counter"""
        import json
        
        # 1. 优先从 global_counter.json 恢复
        progress_file = STORAGE_DIR / "global_counter.json"
        if progress_file.exists():
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._global_order_counter = data.get("global_counter", 0)
                logger.info(f"从 global_counter.json 恢复 global_counter: {self._global_order_counter}")
                return
            except Exception as e:
                logger.warning(f"读取 global_counter.json 失败: {e}")
        
        # 2. 从 LSH 索引恢复
        if self.lsh_manager and self.lsh_manager._total_vectors > 0:
            self._global_order_counter = self.lsh_manager._total_vectors
            logger.info(f"从 LSH 索引恢复 global_counter: {self._global_order_counter}")
            return
        
        # 3. 从 libsql 向量库恢复（查询所有文档的 global_order 最大值）
        try:
            docs = self.vector_store.list_documents()
            if docs:
                global_orders = [d.get('metadata', {}).get('global_order', 0) for d in docs if d.get('metadata')]
                if global_orders:
                    self._global_order_counter = max(global_orders)
                    logger.info(f"从 libsql 向量库恢复 global_counter: {self._global_order_counter}")
                    return
        except Exception as e:
            logger.warning(f"从 libsql 向量库恢复 global_counter 失败: {e}")
        
        # 4. 都失败，使用默认值 0
        self._global_order_counter = 0
        logger.info("global_counter 使用默认值: 0")

    def _save_global_counter(self):
        """保存 global_counter 到进度文件"""
        import json
        progress_file = STORAGE_DIR / "global_counter.json"
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump({"global_counter": self._global_order_counter}, f)

    def _is_novel_file(self, filepath: str) -> bool:
        """判断是否为小说类文档"""
        path = Path(filepath)
        # 在 novel_chapters 目录下的文件视为小说
        if NOVEL_CHAPTERS_DIR and path.resolve().is_relative_to(NOVEL_CHAPTERS_DIR.resolve()):
            return True
        # 文件名包含"蛊真人"等关键词
        if "蛊真人" in path.name or "novel" in path.name.lower():
            return True
        return False

    def _sync_wiki_layer(self, chunks, source_file: str):
        """
        同步 Wiki 层：扫描 chunks 中的实体和关系，写入 SQLite
        适用于所有文档类型（小说/普通），提取自 _add_novel_document
        """
        try:
            from rag_core.wiki_updater import WikiUpdater
            from scripts import wiki_graph_web
            import re

            updater = WikiUpdater(use_uie=True)
            wiki_stats = {"entities_added": 0, "relations_added": 0}

            for i, chunk in enumerate(chunks):
                chunk_text = chunk.page_content
                source_info = chunk.metadata.get('source', source_file)
                global_order = chunk.metadata.get('global_order', i)

                # 从 source_info 中提取章节号
                chapter_match = re.search(r'chapter_(\d+)|第(\d+)章', source_info)
                if chapter_match:
                    chapter_num = chapter_match.group(1) or chapter_match.group(2)
                    source_chapter = f"第{chapter_num}章"
                else:
                    source_chapter = source_info

                chunk_stats = updater.batch_add_from_text(
                    text=chunk_text,
                    source_chapter=f"{source_chapter} (Chunk {global_order})",
                    min_confidence=1  # UIE 或正则任一命中即可
                )

                wiki_stats["entities_added"] += chunk_stats["entities_added"]
                wiki_stats["relations_added"] += chunk_stats["relations_added"]

            if wiki_stats["entities_added"] > 0 or wiki_stats["relations_added"] > 0:
                logger.info(f"[OK] Wiki 层已更新: {wiki_stats['entities_added']} 个实体, {wiki_stats['relations_added']} 个关系")
                wiki_graph_web.generate_html()
                logger.info(f"[OK] 知识图谱已重新生成")
            else:
                logger.debug(f"[INFO] Wiki 层无新实体/关系: {source_file}")

        except Exception as e:
            logger.warning(f"[WARNING] Wiki 层更新失败: {e}")
            # 不影响主流程

    def _add_novel_document(self, filepath: str) -> bool:
        """添加小说文档(使用 ResumeLoader + 同步双写)"""
        try:
            # 1. 使用 ResumeLoader 加载（传入 lsh_manager 以共享状态）
            loader = ResumeLoader(
                novel_source=filepath,
                global_counter=self._global_order_counter,
                use_lsh_index=True   # 根据需求开启或关闭 LSH（建议 True）
            )
            chunk_count = loader.load(resume=True)

            if chunk_count == 0:
                logger.warning(f"文档 {filepath} 加载后无新 chunk")
                return True  # 可能已全部加载

            # 2. 获取嵌入向量(从 LSH 重新获取)
            from rag_core.embedding_service import get_embeddings
            import numpy as np

            texts = [c.page_content for c in loader.get_progress()['chunks']]
            if not texts:
                logger.error(f"文档 {filepath} 没有可用的 chunk 内容")
                return False

            embeddings = np.array(get_embeddings(texts, batch_size=loader.embedding_batch_size))

            # 3. 同步双写
            if SYNC_DOUBLE_WRITE:
                # 写 LSH
                self.lsh_manager.add_documents(loader.get_progress()['chunks'], embeddings)
                # 保存 LSH 索引
                self.lsh_manager.save_index()
                # 写 ChromaDB
                self.vector_store.add_documents(loader.get_progress()['chunks'])
                # 更新全局计数器
                self._global_order_counter = loader.global_counter
                self._save_global_counter()

            logger.info(f"[OK] 小说文档已入库: {filepath} ({chunk_count} 个块)")

            # 4. 更新 Wiki 层
            self._sync_wiki_layer(loader.get_progress()['chunks'], filepath)
            return True

        except Exception as e:
            logger.error(f"添加小说文档失败 {filepath}: {e}")
            return False

    def _add_regular_document(self, filepath: str) -> bool:
        """添加普通文档(保持原有逻辑)"""
        path = Path(filepath)
        if not path.exists():
            logger.error(f"文件不存在: {filepath}")
            return False

        try:
            # 1. 加载文档
            documents = load_document(path)
            if not documents:
                logger.warning(f"未从 {filepath} 加载到任何内容")
                return False

            # 2. 分割文档
            chunks = chunk_documents(documents)

            # 3. 过滤空内容和异常内容
            valid_chunks = []
            for c in chunks:
                content = c.page_content
                if not content or not content.strip():
                    continue
                if '>>>' in content:
                    continue
                if 'array(' in content:
                    continue
                stripped = content.replace(' ', '').replace('\n', '')
                if stripped and all(ch.isdigit() or ch in '.-,;:' for ch in stripped):
                    continue
                valid_chunks.append(c)

            if not valid_chunks:
                logger.warning(f"文档 {filepath} 分割后无有效内容")
                return False

            # 4. 添加到向量库
            self.vector_store.add_documents(valid_chunks)

            # 5. 同步 Wiki 层（实体/关系扫描）
            self._sync_wiki_layer(valid_chunks, filepath)

            logger.info(f"Document added: {filepath} ({len(valid_chunks)} chunks)")

            # 6. 异步构建父子索引(后台线程)
            if self.auto_build_parent and len(valid_chunks) > 500:
                self._async_build_parent_index(filepath)

            return True

        except Exception as e:
            logger.error(f"添加文档失败 {filepath}: {e}")
            return False

    @property
    def pipeline(self):
        """懒加载 pipeline,仅在首次调用 ask/search 时初始化"""
        if self._pipeline is None:
            self._pipeline = RagPipeline(vector_store=self.vector_store)
        return self._pipeline

    def add_document(self, filepath: str) -> bool:
        """
        添加单个文档到知识库(自动判断是否为小说)

        Args:
            filepath: 文件路径

        Returns:
            是否成功
        """
        # 判断是否为小说类文档
        if self._is_novel_file(filepath):
            return self._add_novel_document(filepath)
        else:
            return self._add_regular_document(filepath)

    def _async_build_parent_index(self, filepath: str):
        """
        异步构建父子索引(后台线程)

        Args:
            filepath: 文件路径
        """
        def _build_thread():
            try:
                logger.info(f"🔄 开始后台构建父子索引: {filepath}")
                task_id = build_parent_index_async(filepath)
                logger.info(f"Parent index task submitted: {task_id}")
            except Exception as e:
                logger.error(f"❌ 后台构建父子索引失败: {e}")

        # 启动后台线程
        thread = threading.Thread(target=_build_thread, daemon=True)
        thread.start()
        logger.info(f"Parent index background task started: {filepath}")

    def add_directory(self, directory: Optional[Path] = None) -> int:
        """
        批量添加目录下所有文档(按文件分批,避免超大批次)

        Args:
            directory: 文档目录,默认使用配置的 DOCUMENTS_DIR

        Returns:
            成功添加的文件数
        """
        target_dir = directory or self.documents_dir
        if not target_dir.exists():
            logger.error(f"目录不存在: {target_dir}")
            return 0

        try:
            file_list = sorted([f for f in target_dir.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS])
            if not file_list:
                logger.warning(f"目录中无支持的文档: {target_dir}")
                return 0

            total_chunks = 0
            added_files = 0

            for filepath in file_list:
                try:
                    docs = load_document(filepath)
                    if not docs:
                        continue
                    chunks = chunk_documents(docs)

                    # 过滤无效内容
                    valid_chunks = []
                    for c in chunks:
                        content = c.page_content
                        if not content or not content.strip():
                            continue
                        if '>>>' in content:
                            continue
                        if 'array(' in content:
                            continue
                        stripped = content.replace(' ', '').replace('\n', '')
                        if stripped and all(ch.isdigit() or ch in '.-,;:' for ch in stripped):
                            continue
                        valid_chunks.append(c)

                    if valid_chunks:
                        self.vector_store.add_documents(valid_chunks)
                        # 同步 Wiki 层
                        self._sync_wiki_layer(valid_chunks, str(filepath))
                        total_chunks += len(valid_chunks)
                        added_files += 1
                except Exception as e:
                    logger.error(f"加载文件失败 {filepath}: {e}")

            logger.info(f"Directory batch add completed: {target_dir} ({added_files} files, {total_chunks} chunks)")
            return added_files

        except Exception as e:
            logger.error(f"批量添加失败: {e}")
            return 0

    def _auto_import_if_needed(self):
        """在搜索/统计前自动检查并导入新文件"""
        if self.auto_importer:
            try:
                result = self.auto_importer.scan_and_import()
                if result["added"] > 0 or result["updated"] > 0:
                    logger.info(f"自动导入触发: 新增 {result['added']}, 更新 {result['updated']}")
            except Exception as e:
                logger.warning(f"自动导入失败(不影响搜索): {e}")

    def search(self, query: str, top_k: int = None, score_threshold: float = None, source: str = None, use_web: bool = False) -> dict:
        """
        搜索知识库并生成回答(支持混合检索路由 + 实时网络搜索)

        Args:
            query: 查询问题
            top_k: 返回数量
            score_threshold: 相似度阈值
            source: 文档来源(可选,用于路由决策)
            use_web: 是否启用实时网络搜索（本地无结果时自动搜）

        Returns:
            {
                "query": "原始问题",
                "answer": "LLM 回答",
                "sources": [{"source": "文件名", "content": "...", "score": 0.5}],
                "has_web": 是否包含实时搜索数据
            }
        """
        # 预热 ChromaDB（避免首次搜索慢）
        self._warmup_vector_store()
        
        # 关键优化:搜索时不触发自动导入(避免向量化大文件导致超时)
        # 只在添加文档/重建时才触发自动导入
        result = self.pipeline.ask(query, top_k, score_threshold, source)
        
        # 如果本地 KB 无结果且 use_web=True，搜实时数据
        if use_web and not result.get('sources'):
            from tools.multi_source_kb import MultiSourceKB
            multi_kb = MultiSourceKB()
            web_results = multi_kb.search_by_sources(query, ['tavily', 'trend'], top_k)
            
            if web_results['tavily'] or web_results['trend']:
                all_sources = result.get('sources', [])
                all_sources.extend(web_results['tavily'] + web_results['trend'])
                result['sources'] = all_sources
                result['has_web'] = True
        
        return result

    def search_raw(self, query: str, top_k: int = 5, score_threshold: float = 0.3, source: str = None) -> List[Dict]:
        """
        原始检索（不生成回答，直接返回文档片段）
        
        Args:
            query: 查询文本
            top_k: 返回数量
            score_threshold: 相似度阈值
            source: 文档来源（可选）
            
        Returns:
            [{"source": "文件名", "content": "文档片段", "score": 0.5}, ...]
        """
        # 空查询处理
        if not query or not query.strip():
            logger.warning("空查询，返回空结果")
            return []
        
        # 预热 ChromaDB（避免首次搜索慢）
        self._warmup_vector_store()
        
        # 直接调用 retrieve，不经过 LLM 生成
        results = self.pipeline.retrieve(query, top_k, score_threshold, source)
        
        return [
            {
                "source": doc.metadata.get("source", "未知"),
                "content": doc.page_content,
                "score": round(score, 4)
            }
            for doc, score in results
        ]

    def list_documents(self) -> List[Dict]:
        """列出所有已入库文档"""
        # 不触发自动导入,避免向量化大文件
        return self.vector_store.list_documents()

    def get_stats(self) -> Dict:
        """获取知识库统计信息"""
        # 不触发自动导入,避免向量化大文件
        return self.vector_store.get_stats()

    def _warmup_vector_store(self):
        """预热 ChromaDB，避免首次搜索慢"""
        if self._vector_store_warmed:
            return
        if not self.vector_store:
            self._vector_store_warmed = True
            return
        try:
            # 执行一次空搜索预热
            self.vector_store.search("test", top_k=1)
            self._vector_store_warmed = True
            logger.info("ChromaDB 预热完成")
        except Exception as e:
            logger.warning(f"ChromaDB 预热失败: {e}")
            self._vector_store_warmed = True  # 即使失败也标记为已尝试

    def get_novel_status(self) -> dict:
        """获取小说加载状态"""
        return {
            "global_counter": self._global_order_counter,
            "lsh_total_vectors": self.lsh_manager._total_vectors if self.lsh_manager else 0,
        }

    def rebuild(self, novel_only: bool = False) -> int:
        """
        重新构建知识库

        Args:
            novel_only: True=仅清空小说数据, False=清空全部

        Returns:
            重新加载的文档数
        """
        if novel_only:
            logger.info("开始重建小说知识库...")
            if self.lsh_manager:
                self.lsh_manager.clear()
            self._global_order_counter = 0
            self._save_global_counter()
            return 0
        else:
            logger.info("开始重建知识库...")
            self.vector_store.delete_collection()
            self.vector_store = VectorStoreManager()
            self._pipeline = None
            if self.lsh_manager:
                self.lsh_manager.clear()
            self._global_order_counter = 0
            self._save_global_counter()
            return self.add_directory()

    def delete_document(self, doc_id_or_source: str) -> bool:
        """
        删除指定文档(通过 source 文件名)

        Args:
            doc_id_or_source: 文档 ID 或源文件名

        Returns:
            是否成功
        """
        try:
            count = self.vector_store.delete_by_source(doc_id_or_source)
            logger.info(f"已删除文档: {doc_id_or_source} ({count} chunks)")
            return count > 0
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return False
