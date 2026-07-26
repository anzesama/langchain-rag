#!/usr/bin/env python3
"""
知识库状态检查脚本
用法: python check_knowledge_base.py

重构说明:
- 使用 KnowledgeBase 类获取统计信息
- 移除直接 ChromaDB 操作，使用 KnowledgeBase.list_documents()
- 保留原有的目录检查和存储使用情况检查
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# 设置标准输出编码
sys.stdout.reconfigure(encoding='utf-8')

# 设置环境变量避免 segfault
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# 添加项目根目录到路径（scripts/ 的父目录）
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_core.knowledge_base import KnowledgeBase
from rag_config import DOCUMENTS_DIR, NOVEL_CHAPTERS_DIR, STORAGE_DIR, logger


def check_knowledge_base_status(kb: KnowledgeBase) -> dict:
    """
    检查知识库状态
    
    Args:
        kb: KnowledgeBase 实例
        
    Returns:
        知识库状态字典
    """
    try:
        # 获取统计信息
        stats = kb.get_stats()
        
        # 获取小说状态
        novel_status = kb.get_novel_status()
        
        return {
            'stats': stats,
            'novel_status': novel_status,
            'status': 'normal'
        }
    except Exception as e:
        logger.error(f"检查知识库状态失败: {e}")
        return {
            'stats': {},
            'novel_status': {},
            'status': 'error',
            'error': str(e)
        }


def print_knowledge_base_status(status: dict):
    """打印知识库状态"""
    print("\n" + "="*60)
    print("📚 知识库状态检查")
    print("="*60)
    
    if status['status'] == 'error':
        print(f"❌ 检查失败: {status.get('error', '未知错误')}")
        return
    
    stats = status.get('stats', {})
    print(f"✅ 知识库状态: 正常")
    print(f"📊 文档总数: {stats.get('total_documents', 0)}")
    print(f"💾 存储路径: {stats.get('persist_dir', 'N/A')}")
    
    # 打印小说状态
    novel_status = status.get('novel_status', {})
    if novel_status:
        print("\n📖 小说加载状态:")
        print(f"   全局计数器: {novel_status.get('global_counter', 0)}")
        print(f"   LSH 总向量: {novel_status.get('lsh_total_vectors', 0)}")


def check_source_files():
    """检查源文件状态"""
    print("\n" + "="*60)
    print("📁 源文件状态检查")
    print("="*60)
    
    # 检查 documents 目录
    docs_path = DOCUMENTS_DIR
    if docs_path.exists():
        doc_files = list(docs_path.rglob('*'))
        file_count = len([f for f in doc_files if f.is_file()])
        print(f"📄 源文档目录: {file_count} 个文件")
    else:
        print("❌ 源文档目录不存在")
    
    # 检查 novel_chapters 目录
    if NOVEL_CHAPTERS_DIR:
        novel_chapters_path = NOVEL_CHAPTERS_DIR
        if novel_chapters_path.exists():
            chapter_files = list(novel_chapters_path.glob('*.txt'))
            print(f"📖 小说章节目录: {len(chapter_files)} 个文件")
        else:
            print("❌ 小说章节目录不存在")


def check_storage_usage():
    """检查存储使用情况"""
    print("\n" + "="*60)
    print("💾 存储使用情况")
    print("="*60)
    
    if STORAGE_DIR.exists():
        total_size = sum(f.stat().st_size for f in STORAGE_DIR.rglob('*') if f.is_file())
        print(f"📊 存储总用量: {total_size / (1024*1024):.2f} MB")
        
        # 各目录大小
        for item in STORAGE_DIR.iterdir():
            if item.is_dir():
                item_size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                print(f"   {item.name}: {item_size / (1024*1024):.2f} MB")
    else:
        print("❌ 存储目录不存在")


def main():
    """主函数"""
    print("="*60)
    print("🔍 知识库状态检查工具")
    print("="*60)
    print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 创建知识库实例
    kb = KnowledgeBase(auto_import=False, auto_build_parent=False)
    
    # 检查知识库状态
    status = check_knowledge_base_status(kb)
    print_knowledge_base_status(status)
    
    # 检查源文件状态
    check_source_files()
    
    # 检查存储使用情况
    check_storage_usage()
    
    print("\n" + "="*60)
    print("✅ 检查完成!")
    print("="*60)


if __name__ == '__main__':
    main()
