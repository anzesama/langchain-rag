"""
Wiki 种子数据加载脚本

功能：
- 从 seed.json 加载初始实体和关系到 Wiki 数据库
- 支持增量加载（跳过已存在的实体）
- 提供加载报告
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.wiki_db import WikiDB, get_wiki_db

logger = logging.getLogger(__name__)


class SeedLoader:
    """
    种子数据加载器
    
    用法:
        loader = SeedLoader()
        loader.load("data/wiki/seed.json")
    """

    def __init__(self, wiki_db: WikiDB = None):
        """
        初始化加载器
        
        Args:
            wiki_db: Wiki 数据库实例（可选，默认使用全局实例）
        """
        self.wiki_db = wiki_db or get_wiki_db()
        self._stats = {
            "entities_total": 0,
            "entities_added": 0,
            "entities_skipped": 0,
            "relations_total": 0,
            "relations_added": 0,
            "relations_skipped": 0
        }
        self._id_to_name = {}  # ID 到名称的映射

    def load(self, seed_file: str = None) -> Dict[str, int]:
        """
        加载种子数据
        
        Args:
            seed_file: 种子文件路径
            
        Returns:
            加载统计
        """
        if seed_file is None:
            seed_file = "data/wiki/seed.json"
        
        seed_path = Path(seed_file)
        
        if not seed_path.exists():
            logger.error(f"种子文件不存在: {seed_file}")
            return self._stats
        
        logger.info(f"加载种子文件: {seed_file}")
        
        with open(seed_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        entities = data.get('entities', [])
        relationships = data.get('relationships', [])
        
        # 构建 ID 到名称的映射
        for entity in entities:
            entity_id = entity.get('id')
            entity_name = entity.get('name')
            if entity_id and entity_name:
                self._id_to_name[entity_id] = entity_name
        
        self._stats['entities_total'] = len(entities)
        self._stats['relations_total'] = len(relationships)
        
        # 加载实体
        logger.info(f"开始加载 {len(entities)} 个实体...")
        for entity in entities:
            self._add_entity(entity)
        
        # 加载关系
        logger.info(f"开始加载 {len(relationships)} 个关系...")
        for rel in relationships:
            self._add_relationship(rel)
        
        logger.info(f"种子数据加载完成!")
        return self._stats

    def _add_entity(self, entity_data: Dict[str, Any]) -> bool:
        """
        添加单个实体
        
        Args:
            entity_data: 实体数据
            
        Returns:
            是否成功
        """
        name = entity_data.get('name')
        entity_type = entity_data.get('type', '未分类')
        properties = entity_data.get('properties', {})
        aliases = entity_data.get('aliases', [])
        source_chapter = entity_data.get('source_chapter')
        
        # 检查是否已存在
        if self.wiki_db.entity_exists(name):
            logger.debug(f"实体已存在，跳过: {name}")
            self._stats['entities_skipped'] += 1
            return False
        
        # 添加实体
        try:
            self.wiki_db.add_entity(
                name=name,
                entity_type=entity_type,
                properties=properties,
                aliases=aliases if aliases else None,
                source_chapter=source_chapter
            )
            
            self._stats['entities_added'] += 1
            logger.debug(f"实体已添加: {name} ({entity_type})")
            return True
            
        except Exception as e:
            logger.error(f"添加实体失败 {name}: {e}")
            return False

    def _add_relationship(self, rel_data: Dict[str, Any]) -> bool:
        """
        添加单个关系
        
        Args:
            rel_data: 关系数据
            
        Returns:
            是否成功
        """
        source = rel_data.get('source')
        target = rel_data.get('target')
        rel_type = rel_data.get('rel_type', '未知')
        source_chapter = rel_data.get('source_chapter')
        
        # 检查 source 和 target 是否是 ID（如 fang_yuan）还是名称（如 方源）
        # 如果是 ID，需要转换为名称
        if source.startswith('entity_') or source.islower():
            # 可能是 ID，尝试查找对应的名称
            source_name = self._find_entity_name_by_id(source)
            if source_name:
                source = source_name
        
        if target.startswith('entity_') or target.islower():
            # 可能是 ID，尝试查找对应的名称
            target_name = self._find_entity_name_by_id(target)
            if target_name:
                target = target_name
        
        # 检查源实体和目标实体是否存在
        if not self.wiki_db.entity_exists(source):
            logger.warning(f"源实体不存在，跳过关系: {source}")
            self._stats['relations_skipped'] += 1
            return False
        
        if not self.wiki_db.entity_exists(target):
            logger.warning(f"目标实体不存在，跳过关系: {target}")
            self._stats['relations_skipped'] += 1
            return False
        
        # 添加关系
        try:
            self.wiki_db.add_relationship(
                source_name=source,
                target_name=target,
                rel_type=rel_type,
                source_chapter=source_chapter
            )
            
            self._stats['relations_added'] += 1
            logger.debug(f"关系已添加: {source} -{rel_type}-> {target}")
            return True
            
        except Exception as e:
            logger.error(f"添加关系失败: {e}")
            return False

    def _find_entity_name_by_id(self, entity_id: str) -> str:
        """
        根据实体 ID 查找实体名称
        
        Args:
            entity_id: 实体 ID
            
        Returns:
            实体名称，如果找不到则返回 None
        """
        # 使用内存中的映射
        return self._id_to_name.get(entity_id)

    def get_stats(self) -> Dict[str, int]:
        """
        获取加载统计
        
        Returns:
            统计信息
        """
        return self._stats.copy()

    def print_report(self):
        """
        打印加载报告
        """
        print("\n" + "=" * 60)
        print("种子数据加载报告")
        print("=" * 60)
        
        print(f"\n实体统计:")
        print(f"  总计: {self._stats['entities_total']}")
        print(f"  已添加: {self._stats['entities_added']}")
        print(f"  已跳过: {self._stats['entities_skipped']}")
        
        print(f"\n关系统计:")
        print(f"  总计: {self._stats['relations_total']}")
        print(f"  已添加: {self._stats['relations_added']}")
        print(f"  已跳过: {self._stats['relations_skipped']}")
        
        print("\n" + "=" * 60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="加载 Wiki 种子数据"
    )
    parser.add_argument(
        '--seed-file',
        type=str,
        default='data/wiki/seed.json',
        help='种子文件路径 (默认: data/wiki/seed.json)'
    )
    
    args = parser.parse_args()
    
    # 初始化加载器
    loader = SeedLoader()
    
    # 加载数据
    stats = loader.load(args.seed_file)
    
    # 打印报告
    loader.print_report()


if __name__ == "__main__":
    main()
