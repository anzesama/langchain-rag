#!/usr/bin/env python3
"""
知识库文档添加脚本
用法: python add_documents.py [文档路径]

重构说明:
- 使用 KnowledgeBase 类统一管理知识库操作
- 移除直接 ChromaDB 操作，避免与 rag_core 逻辑重复
- 保留原有的分类检测和批量添加功能
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
from rag_config import DOCUMENTS_DIR, SUPPORTED_EXTENSIONS, logger


def detect_category(file_path: Path) -> str:
    """
    自动检测文档分类
    
    Args:
        file_path: 文件路径
        
    Returns:
        分类名称
    """
    filename = file_path.name.lower()
    parent_dir = file_path.parent.name.lower()
    
    # 基于文件名和目录分类
    if '视频' in filename or 'tutorial' in filename or parent_dir == '视频教程':
        return '视频教程'
    elif '政策' in filename or parent_dir == '政策分析':
        return '政策分析'
    elif '趋势' in filename or parent_dir == '趋势情报':
        return '趋势情报'
    elif 'tavily' in filename or parent_dir == '_tavily_search':
        return 'Tavily搜索'
    elif '科技' in filename or '财经' in filename or parent_dir == '科技财经热点':
        return '科技财经热点'
    else:
        return '其他'


def add_single_document(kb: KnowledgeBase, file_path: Path, category: str = None) -> bool:
    """
    添加单个文档到知识库
    
    Args:
        kb: KnowledgeBase 实例
        file_path: 文件路径
        category: 文档分类（可选，None 表示自动检测）
        
    Returns:
        是否成功
    """
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        return False
    
    try:
        # 自动检测分类
        if category is None:
            category = detect_category(file_path)
        
        # 使用 KnowledgeBase 添加文档
        success = kb.add_document(str(file_path))
        
        if success:
            logger.info(f"✅ 成功添加文档: {file_path.name} (分类: {category})")
        else:
            logger.error(f"❌ 添加文档失败: {file_path.name}")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ 添加文档异常: {e}", exc_info=True)
        return False


def batch_add_documents(kb: KnowledgeBase, folder_path: Path) -> int:
    """
    批量添加文件夹中的所有文档
    
    Args:
        kb: KnowledgeBase 实例
        folder_path: 文件夹路径
        
    Returns:
        成功添加的文件数
    """
    if not folder_path.exists():
        logger.error(f"文件夹不存在: {folder_path}")
        return 0
    
    # 获取支持的文档文件
    doc_files = [f for f in folder_path.rglob('*') 
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    
    logger.info(f"找到 {len(doc_files)} 个支持的文档文件")
    
    success_count = 0
    for doc_file in doc_files:
        if add_single_document(kb, doc_file):
            success_count += 1
    
    logger.info(f"批量添加完成: {success_count}/{len(doc_files)} 成功")
    return success_count


def main():
    """主函数"""
    print("=" * 80)
    print("Knowledge Base Document Add Tool")
    print("=" * 80)
    print()
    
    # 创建知识库实例
    kb = KnowledgeBase()
    
    if len(sys.argv) > 1:
        # 命令行参数指定文档路径
        file_path = Path(sys.argv[1])
        category = sys.argv[2] if len(sys.argv) > 2 else None
        
        if file_path.is_file():
            success = add_single_document(kb, file_path, category)
            if success:
                print("\n[OK] Document added!")
            else:
                print("\n[FAIL] Document add failed!")
                sys.exit(1)
        elif file_path.is_dir():
            print(f"\n[DIR] Detected folder, starting batch add...")
            batch_add_documents(kb, file_path)
        else:
            print(f"[ERROR] Path does not exist: {file_path}")
            sys.exit(1)
    else:
        # Interactive mode
        print("Usage:")
        print("  1. Add single doc: python add_documents.py <path> [category]")
        print("  2. Batch add: python add_documents.py <folder>")
        print()
        print("Examples:")
        print("  python add_documents.py documents/policy/new_policy.txt")
        print("  python add_documents.py documents/video_tutorials")
        print()
        
        file_path_str = input("Please enter document or folder path: ").strip()
        if file_path_str:
            file_path = Path(file_path_str)
            if file_path.is_file():
                category = input("Enter category (press Enter to auto-detect): ").strip()
                category = category if category else None
                add_single_document(kb, file_path, category)
            elif file_path.is_dir():
                batch_add_documents(kb, file_path)


if __name__ == '__main__':
    main()
