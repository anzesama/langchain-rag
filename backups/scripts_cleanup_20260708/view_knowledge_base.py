#!/usr/bin/env python3
"""
知识库内容查看工具
用法: python view_knowledge_base.py
"""
import sys
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from rag_core.knowledge_base import KnowledgeBase

def main():
    kb = KnowledgeBase(auto_import=False, auto_build_parent=False)
    
    # 获取统计信息
    stats = kb.get_stats()
    print("=" * 60)
    print("Knowledge Base Statistics")
    print("=" * 60)
    print(f"Total docs: {stats.get('total_documents', 0)}")
    print(f"Storage path: {stats.get('persist_dir', 'N/A')}")
    
    # 获取小说状态
    novel = kb.get_novel_status()
    print(f"\nNovel Status")
    print(f"Global counter: {novel.get('global_counter', 0)}")
    print(f"LSH total vectors: {novel.get('lsh_total_vectors', 0)}")
    
    # 获取文档列表（前 30 条）
    docs = kb.list_documents()
    print(f"\nDocument List (first 30)")
    print("-" * 60)
    
    # 统计来源文件
    sources = {}
    for doc in docs:
        source = doc.get('source', 'unknown')
        basename = os.path.basename(source) if source != 'unknown' else source
        sources[basename] = sources.get(basename, 0) + 1
    
    print(f"\nSource Files ({len(sources)} files total)")
    print("-" * 60)
    
    # 按文档数排序
    sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
    
    for i, (name, count) in enumerate(sorted_sources[:30]):
        print(f"{i+1:2d}. {name} ({count} chunks)")
    
    if len(sorted_sources) > 30:
        print(f"... plus {len(sorted_sources)-30} more files")
    
    # 搜索测试
    print(f"\nSearch Tests")
    print("-" * 60)
    
    queries = ["方源", "修仙", "资源"]
    for query in queries:
        results = kb.search_raw(query, top_k=3, score_threshold=0.1)
        print(f"\nQuery '{query}': {len(results)} results")
        for i, r in enumerate(results[:2]):
            content = r.get('content', '')[:100]
            source = r.get('source', 'unknown')
            score = r.get('score', 0)
            print(f"  {i+1}. [{score:.3f}] {source}")
            print(f"     {content}...")

if __name__ == '__main__':
    main()
