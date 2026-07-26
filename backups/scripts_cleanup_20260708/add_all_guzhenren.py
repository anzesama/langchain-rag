#!/usr/bin/env python3
"""
一键添加小说到知识库（通用版）
用法: python add_novel.py <小说文件路径> [--chunks=总数]

# 添加任何小说
python add_novel.py "D:/path/to/your_novel.txt"

# 如果知道总 chunk 数，可以指定加速进度判断
python add_novel.py "蛊真人_精校版.txt" --chunks 18738
断点续传不能指定chunks
"""

import sys
import os
import argparse
from pathlib import Path

os.environ['TOKENIZERS_PARALLELISM'] = 'false'

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_config import DOCUMENTS_DIR, AUTO_OMP_THREADS, AUTO_EMBEDDING_BATCH_SIZE
from rag_core.knowledge_base import KnowledgeBase

# 设置自动计算的线程数
os.environ['OMP_NUM_THREADS'] = str(AUTO_OMP_THREADS)
print(f"🧵 OMP_NUM_THREADS (自动): {AUTO_OMP_THREADS}")
print(f"📦 EMBEDDING_BATCH_SIZE (自动): {AUTO_EMBEDDING_BATCH_SIZE}")


def check_completion(kb: KnowledgeBase, total_chunks_estimate: int = None) -> tuple:
    from pathlib import Path
    coll = kb.vector_store.vectorstore._collection
    current_count = coll.count()
    
    # 尝试从进度文件读取
    progress_files = list(Path('storage').glob('progress_*.json'))
    total_chunks = total_chunks_estimate or 0
    if progress_files:
        import json
        try:
            with open(progress_files[0], 'r', encoding='utf-8') as f:
                progress = json.load(f)
                total_chunks = progress.get('total_chunks', total_chunks)
        except:
            pass
    
    is_complete = current_count >= total_chunks if total_chunks > 0 else False
    return current_count, total_chunks, is_complete


def main():
    parser = argparse.ArgumentParser(description="添加任意小说到知识库")
    parser.add_argument("file", help="小说文件路径")
    parser.add_argument("--chunks", type=int, default=0, help="预估总 chunk 数（可选，不提供则自动检测）")
    args = parser.parse_args()

    novel_file = Path(args.file)
    if not novel_file.exists():
        print(f"❌ 文件不存在: {novel_file}")
        sys.exit(1)

    print("=" * 80)
    print(f"添加小说: {novel_file.name}")
    print("=" * 80)
    print(f"📁 文件大小: {novel_file.stat().st_size / 1024 / 1024:.2f} MB")

    kb = KnowledgeBase()
    current_count, total_chunks, is_complete = check_completion(kb, args.chunks)
    print(f"📊 当前进度: {current_count}/{total_chunks if total_chunks > 0 else '未知'} ({current_count/ total_chunks*100 if total_chunks > 0 else 0:.1f}%)")
    
    if is_complete:
        print("✅ 所有 chunk 已添加完成！")
        return

    print("🚀 开始添加文档...")
    success = kb.add_document(str(novel_file))
    
    if success:
        print("✅ 添加完成！")
        final_count, _, _ = check_completion(kb, total_chunks)
        print(f"📊 最终记录数: {final_count}")
    else:
        print("❌ 添加失败！")
        sys.exit(1)

if __name__ == '__main__':
    main()