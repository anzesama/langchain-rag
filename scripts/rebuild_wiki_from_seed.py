#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重建 Wiki 层 - 使用 seed.json 作为基准，增量提取关系

用法:
    python rebuild_wiki_from_seed.py
"""
import sys
import os
import time
import json
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

from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_core.document_loader import load_document, chunk_documents
from rag_config import NOVEL_CHAPTERS_DIR, logger


def load_seed_entities(seed_file: str = None) -> dict:
    """
    加载 seed.json 中的实体

    Returns:
        实体字典: {name: {type, properties, aliases}}
    """
    if seed_file is None:
        seed_file = project_root / "data" / "wiki" / "seed.json"

    seed_path = Path(seed_file)

    if not seed_path.exists():
        logger.warning(f"seed.json 不存在: {seed_path}")
        return {}

    with open(seed_path, 'r', encoding='utf-8') as f:
        seed_data = json.load(f)

    # 构建实体字典（只提取 name, type, properties）
    entities = {}
    for entity in seed_data.get('entities', []):
        name = entity.get('name')
        if name:
            entities[name] = {
                'type': entity.get('type', '未分类'),
                'properties': entity.get('properties', {}),
                'aliases': entity.get('aliases', [])
            }

    logger.info(f"从 seed.json 加载了 {len(entities)} 个实体")
    return entities


def rebuild_wiki_from_seed(chapters_dir=None, batch_size=50):
    """
    从小说章节重建 Wiki 层（使用 seed.json 基准）

    Args:
        chapters_dir: 小说章节目录
        batch_size: 每批处理的章节数
    """
    if chapters_dir is None:
        chapters_dir = NOVEL_CHAPTERS_DIR

    chapters_path = Path(chapters_dir)
    if not chapters_path.exists():
        print(f"[ERROR] 小说章节目录不存在: {chapters_path}")
        return False

    # 加载 seed.json 中的实体
    seed_entities = load_seed_entities()
    if not seed_entities:
        print("[WARN] 未加载到 seed.json 实体，将使用默认模式")

    # 初始化 Wiki 数据库
    from rag_core import wiki_db as wiki_db_module
    wiki_db_module._wiki_db_instance = None
    wiki_db = get_wiki_db()

    print(f"\n{'='*70}")
    print(f"  Wiki 重建任务（基于 seed.json）")
    print(f"{'='*70}")
    print(f"章节目录: {chapters_path}")
    print(f"章节总数: {len(list(chapters_path.glob('*.txt')))}")
    print(f"Seed 实体数: {len(seed_entities)}")
    print(f"批次大小: {batch_size}")
    print(f"{'='*70}\n")

    # 获取所有小说章节
    chapter_files = sorted([f for f in chapters_path.glob('*.txt')])

    # 统计信息
    total_entities = len(seed_entities)
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
                    continue

                # 切分章节
                chunks = chunk_documents(documents)
                if not chunks:
                    continue

                # 合并文本
                combined_text = "\n".join([c.page_content for c in chunks])

                # 提取章节号
                chapter_name = chapter_file.stem.replace('chapter_', '')
                source_chapter = f"第{chapter_name}章"

                # 提取关系（只提取与 seed 实体相关的关系）
                relations_added = extract_relations_from_text(
                    combined_text,
                    source_chapter,
                    seed_entities,
                    wiki_db
                )

                total_relations += relations_added
                processed_count += 1

                if relations_added > 0:
                    print(f"  [OK] {chapter_file.name}: +{relations_added} 关系")

            except Exception as e:
                error_count += 1
                print(f"  [ERROR] {chapter_file.name}: {e}")

        # 打印进度
        elapsed = time.time() - start_time
        print(f"  进度: {processed_count}/{len(chapter_files)} | "
              f"关系: {total_relations} | "
              f"耗时: {elapsed:.1f}s\n")

    # 完成
    elapsed = time.time() - start_time

    print(f"\n{'='*70}")
    print(f"  Wiki 重建完成")
    print(f"{'='*70}")
    print(f"处理章节: {processed_count} 个")
    print(f"错误: {error_count} 个")
    print(f"新增关系: {total_relations} 条")
    print(f"总耗时: {elapsed:.1f} 秒")
    print(f"{'='*70}\n")

    # 生成知识图谱
    from scripts import wiki_graph_web
    wiki_graph_web.generate_html()
    print("[OK] 知识图谱已重新生成")

    return True


def extract_relations_from_text(text, source_chapter, seed_entities, wiki_db):
    """
    从文本中提取与 seed 实体相关的关系

    Args:
        text: 文本内容
        source_chapter: 来源章节
        seed_entities: seed 实体字典
        wiki_db: Wiki 数据库

    Returns:
        关系列表数量
    """
    import re

    relations_added = 0

    # 关系模式（直接匹配已知实体，不使用捕获组）
    # 注意：所有实体必须已经在 seed_entities 中定义
    relation_patterns = [
        # 方源相关
        (r'方源持有(.+?)', ['持有']),
        (r'方源拥有(.+?)', ['持有']),
        (r'方源是(.+?)', ['属于']),
        (r'方源主修(.+?)', ['主修']),
        (r'方源修炼(.+?)', ['主修']),
        (r'方源师从(.+?)', ['师承']),
        (r'方源拜(.+?)为师', ['师承']),
        (r'方源与(.+?)结盟', ['盟友']),
        (r'方源与(.+?)联手', ['盟友']),
        (r'方源与(.+?)对抗', ['敌对']),
        (r'方源击杀(.+?)', ['击杀']),
        (r'方源使用(.+?)', ['使用']),
        (r'方源控制(.+?)', ['控制']),
        (r'方源背叛(.+?)', ['背叛']),
        (r'方源被(.+?)背叛', ['背叛']),
        # 春秋蝉相关
        (r'春秋蝉持有(.+?)', ['持有']),
        (r'春秋蝉拥有(.+?)', ['持有']),
        (r'春秋蝉是(.+?)', ['属于']),
        (r'春秋蝉主修(.+?)', ['主修']),
        # 力道相关
        (r'力道持有(.+?)', ['持有']),
        (r'力道拥有(.+?)', ['持有']),
        (r'力道是(.+?)', ['属于']),
        (r'力道主修(.+?)', ['主修']),
        # 奴道相关
        (r'奴道持有(.+?)', ['持有']),
        (r'奴道拥有(.+?)', ['持有']),
        (r'奴道是(.+?)', ['属于']),
        (r'奴道主修(.+?)', ['主修']),
        # 狐仙福地相关
        (r'狐仙福地持有(.+?)', ['持有']),
        (r'狐仙福地拥有(.+?)', ['持有']),
        (r'狐仙福地是(.+?)', ['属于']),
        # 荡魂山相关
        (r'荡魂山持有(.+?)', ['持有']),
        (r'荡魂山拥有(.+?)', ['持有']),
        (r'荡魂山是(.+?)', ['属于']),
        # 白凝冰相关
        (r'白凝冰持有(.+?)', ['持有']),
        (r'白凝冰拥有(.+?)', ['持有']),
        (r'白凝冰是(.+?)', ['属于']),
        # 商心慈相关
        (r'商心慈持有(.+?)', ['持有']),
        (r'商心慈拥有(.+?)', ['持有']),
        (r'商心慈是(.+?)', ['属于']),
        # 元始仙尊相关
        (r'元始仙尊持有(.+?)', ['持有']),
        (r'元始仙尊拥有(.+?)', ['持有']),
        (r'元始仙尊是(.+?)', ['属于']),
        (r'元始仙尊主修(.+?)', ['主修']),
        (r'元始仙尊师从(.+?)', ['师承']),
        # 星宿仙尊相关
        (r'星宿仙尊持有(.+?)', ['持有']),
        (r'星宿仙尊拥有(.+?)', ['持有']),
        (r'星宿仙尊是(.+?)', ['属于']),
        (r'星宿仙尊主修(.+?)', ['主修']),
        (r'星宿仙尊师从(.+?)', ['师承']),
        # 红莲魔尊相关
        (r'红莲魔尊持有(.+?)', ['持有']),
        (r'红莲魔尊拥有(.+?)', ['持有']),
        (r'红莲魔尊是(.+?)', ['属于']),
        (r'红莲魔尊主修(.+?)', ['主修']),
        (r'红莲魔尊师从(.+?)', ['师承']),
    ]

    # 提取所有可能的实体
    all_entity_names = set(seed_entities.keys())

    for rel_type, patterns in relation_patterns:
        for pattern in patterns:
            matches = re.findall(pattern, text)

            for match in matches:
                # match 是捕获组中的文本
                target = match.strip() if match.strip() else ''

                # 检查目标是否在 seed 实体列表中
                if target and target in all_entity_names:
                    source = '方源'  # 默认源为方源（从 seed.json 关系推断）

                    try:
                        # 确保实体存在
                        if not wiki_db.entity_exists(source):
                            wiki_db.add_entity(source, seed_entities[source]['type'], source_chapter=source_chapter)
                        if not wiki_db.entity_exists(target):
                            wiki_db.add_entity(target, seed_entities[target]['type'], source_chapter=source_chapter)

                        # 添加关系
                        wiki_db.add_relationship(
                            source_name=source,
                            target_name=target,
                            rel_type=rel_type,
                            source_chapter=source_chapter
                        )
                        relations_added += 1
                    except Exception as e:
                        pass

    return relations_added


def main():
    """主函数"""
    success = rebuild_wiki_from_seed(batch_size=100)
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
