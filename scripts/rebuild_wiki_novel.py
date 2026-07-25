#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重建 Wiki 层 - 仅从小说章节重新扫描实体和关系

用法:
    python rebuild_wiki_novel.py [--chapters <章节目录>]
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

# 数据库路径（使用 rag_config 中的路径逻辑）
from rag_core.wiki_db import WikiDB
wiki_db = WikiDB()  # 会自动计算正确的 db_path

from rag_core.wiki_updater import WikiUpdater
from rag_core.document_loader import load_document, chunk_documents
from rag_config import NOVEL_CHAPTERS_DIR, logger


def rebuild_wiki_from_novel(chapters_dir=None, batch_size=50):
    """
    从小说章节重建 Wiki 层
    
    Args:
        chapters_dir: 小说章节目录，默认使用 NOVEL_CHAPTERS_DIR
        batch_size: 每批处理的章节数
    """
    if chapters_dir is None:
        chapters_dir = NOVEL_CHAPTERS_DIR
    
    chapters_path = Path(chapters_dir)
    if not chapters_path.exists():
        print(f"[ERROR] 小说章节目录不存在: {chapters_path}")
        return False
    
    # 初始化 Wiki 更新器
    updater = WikiUpdater()
    
    # 获取所有小说章节
    chapter_files = sorted([f for f in chapters_path.glob('*.txt')])
    
    # 清理旧数据
    print("\n[清理] 删除旧数据库...")
    if wiki_db.db_path and Path(wiki_db.db_path).exists():
        Path(wiki_db.db_path).unlink()
        print(f"[OK] 已删除旧数据库")
    
    # 重置 WikiDB 单例（强制重新初始化）
    from rag_core import wiki_db as wiki_db_module
    wiki_db_module._wiki_db_instance = None
    
    # 重新初始化 Wiki 更新器（使用新数据库）
    from rag_core.wiki_db import get_wiki_db
    new_wiki_db = get_wiki_db()
    updater = WikiUpdater(wiki_db=new_wiki_db)
    print(f"[OK] 新数据库已初始化")
    
    print(f"\n{'='*70}")
    print(f"  Wiki 重建任务（仅小说章节）")
    print(f"{'='*70}")
    print(f"章节目录: {chapters_path}")
    print(f"章节总数: {len(chapter_files)}")
    print(f"批次大小: {batch_size}")
    print(f"{'='*70}\n")
    
    if not chapter_files:
        print("[WARN] 未找到任何小说章节文件")
        return True
    
    # 统计信息
    total_entities = 0
    total_relations = 0
    processed_count = 0
    error_count = 0
    
    start_time = time.time()
    
    # 分批处理
    for i in range(0, len(chapter_files), batch_size):
        batch = chapter_files[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(chapter_files) + batch_size - 1) // batch_size
        
        print(f"[{batch_num}/{total_batches}] 处理批次 {i+1}-{min(i+batch_size, len(chapter_files))}...")
        
        for chapter_file in batch:
            try:
                # 加载章节
                documents = load_document(chapter_file)
                if not documents:
                    print(f"  [SKIP] 无法加载: {chapter_file.name}")
                    continue
                
                # 切分章节
                chunks = chunk_documents(documents)
                if not chunks:
                    print(f"  [SKIP] 切分后为空: {chapter_file.name}")
                    continue
                
                # 合并文本
                combined_text = "\n".join([c.page_content for c in chunks])
                
                # 提取章节号
                chapter_name = chapter_file.stem.replace('chapter_', '')
                source_chapter = f"第{chapter_name}章"
                
                # 使用 WikiUpdater 的内置方法（已优化过滤）
                stats = updater.batch_add_from_text(
                    text=combined_text,
                    source_chapter=source_chapter,
                    min_confidence=3  # 提高置信度阈值
                )
                
                # 扫描关系
                for rel_type, patterns in updater._rel_patterns.items():
                    for pattern in patterns:
                        matches = re.findall(pattern, combined_text)
                        for match in matches:
                            if isinstance(match, tuple):
                                source = match[0].strip()
                                target = match[1].strip() if len(match) > 1 else ""
                                
                                # 清理和过滤
                                source = source.strip('，。、；""''')
                                target = target.strip('，。、；""''')
                                
                                if not source or not target:
                                    continue
                                if len(source) < 2 or len(target) < 2:
                                    continue
                                if len(source) > 8 or len(target) > 8:
                                    continue
                                if not re.match(r'^[一-龥]{2,8}$', source):
                                    continue
                                if not re.match(r'^[一-龥]{2,8}$', target):
                                    continue
                                
                                relation_key = f"{source}|{rel_type}|{target}"
                                rel_count[relation_key] = rel_count.get(relation_key, 0) + 1
                
                # 添加高置信度关系
                relations_added = 0
                for relation_key, confidence in rel_count.items():
                    if confidence >= 2:
                        parts = relation_key.split("|")
                        source, rel_type, target = parts[0], parts[1], parts[2]
                        
                        # 确保实体存在
                        if not updater.wiki_db.entity_exists(source):
                            updater.wiki_db.add_entity(source, "人物", source_chapter=source_chapter)
                        if not updater.wiki_db.entity_exists(target):
                            updater.wiki_db.add_entity(target, "人物", source_chapter=source_chapter)
                        
                        try:
                            updater.wiki_db.add_relationship(
                                source_name=source,
                                target_name=target,
                                rel_type=rel_type,
                                source_chapter=source_chapter
                            )
                            relations_added += 1
                        except Exception as e:
                            pass
                
                stats = {
                    'entities_added': entities_added,
                    'relations_added': relations_added
                }
                
                total_entities += stats['entities_added']
                total_relations += stats['relations_added']
                processed_count += 1
                
                if stats['entities_added'] > 0 or stats['relations_added'] > 0:
                    print(f"  [OK] {chapter_file.name}: +{stats['entities_added']} 实体, +{stats['relations_added']} 关系")
            
            except Exception as e:
                error_count += 1
                print(f"  [ERROR] {chapter_file.name}: {e}")
        
        # 打印进度
        elapsed = time.time() - start_time
        print(f"  进度: {processed_count}/{len(chapter_files)} | "
              f"实体: {total_entities} | 关系: {total_relations} | "
              f"耗时: {elapsed:.1f}s\n")
    
    # 完成
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"  Wiki 重建完成")
    print(f"{'='*70}")
    print(f"处理章节: {processed_count} 个")
    print(f"错误: {error_count} 个")
    print(f"新增实体: {total_entities} 个")
    print(f"新增关系: {total_relations} 条")
    print(f"总耗时: {elapsed:.1f} 秒")
    print(f"{'='*70}\n")
    
    # 生成知识图谱
    from scripts import wiki_graph_web
    wiki_graph_web.generate_html()
    print("[OK] 知识图谱已重新生成")
    
    return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='从小说章节重建 Wiki 层')
    parser.add_argument('--chapters', type=str, default=None,
                       help='小说章节目录路径')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='每批处理的章节数')
    
    args = parser.parse_args()
    
    success = rebuild_wiki_from_novel(
        chapters_dir=args.chapters,
        batch_size=args.batch_size
    )
    
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
