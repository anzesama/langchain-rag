#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重建 Wiki 层 - 从所有文档重新扫描实体和关系

用法:
    python rebuild_wiki.py [--docs <目录>] [--batch-size <数量>]
"""
import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Fix GBK encoding
if sys.platform == 'win32':
    import io
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_updater import WikiUpdater
from rag_core.document_loader import load_document, chunk_documents
from rag_config import DOCUMENTS_DIR


def rebuild_wiki(docs_dir=None, batch_size=50):
    """
    重建 Wiki 层
    
    Args:
        docs_dir: 文档目录，默认使用 DOCUMENTS_DIR
        batch_size: 每批处理的文档数
    """
    if docs_dir is None:
        docs_dir = DOCUMENTS_DIR
    
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        print(f"[ERROR] 文档目录不存在: {docs_path}")
        return False
    
    # 初始化 Wiki 更新器
    updater = WikiUpdater()
    
    # 获取所有文档
    supported_exts = ['.txt', '.md', '.pdf', '.docx', '.csv', '.json']
    doc_files = [f for f in docs_path.rglob('*') 
                 if f.is_file() and f.suffix.lower() in supported_exts]
    
    print(f"\n{'='*70}")
    print(f"  Wiki 重建任务")
    print(f"{'='*70}")
    print(f"文档目录: {docs_path}")
    print(f"文档总数: {len(doc_files)}")
    print(f"批次大小: {batch_size}")
    print(f"{'='*70}\n")
    
    if not doc_files:
        print("[WARN] 未找到任何文档")
        return True
    
    # 统计信息
    total_entities = 0
    total_relations = 0
    processed_count = 0
    error_count = 0
    
    start_time = time.time()
    
    # 分批处理
    for i in range(0, len(doc_files), batch_size):
        batch = doc_files[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(doc_files) + batch_size - 1) // batch_size
        
        print(f"[{batch_num}/{total_batches}] 处理批次 {i+1}-{min(i+batch_size, len(doc_files))}...")
        
        for doc_file in batch:
            try:
                # 加载文档
                documents = load_document(doc_file)
                if not documents:
                    print(f"  [SKIP] 无法加载: {doc_file.name}")
                    continue
                
                # 切分文档
                chunks = chunk_documents(documents)
                if not chunks:
                    print(f"  [SKIP] 切分后为空: {doc_file.name}")
                    continue
                
                # 合并文本
                combined_text = "\n".join([c.page_content for c in chunks])
                
                # 提取源文件信息
                rel_key = doc_file.relative_to(docs_path)
                
                # 扫描实体和关系
                stats = updater.batch_add_from_text(
                    text=combined_text,
                    source_chapter=str(rel_key),
                    min_confidence=2
                )
                
                total_entities += stats['entities_added']
                total_relations += stats['relations_added']
                processed_count += 1
                
                if stats['entities_added'] > 0 or stats['relations_added'] > 0:
                    print(f"  [OK] {doc_file.name}: +{stats['entities_added']} 实体, +{stats['relations_added']} 关系")
            
            except Exception as e:
                error_count += 1
                print(f"  [ERROR] {doc_file.name}: {e}")
        
        # 打印进度
        elapsed = time.time() - start_time
        print(f"  进度: {processed_count}/{len(doc_files)} | "
              f"实体: {total_entities} | 关系: {total_relations} | "
              f"耗时: {elapsed:.1f}s\n")
    
    # 完成
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"  Wiki 重建完成")
    print(f"{'='*70}")
    print(f"处理文档: {processed_count} 个")
    print(f"错误: {error_count} 个")
    print(f"新增实体: {total_entities} 个")
    print(f"新增关系: {total_relations} 条")
    print(f"总耗时: {elapsed:.1f} 秒")
    print(f"{'='*70}\n")
    
    return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='重建 Wiki 层')
    parser.add_argument('--docs', type=str, default=None,
                       help='文档目录路径')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='每批处理的文档数')
    
    args = parser.parse_args()
    
    success = rebuild_wiki(
        docs_dir=args.docs,
        batch_size=args.batch_size
    )
    
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
