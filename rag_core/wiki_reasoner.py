"""
Wiki 推理引擎 - 自动推导新关系和实体属性

功能：
- 基于现有实体关系自动推导新关系
- 基于关系推导实体属性（核心新功能）
- 支持规则引擎和置信度评分
- 推导结果进入待审核队列

核心规则：
1. 持有→主修：如果 X 持有 Y，且 Y 属于 Z 流派，则 X 主修 Z
2. 师承→师兄弟：如果 X 与 Y 师从同一人，则 X 与 Y 是师兄弟
3. 持有→拥有：如果 X 持有 Y，则 X 拥有 Y（默认关系）
4. 持有蛊虫→获得功能：如果 X 持有 Y，且 Y 有"功能"属性，则 X 获得该能力
5. 师承→继承：如果 X 师承 Y，且 Y 有特定属性，X 可能继承
"""

import re
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

from rag_core.wiki_db import WikiDB, get_wiki_db

logger = logging.getLogger(__name__)


class WikiReasoner:
    """
    Wiki 推理引擎

    用法:
        reasoner = WikiReasoner()
        reasoner.analyze_all_entities()
        reasoner.get_deduced_relations()
    """

    def __init__(self, wiki_db: WikiDB = None):
        """
        初始化推理引擎

        Args:
            wiki_db: Wiki 数据库实例（可选，默认使用全局实例）
        """
        self.wiki_db = wiki_db or get_wiki_db()
        self._rules = self._init_rules()

    def _init_rules(self) -> List[Dict]:
        """
        初始化推理规则

        规则格式：
        {
            "name": "规则名称",
            "description": "规则描述",
            "condition": lambda src, tgt, rels: bool,
            "deduce": lambda src, tgt, rels: {
                "rel_type": "关系类型",
                "properties": {"reason": "推导原因"},
                "confidence": 0.8
            }
        }
        """
        return [
            # ==================== 关系推导规则 ====================
            {
                "name": "持有→主修",
                "description": "如果 X 持有 Y，且 Y 属于 Z 流派，则 X 主修 Z",
                "condition": self._condition_hold_to_main,
                "deduce": self._deduce_hold_to_main,
                "confidence": 0.7
            },
            {
                "name": "师承→师兄弟",
                "description": "如果 X 与 Y 师从同一人，则 X 与 Y 是师兄弟",
                "condition": self._condition_mentorship_to_brother,
                "deduce": self._deduce_mentorship_to_brother,
                "confidence": 0.8
            },
            {
                "name": "持有→拥有",
                "description": "如果 X 持有 Y，则 X 拥有 Y（默认关系）",
                "condition": self._condition_hold_to_own,
                "deduce": self._deduce_hold_to_own,
                "confidence": 0.9
            },
            {
                "name": "盟友→联盟",
                "description": "如果 X 与 Y 是盟友，则 X 与 Y 是联盟关系",
                "condition": self._condition_ally_to_union,
                "deduce": self._deduce_ally_to_union,
                "confidence": 0.7
            },
            # ==================== 属性推导规则（新增） ====================
            {
                "name": "持有蛊虫→获得功能",
                "description": "如果 X 持有 Y（蛊虫），且 Y 有'功能'属性，则 X 获得该能力",
                "condition": self._condition_hold_gu_function,
                "deduce": self._deduce_hold_gu_function,
                "confidence": 0.8
            },
            {
                "name": "持有蛊虫→获得境界",
                "description": "如果 X 持有 Y（蛊虫），且 Y 有'境界'属性，则 X 获得对应境界信息",
                "condition": self._condition_hold_gu_rank,
                "deduce": self._deduce_hold_gu_rank,
                "confidence": 0.7
            },
            {
                "name": "师承→继承流派",
                "description": "如果 X 师承 Y，且 Y 有'主修'属性，则 X 可能继承该流派",
                "condition": self._condition_mentorship_inherit,
                "deduce": self._deduce_mentorship_inherit,
                "confidence": 0.5
            },
            {
                "name": "持有流派→获得特点",
                "description": "如果 X 持有/主修 Y（流派），且 Y 有'特点'属性，则 X 获得该特点",
                "condition": self._condition_hold_road_trait,
                "deduce": self._deduce_hold_road_trait,
                "confidence": 0.75
            }
        ]

    # ==================== 属性推导规则（新增） ====================

    def _condition_hold_gu_function(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则5: 持有蛊虫→获得功能

        条件: X 持有 Y（蛊虫），且 Y 有'功能'属性
        """
        # 检查是否持有关系
        has_hold_rel = any(
            r['rel_type'] == '持有' and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_hold_rel:
            return False

        # 检查 Y 是否有功能属性
        entity = self.wiki_db.get_entity(tgt)
        if not entity or not entity.get('properties'):
            return False

        properties = entity['properties']
        return '功能' in properties or '效果' in properties

    def _deduce_hold_gu_function(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 获得 Y 的功能
        """
        entity = self.wiki_db.get_entity(tgt)
        properties = entity['properties']

        # 提取功能或效果
        function = properties.get('功能', properties.get('效果', '未知'))

        return {
            "rel_type": "持有",
            "properties": {
                "reason": f"{src}持有{tgt}，且{tgt}具有{function}功能，故{src}获得该能力",
                "deduced_from": f"持有 {tgt}",
                "inferred_property": {"能力": function}
            },
            "confidence": 0.8
        }

    def _condition_hold_gu_rank(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则6: 持有蛊虫→获得境界

        条件: X 持有 Y（蛊虫），且 Y 有'境界'属性
        """
        # 检查是否持有关系
        has_hold_rel = any(
            r['rel_type'] == '持有' and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_hold_rel:
            return False

        # 检查 Y 是否有境界属性
        entity = self.wiki_db.get_entity(tgt)
        if not entity or not entity.get('properties'):
            return False

        properties = entity['properties']
        return '境界' in properties

    def _deduce_hold_gu_rank(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 获得 Y 的境界信息
        """
        entity = self.wiki_db.get_entity(tgt)
        properties = entity['properties']

        rank = properties.get('境界', '未知')

        return {
            "rel_type": "持有",
            "properties": {
                "reason": f"{src}持有{tgt}，且{tgt}为{rank}，故{src}掌握该境界蛊虫",
                "deduced_from": f"持有 {tgt}",
                "inferred_property": {"掌握境界": rank}
            },
            "confidence": 0.7
        }

    def _condition_mentorship_inherit(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则7: 师承→继承流派

        条件: X 师承 Y，且 Y 有'主修'属性
        """
        # 检查是否有师承关系
        has_mentorship = any(
            r['rel_type'] == '师承' and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_mentorship:
            return False

        # 检查 Y 是否有主修属性
        entity = self.wiki_db.get_entity(tgt)
        if not entity or not entity.get('properties'):
            return False

        properties = entity['properties']
        return '主修' in properties

    def _deduce_mentorship_inherit(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 可能继承 Y 的流派
        """
        entity = self.wiki_db.get_entity(tgt)
        properties = entity['properties']

        main_road = properties.get('主修', '未知')

        return {
            "rel_type": "师承",
            "properties": {
                "reason": f"{src}师从{tgt}，且{tgt}主修{main_road}，故{src}可能继承{main_road}",
                "deduced_from": f"师承 {tgt}",
                "inferred_property": {"可能继承流派": main_road}
            },
            "confidence": 0.5
        }

    def _condition_hold_road_trait(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则8: 持有流派→获得特点

        条件: X 持有/主修 Y（流派），且 Y 有'特点'属性
        """
        # 检查是否持有或主修关系
        has_rel = any(
            (r['rel_type'] in ['持有', '主修']) and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_rel:
            return False

        # 检查 Y 是否有特点属性
        entity = self.wiki_db.get_entity(tgt)
        if not entity or not entity.get('properties'):
            return False

        properties = entity['properties']
        return '特点' in properties

    def _deduce_hold_road_trait(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 获得 Y 的特点
        """
        entity = self.wiki_db.get_entity(tgt)
        properties = entity['properties']

        trait = properties.get('特点', '未知')
        advantage = properties.get('优势', '')

        desc = trait
        if advantage:
            desc += f"，优势：{advantage}"

        return {
            "rel_type": "主修",
            "properties": {
                "reason": f"{src}主修{tgt}，且{tgt}的特点是{desc}，故{src}具备该特点",
                "deduced_from": f"主修 {tgt}",
                "inferred_property": {"流派特点": trait, "流派优势": advantage}
            },
            "confidence": 0.75
        }

    def _condition_hold_to_main(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则1: 持有→主修

        条件: X 持有 Y，且 Y 的属性包含流派信息
        """
        # 检查是否持有关系
        has_hold_rel = any(
            r['rel_type'] == '持有' and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_hold_rel:
            return False

        # 检查 Y 是否有流派属性
        entity = self.wiki_db.get_entity(tgt)
        if not entity or not entity.get('properties'):
            return False

        properties = entity['properties']
        has_road_type = any(
            k in properties and properties[k].lower() in ['力道', '空间道', '时间道', '血道', '地水火风道', '天道', '奴道']
            for k in properties.keys()
        )

        return has_road_type

    def _deduce_hold_to_main(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 主修 Y 所属流派
        """
        entity = self.wiki_db.get_entity(tgt)
        properties = entity['properties']

        # 查找流派属性
        road_type = None
        for k, v in properties.items():
            if v.lower() in ['力道', '空间道', '时间道', '血道', '地水火风道', '天道', '奴道']:
                road_type = v
                break

        if not road_type:
            road_type = "未知流派"

        return {
            "rel_type": "主修",
            "properties": {
                "reason": f"{src}持有{tgt}，且{tgt}属于{road_type}，故{src}主修{road_type}",
                "deduced_from": f"持有 {tgt}"
            },
            "confidence": 0.7
        }

    def _condition_mentorship_to_brother(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则2: 师承→师兄弟

        条件: X 与 Y 师从同一人
        """
        # 检查是否有师承关系
        has_mentorship = any(
            r['rel_type'] == '师承' and r['source'] == src and r['target'] == tgt
            for r in rels
        )
        if not has_mentorship:
            return False

        # 检查是否有反向师承关系（X 是 Y 的徒弟）
        has_reverse_mentorship = any(
            r['rel_type'] == '师承' and r['source'] == tgt and r['target'] == src
            for r in rels
        )
        if not has_reverse_mentorship:
            return False

        return True

    def _deduce_mentorship_to_brother(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 与 Y 是师兄弟
        """
        # 找出共同的师傅
        common_mentor = None
        for r in rels:
            if r['rel_type'] == '师承':
                if r['source'] == src:
                    common_mentor = r['target']
                elif r['source'] == tgt:
                    common_mentor = r['target']

        if not common_mentor:
            common_mentor = "同一师傅"

        return {
            "rel_type": "师兄弟",
            "properties": {
                "reason": f"{src}与{tgt}师从{common_mentor}，故是师兄弟",
                "deduced_from": "师承关系"
            },
            "confidence": 0.8
        }

    def _condition_hold_to_own(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则3: 持有→拥有

        条件: X 持有 Y
        """
        # 检查是否持有关系
        return any(
            r['rel_type'] == '持有' and r['source'] == src and r['target'] == tgt
            for r in rels
        )

    def _deduce_hold_to_own(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 拥有 Y
        """
        return {
            "rel_type": "拥有",
            "properties": {
                "reason": f"{src}持有{tgt}，故{src}拥有{tgt}",
                "deduced_from": "持有关系"
            },
            "confidence": 0.9
        }

    def _condition_ally_to_union(self, src: str, tgt: str, rels: List[Dict]) -> bool:
        """
        规则4: 盟友→联盟

        条件: X 与 Y 是盟友
        """
        # 检查是否有盟友关系
        return any(
            r['rel_type'] == '盟友' and r['source'] == src and r['target'] == tgt
            for r in rels
        )

    def _deduce_ally_to_union(self, src: str, tgt: str, rels: List[Dict]) -> Dict:
        """
        推导: X 与 Y 是联盟
        """
        return {
            "rel_type": "联盟",
            "properties": {
                "reason": f"{src}与{tgt}是盟友，故形成联盟",
                "deduced_from": "盟友关系"
            },
            "confidence": 0.7
        }

    def analyze_all_entities(self) -> List[Dict]:
        """
        对所有实体进行分析，推导新关系和属性

        Returns:
            推导结果列表
        """
        all_entities = self.wiki_db.get_all_entities()
        deduced_relations = []

        for entity in all_entities:
            entity_name = entity['name']
            entity_id = entity['id']

            # 获取实体的所有关系
            relations = self.wiki_db.get_relations(entity_id)

            # 对每个关系，检查是否可以推导新关系
            for rel in relations:
                target_name = rel['target']
                target_id = self.wiki_db.get_entity_id(target_name)

                # 获取目标实体的所有关系
                target_relations = self.wiki_db.get_relations(target_id)

                # 对每个规则进行评估
                for rule in self._rules:
                    # 检查条件是否满足（使用源实体和目标实体）
                    if rule['condition'](entity_name, target_name, relations):
                        # 执行推导
                        deduce_result = rule['deduce'](entity_name, target_name, relations)

                        deduced_relations.append({
                            "rule_name": rule['name'],
                            "rule_description": rule['description'],
                            "confidence": rule['confidence'],
                            "deduced_rel_type": deduce_result['rel_type'],
                            "deduced_properties": deduce_result['properties'],
                            "source_entity": entity_name,
                            "target_entity": target_name,
                            "source_relations": len(relations),
                            "target_relations": len(target_relations)
                        })

        return deduced_relations

    def derive_entity_properties(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        基于关系推导实体属性

        Args:
            entity_name: 实体名称

        Returns:
            推导出的属性列表
        """
        entity = self.wiki_db.get_entity(entity_name)
        if not entity:
            logger.warning(f"实体不存在: {entity_name}")
            return []

        entity_id = entity['id']
        relations = self.wiki_db.get_relations(entity_id)
        
        derived_properties = []
        
        # 遍历所有规则
        for rule in self._rules:
            for rel in relations:
                target_name = rel['target']
                
                if rule['condition'](entity_name, target_name, relations):
                    deduce_result = rule['deduce'](entity_name, target_name, relations)
                    
                    # 检查是否有推导出的属性
                    if 'inferred_property' in deduce_result['properties']:
                        derived_properties.append({
                            "rule_name": rule['name'],
                            "confidence": rule['confidence'],
                            "inferred_properties": deduce_result['properties']['inferred_property'],
                            "reason": deduce_result['properties']['reason'],
                            "source_target": target_name
                        })
        
        return derived_properties

    def apply_derived_properties(self, entity_name: str) -> int:
        """
        应用推导出的属性到实体

        Args:
            entity_name: 实体名称

        Returns:
            应用的属性数量
        """
        derived = self.derive_entity_properties(entity_name)
        if not derived:
            return 0
        
        entity = self.wiki_db.get_entity(entity_name)
        if not entity:
            return 0
        
        current_properties = entity['properties'].copy()
        applied_count = 0
        
        for item in derived:
            for prop_name, prop_value in item['inferred_properties'].items():
                # 如果属性已存在，跳过
                if prop_name in current_properties:
                    continue
                
                # 添加新属性
                current_properties[prop_name] = prop_value
                applied_count += 1
        
        # 更新实体属性
        if applied_count > 0:
            try:
                self.wiki_db.update_entity(entity_name, properties=current_properties)
                logger.info(f"已为 {entity_name} 应用 {applied_count} 个推导属性")
            except Exception as e:
                logger.error(f"更新实体属性失败 {entity_name}: {e}")
        
        return applied_count

    def apply_all_derived_properties(self) -> Dict[str, int]:
        """
        为所有实体应用推导出的属性

        Returns:
            统计信息
        """
        all_entities = self.wiki_db.get_all_entities()
        stats = {
            "total_entities": len(all_entities),
            "entities_with_derivations": 0,
            "total_properties_applied": 0
        }
        
        for entity in all_entities:
            entity_name = entity['name']
            applied = self.apply_derived_properties(entity_name)
            if applied > 0:
                stats['entities_with_derivations'] += 1
                stats['total_properties_applied'] += applied
        
        return stats

    def get_deduced_relations(self) -> List[Dict]:
        """
        获取推导出的新关系

        Returns:
            待审核的关系列表
        """
        deduced = self.analyze_all_entities()

        # 转换为待审核格式
        pending_reviews = []
        for item in deduced:
            pending_reviews.append({
                "entity_id": self.wiki_db.get_entity_id(item['source_entity']),
                "entity_name": item['source_entity'],
                "relation_type": item['deduced_rel_type'],
                "properties": json.dumps(item['deduced_properties'], ensure_ascii=False),
                "confidence": item['confidence'],
                "review_status": "pending"
            })

        return pending_reviews

    def save_deductions_to_pending(self) -> int:
        """
        将推导结果保存到待审核队列

        Returns:
            保存的记录数
        """
        deduced = self.get_deduced_relations()

        saved_count = 0
        for item in deduced:
            try:
                # 检查是否已存在
                entity_id = item['entity_id']
                relation_type = item['relation_type']

                # TODO: 检查是否已存在相同关系
                # 这里简化处理，直接插入

                # 插入待审核队列（使用 with 确保连接正确关闭）
                conn = self.wiki_db.connect()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pending_reviews
                    (entity_id, entity_name, relation_type, properties, confidence, review_status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    entity_id,
                    item['entity_name'],
                    relation_type,
                    item['properties'],
                    item['confidence'],
                    item['review_status']
                ))
                conn.commit()
                cursor.close()
                conn.close()

                saved_count += 1
                logger.info(f"推导结果已保存到待审核队列: {item['entity_name']} -{relation_type}-> ...")

            except Exception as e:
                logger.error(f"保存推导结果失败: {e}")

        return saved_count

    def get_rule_summary(self) -> Dict[str, Any]:
        """
        获取规则执行摘要

        Returns:
            摘要信息
        """
        deduced = self.analyze_all_entities()

        # 按规则分组
        by_rule = {}
        for item in deduced:
            rule_name = item['rule_name']
            if rule_name not in by_rule:
                by_rule[rule_name] = {
                    "count": 0,
                    "total_confidence": 0.0
                }
            by_rule[rule_name]['count'] += 1
            by_rule[rule_name]['total_confidence'] += item['confidence']

        # 计算平均置信度
        summary = {
            "total_deductions": len(deduced),
            "rules": {}
        }

        for rule_name, data in by_rule.items():
            summary["rules"][rule_name] = {
                "count": data['count'],
                "average_confidence": data['total_confidence'] / data['count']
            }

        return summary
