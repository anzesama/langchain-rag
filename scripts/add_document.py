#!/usr/bin/env python3
"""
通用知识库文档添加脚本（以 add_all_guzhenren.py 为主）
用法:
  1. 添加小说: python add_document.py <小说文件路径>
  2. 添加单个文档: python add_document.py --doc <文档路径>
  3. 批量添加文件夹: python add_document.py --batch <文件夹路径>

断点续传: 自动从进度文件或 ChromaDB 同步状态，无需手动指定 chunks
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

os.environ['TOKENIZERS_PARALLELISM'] = 'false'

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_config import DOCUMENTS_DIR, AUTO_OMP_THREADS, AUTO_EMBEDDING_BATCH_SIZE, SUPPORTED_EXTENSIONS
from rag_core.knowledge_base import KnowledgeBase

# 设置自动计算的线程数
os.environ['OMP_NUM_THREADS'] = str(AUTO_OMP_THREADS)


def detect_category(file_path: Path) -> str:
    """自动检测文档分类"""
    filename = file_path.name.lower()
    parent_dir = file_path.parent.name.lower()
    
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


def add_single_document(file_path: Path) -> bool:
    """添加单个文档到知识库"""
    if not file_path.exists():
        print(f"[FAIL] 文件不存在: {file_path}")
        return False
    
    category = detect_category(file_path)
    print(f"\n[INFO] 添加文档: {file_path.name} (分类: {category})")
    
    kb = KnowledgeBase()
    success = kb.add_document(str(file_path))
    
    if success:
        print(f"[OK] 成功添加文档: {file_path.name}")
    else:
        print(f"[FAIL] 添加文档失败: {file_path.name}")
    
    return success


def batch_add_documents(folder_path: Path) -> int:
    """批量添加文件夹中的所有文档"""
    if not folder_path.exists():
        print(f"[FAIL] 文件夹不存在: {folder_path}")
        return 0
    
    doc_files = [f for f in folder_path.rglob('*') 
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    
    print(f"[INFO] 找到 {len(doc_files)} 个支持的文档文件")
    
    success_count = 0
    for doc_file in doc_files:
        if add_single_document(doc_file):
            success_count += 1
    
    print(f"\n[OK] 批量添加完成: {success_count}/{len(doc_files)} 成功")
    return success_count


def main():
    parser = argparse.ArgumentParser(description="通用知识库文档添加工具")
    parser.add_argument("file", nargs="?", help="小说或文档文件路径")
    parser.add_argument("--doc", type=str, help="添加单个文档")
    parser.add_argument("--batch", type=str, help="批量添加文件夹中的文档")
    args = parser.parse_args()

    # 打印配置信息
    print("=" * 80)
    print("知识库文档添加工具")
    print("=" * 80)
    print(f"[OK] OMP_NUM_THREADS (自动): {AUTO_OMP_THREADS}")
    print(f"[OK] EMBEDDING_BATCH_SIZE (自动): {AUTO_EMBEDDING_BATCH_SIZE}")

    # 模式1: 批量添加文件夹
    if args.batch:
        batch_path = Path(args.batch)
        print(f"\n[INFO] 批量添加模式: {batch_path}")
        batch_add_documents(batch_path)
        return

    # 模式2: 添加单个文档
    if args.doc:
        doc_path = Path(args.doc)
        print(f"\n[INFO] 单文档模式: {doc_path}")
        add_single_document(doc_path)
        return

    # 模式3: 添加小说（默认模式）
    if args.file:
        novel_file = Path(args.file)
        if not novel_file.exists():
            print(f"[FAIL] 文件不存在: {novel_file}")
            sys.exit(1)
        
        print(f"\n[INFO] 添加小说: {novel_file.name}")
        print(f"[OK] 文件大小: {novel_file.stat().st_size / 1024 / 1024:.2f} MB")
        
        kb = KnowledgeBase()
        print("[INFO] 开始添加文档...")
        success = kb.add_document(str(novel_file))
        
        if success:
            final_count = kb.vector_store.get_stats()['total_documents']
            print(f"\n[OK] 添加完成！最终记录数: {final_count}")
        else:
            print("\n[FAIL] 添加失败！")
            sys.exit(1)
        return

    # 无参数：显示帮助
    print("\n用法:")
    print("  1. 添加小说: python add_document.py <小说文件路径>")
    print("  2. 添加单个文档: python add_document.py --doc <文档路径>")
    print("  3. 批量添加: python add_document.py --batch <文件夹路径>")
    print()
    print("示例:")
    print("  python add_document.py documents/蛊真人_精校版.txt")
    print("  python add_document.py --doc documents/policy/new_policy.txt")
    print("  python add_document.py --batch documents/video_tutorials")


if __name__ == '__main__':
    main()
