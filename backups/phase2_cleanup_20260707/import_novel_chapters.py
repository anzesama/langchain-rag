#!/usr/bin/env python3
"""
小说章节导入脚本
用法: python import_novel_chapters.py

重构说明:
- 使用 KnowledgeBase 统一管理小说导入
- 移除直接 ChromaDB 操作，使用 KnowledgeBase.add_document()
- 保留断点续传和 LSH 索引功能
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 设置环境变量避免 segfault
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# 添加项目根目录到路径（scripts/ 的父目录）
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_core.knowledge_base import KnowledgeBase
from rag_config import NOVEL_CHAPTERS_DIR, SUPPORTED_EXTENSIONS, logger


def import_single_chapter(kb: KnowledgeBase, chapter_file: Path) -> bool:
    """
    导入单个小说章节
    
    Args:
        kb: KnowledgeBase 实例
        chapter_file: 章节文件路径
        
    Returns:
        是否成功
    """
    if not chapter_file.exists():
        logger.error(f"文件不存在: {chapter_file}")
        return False
    
    try:
        # 使用 KnowledgeBase 添加文档（自动识别为小说文件）
        success = kb.add_document(str(chapter_file))
        
        if success:
            logger.info(f"✅ 成功导入章节: {chapter_file.name}")
        else:
            logger.error(f"❌ 导入章节失败: {chapter_file.name}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ 导入章节异常: {e}", exc_info=True)
        return False


def import_all_chapters(kb: KnowledgeBase, chapters_dir: Path = None) -> int:
    """
    导入所有小说章节
    
    Args:
        kb: KnowledgeBase 实例
        chapters_dir: 章节目录路径，默认为 NOVEL_CHAPTERS_DIR
        
    Returns:
        成功导入的文件数
    """
    if chapters_dir is None:
        chapters_dir = NOVEL_CHAPTERS_DIR
    
    if chapters_dir is None or not chapters_dir.exists():
        logger.error(f"章节目录不存在: {chapters_dir}")
        return 0
    
    # 获取所有 txt 文件
    chapter_files = sorted([f for f in chapters_dir.glob('*.txt') if f.is_file()])
    logger.info(f"找到 {len(chapter_files)} 个小说章节文件")
    
    if not chapter_files:
        logger.warning("没有找到小说章节文件")
        return 0
    
    # 导入所有章节
    success_count = 0
    for chapter_file in chapter_files:
        if import_single_chapter(kb, chapter_file):
            success_count += 1
    
    logger.info(f"章节导入完成: {success_count}/{len(chapter_files)} 成功")
    
    # 显示知识库状态
    stats = kb.get_stats()
    logger.info(f"知识库共有 {stats.get('total_documents', 0)} 个文档")
    
    return success_count


def main():
    """主函数"""
    print("=" * 80)
    print("Novel Chapter Import Tool")
    print("=" * 80)
    print()
    
    # 创建知识库实例
    kb = KnowledgeBase(auto_import=False, auto_build_parent=False)
    
    # 导入所有章节
    chapters_dir_str = input("Enter chapter directory path (press Enter for default): ").strip()
    if chapters_dir_str:
        chapters_dir = Path(chapters_dir_str)
        import_all_chapters(kb, chapters_dir)
    else:
        import_all_chapters(kb)
    
    print("\n[OK] Import completed!")


if __name__ == '__main__':
    main()
