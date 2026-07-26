# -*- coding: utf-8 -*-
"""
AutoImportManager — 文档目录自动导入管理器

功能：
1. 扫描 documents 目录，检测新增/修改/删除的文件
2. 自动加载 → 切分 → 向量化 → 入库
3. 维护指纹记录，避免重复导入
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from langchain_core.documents import Document

from rag_config import SUPPORTED_EXTENSIONS, logger
from rag_core.document_loader import load_document, chunk_documents
from rag_core.vector_store_libsql import VectorStoreManager


class AutoImportManager:
    """文档目录自动导入管理器"""

    def __init__(
        self,
        documents_dir: Optional[Path] = None,
        storage_dir: Optional[Path] = None,
        fingerprint_file: Optional[Path] = None,
    ):
        self.documents_dir = documents_dir or Path(__file__).parent.parent / "documents"
        self.storage_dir = storage_dir or Path(__file__).parent.parent / "storage"
        self.fingerprint_file = fingerprint_file or self.storage_dir / ".import_fingerprints.json"
        self.vector_store = VectorStoreManager()
        self._fingerprints: Dict[str, dict] = {}
        self._load_fingerprints()

    def _compute_md5(self, filepath: Path) -> str:
        """计算文件的 MD5 哈希"""
        try:
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算 MD5 失败 {filepath}: {e}")
            return ""

    def _load_fingerprints(self):
        """加载指纹记录"""
        if self.fingerprint_file.exists():
            try:
                with open(self.fingerprint_file, "r", encoding="utf-8") as f:
                    self._fingerprints = json.load(f)
                logger.debug(f"加载指纹记录: {len(self._fingerprints)} 条")
            except Exception as e:
                logger.warning(f"加载指纹记录失败: {e}，将从零开始")
                self._fingerprints = {}

    def _save_fingerprints(self):
        """保存指纹记录"""
        try:
            self.fingerprint_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.fingerprint_file, "w", encoding="utf-8") as f:
                json.dump(self._fingerprints, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存指纹记录失败: {e}")

    def _is_supported(self, filepath: Path) -> bool:
        """检查文件是否支持"""
        return filepath.suffix.lower() in SUPPORTED_EXTENSIONS

    def scan_and_import(self) -> dict:
        """
        扫描文档目录并自动导入新文件
        
        Returns:
            {
                "scanned": 扫描的文件数,
                "added": 新增的文件数,
                "updated": 更新的文件数,
                "deleted": 删除的文件数,
                "skipped": 跳过的文件数,
                "errors": 错误数
            }
        """
        if not self.documents_dir.exists():
            logger.warning(f"文档目录不存在: {self.documents_dir}")
            return {"scanned": 0, "added": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": 0}

        result = {"scanned": 0, "added": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": 0}

        # 收集当前目录中所有支持的文件
        current_files = set()
        for filepath in sorted(self.documents_dir.rglob("*")):
            if not filepath.is_file():
                continue
            rel_key = str(filepath.relative_to(self.documents_dir))
            
            if not self._is_supported(filepath):
                result["skipped"] += 1
                continue

            result["scanned"] += 1
            current_files.add(rel_key)

            md5 = self._compute_md5(filepath)
            if not md5:
                result["errors"] += 1
                continue

            # 检查是否是新文件或已更新
            if rel_key not in self._fingerprints or self._fingerprints[rel_key]["md5"] != md5:
                if self._import_file(filepath, rel_key):
                    if rel_key not in self._fingerprints:
                        result["added"] += 1
                    else:
                        result["updated"] += 1
                    self._fingerprints[rel_key] = {
                        "md5": md5,
                        "mtime": filepath.stat().st_mtime,
                        "size": filepath.stat().st_size,
                    }
                else:
                    result["errors"] += 1
            else:
                result["skipped"] += 1

        # 检查是否有文件被删除
        for key in list(self._fingerprints.keys()):
            if key not in current_files:
                self._delete_from_vector_store(key)
                del self._fingerprints[key]
                result["deleted"] += 1
                logger.info(f"文件已删除并从向量库移除: {key}")

        # 保存指纹记录
        self._save_fingerprints()

        # 如果有增删改，刷新向量库
        total = result["added"] + result["updated"] + result["deleted"]
        if total > 0:
            logger.info(f"自动导入完成: 新增 {result['added']}, 更新 {result['updated']}, 删除 {result['deleted']}, 跳过 {result['skipped']}")
            # 刷新 vectorstore 使新数据立即可查
            try:
                self.vector_store.reload()
            except Exception as e:
                logger.warning(f"向量库刷新失败: {e}")
        else:
            logger.debug(f"自动导入扫描完成: 扫描 {result['scanned']}, 无变化")

        return result

    def _import_file(self, filepath: Path, rel_key: str) -> bool:
        """导入单个文件"""
        try:
            # 加载文档
            documents = load_document(filepath)
            if not documents:
                logger.warning(f"未从 {filepath} 加载到任何内容")
                return False

            # 切分文档
            chunks = chunk_documents(documents)
            if not chunks:
                logger.warning(f"文档 {filepath} 切分后为空")
                return False

            # 更新 metadata 使用相对路径
            for doc in chunks:
                doc.metadata["source"] = rel_key

            # 添加到向量库
            self._add_to_vector_store(chunks, rel_key)
            logger.info(f"✅ 自动导入: {filepath.name} ({len(chunks)} 个块)")

            # 同步 Wiki 层
            try:
                from rag_core.wiki_updater import WikiUpdater
                updater = WikiUpdater()
                combined_text = "\n".join([c.page_content for c in chunks])
                wiki_stats = updater.batch_add_from_text(
                    text=combined_text,
                    source_chapter=rel_key,
                    min_confidence=2
                )
                logger.info(f"Wiki 更新: {wiki_stats['entities_added']} 实体, {wiki_stats['relations_added']} 关系")
            except Exception as e:
                logger.warning(f"Wiki 更新失败 {filepath}: {e}")

            return True
        except Exception as e:
            logger.error(f"自动导入失败 {filepath}: {e}")
            return False

    def _add_to_vector_store(self, documents: List[Document], source_rel_key: str):
        """添加文档到向量库，使用 source 相关的唯一 ID"""
        if not documents:
            return

        # 使用 source + 索引作为唯一 ID，避免重复
        ids = [f"auto_{hashlib.md5((source_rel_key + str(i)).encode()).hexdigest()[:12]}"
               for i, doc in enumerate(documents)]

        self.vector_store.add_documents(documents, ids=ids)

    def _delete_from_vector_store(self, source_rel_key: str):
        """从向量库中删除指定源文件的所有文档块"""
        try:
            deleted_count = self.vector_store.delete_by_source(source_rel_key)
            logger.info(f"已从向量库删除 {deleted_count} 个文档块: {source_rel_key}")
        except Exception as e:
            logger.error(f"删除向量库文档失败 {source_rel_key}: {e}")

    def get_status(self) -> dict:
        """获取自动导入状态"""
        return {
            "tracked_files": len(self._fingerprints),
            "documents_dir": str(self.documents_dir),
            "fingerprints_file": str(self.fingerprint_file),
        }
