# -*- coding: utf-8 -*-
"""AutoImportManager 单元测试"""
import os
import sys
import time
import unittest
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["POSTHOG_OFF"] = "1"
os.environ["POSTHOG_JS_OFF"] = "1"

from rag_core.auto_importer import AutoImportManager


class TestAutoImportManagerBasic(unittest.TestCase):
    """基础功能测试"""

    def setUp(self):
        self.tmp_dir = Path(__file__).parent.parent / "tests" / "_tmp_test"
        self.tmp_dir.mkdir(exist_ok=True)
        self.docs_dir = self.tmp_dir / "documents"
        self.docs_dir.mkdir(exist_ok=True)
        self.storage_dir = self.tmp_dir / "storage"
        self.storage_dir.mkdir(exist_ok=True)
        self.mgr = AutoImportManager(
            documents_dir=self.docs_dir,
            storage_dir=self.storage_dir,
        )

    def tearDown(self):
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def test_initial_scan_empty(self):
        """空目录初始扫描不应报错"""
        result = self.mgr.scan_and_import()
        self.assertGreaterEqual(result["scanned"], 0)
        self.assertEqual(result["added"], 0)

    def test_add_txt_file_and_scan(self):
        """添加 txt 文件后扫描应自动入库"""
        test_file = self.docs_dir / "test_auto.txt"
        test_file.write_text("这是一条自动导入的测试文档。", encoding="utf-8")

        result = self.mgr.scan_and_import()
        self.assertGreaterEqual(result["scanned"], 1)
        self.assertGreaterEqual(result["added"], 1)

    def test_duplicate_file_skipped(self):
        """重复文件不应重复导入"""
        test_file = self.docs_dir / "test_dup.txt"
        test_file.write_text("重复导入测试内容。", encoding="utf-8")

        r1 = self.mgr.scan_and_import()
        self.assertGreaterEqual(r1["added"], 1)

        r2 = self.mgr.scan_and_import()
        self.assertEqual(r2["added"], 0)
        self.assertGreaterEqual(r2["skipped"], 1)

    def test_modified_file_redetects(self):
        """文件内容变更后应重新导入"""
        test_file = self.docs_dir / "test_mod.txt"
        test_file.write_text("版本一的内容。", encoding="utf-8")

        r1 = self.mgr.scan_and_import()
        self.assertGreaterEqual(r1["added"], 1)

        time.sleep(0.5)
        test_file.write_text("版本二的内容，已修改。", encoding="utf-8")

        r2 = self.mgr.scan_and_import()
        # 修改的文件算 updated，不是 added
        self.assertGreaterEqual(r2["updated"], 1)

    def test_delete_file_handled(self):
        """删除文件后扫描应清理记录"""
        test_file = self.docs_dir / "test_del.txt"
        test_file.write_text("要被删除的文件。", encoding="utf-8")

        r1 = self.mgr.scan_and_import()
        self.assertGreaterEqual(r1["added"], 1)

        test_file.unlink()

        r2 = self.mgr.scan_and_import()
        self.assertGreaterEqual(r2["deleted"], 1)

    def test_unsupported_extension_skipped(self):
        """不支持的文件类型应被跳过"""
        test_file = self.docs_dir / "test.xyz"
        test_file.write_text("不支持的类型。", encoding="utf-8")

        result = self.mgr.scan_and_import()
        self.assertGreaterEqual(result["skipped"], 1)

    def test_subdirectory_scanned(self):
        """子目录中的文件也应被扫描"""
        subdir = self.docs_dir / "subdir"
        subdir.mkdir()
        test_file = subdir / "nested.txt"
        test_file.write_text("嵌套目录中的文件。", encoding="utf-8")

        result = self.mgr.scan_and_import()
        self.assertGreaterEqual(result["scanned"], 1)
        self.assertGreaterEqual(result["added"], 1)


class TestAutoImportIntegration(unittest.TestCase):
    """与知识库集成的端到端测试"""

    def setUp(self):
        self.tmp_dir = Path(__file__).parent.parent / "tests" / "_tmp_test_e2e"
        self.tmp_dir.mkdir(exist_ok=True)
        self.docs_dir = self.tmp_dir / "documents"
        self.docs_dir.mkdir(exist_ok=True)
        self.storage_dir = self.tmp_dir / "storage"
        self.storage_dir.mkdir(exist_ok=True)

    def tearDown(self):
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)

    def test_full_pipeline(self):
        """完整流程：创建文件 → 自动导入 → 可搜索"""
        from rag_core.knowledge_base import KnowledgeBase

        test_file = self.docs_dir / "integration_test.txt"
        test_file.write_text(
            "这是一份集成测试文档。测试文档包含重要信息：RAG 系统非常强大。",
            encoding="utf-8",
        )

        kb = KnowledgeBase(documents_dir=self.docs_dir)
        mgr = AutoImportManager(
            documents_dir=self.docs_dir,
            storage_dir=self.storage_dir,
        )

        result = mgr.scan_and_import()
        self.assertGreaterEqual(result["added"], 1)

        search_result = kb.search("RAG 系统", top_k=1)
        self.assertIsNotNone(search_result)
        self.assertIn("answer", search_result)

    def test_multiple_file_types(self):
        """多种文件格式同时自动导入"""
        from rag_core.knowledge_base import KnowledgeBase

        (self.docs_dir / "test1.txt").write_text("文本文件内容。", encoding="utf-8")
        (self.docs_dir / "test2.md").write_text("# Markdown 文件内容。", encoding="utf-8")
        (self.docs_dir / "test3.json").write_text('{"key": "value"}', encoding="utf-8")

        kb = KnowledgeBase(documents_dir=self.docs_dir)
        mgr = AutoImportManager(
            documents_dir=self.docs_dir,
            storage_dir=self.storage_dir,
        )

        result = mgr.scan_and_import()
        self.assertGreaterEqual(result["added"], 3)

        stats = kb.get_stats()
        self.assertGreaterEqual(stats["total_documents"], 3)


if __name__ == "__main__":
    unittest.main()
