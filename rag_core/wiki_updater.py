"""
Wiki 增量更新模块 - 半自动化知识更新

功能:
- 扫描新文本中的潜在实体
- 识别实体间的关系
- 提供人工审核接口
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from rag_core.wiki_db import WikiDB, get_wiki_db

logger = logging.getLogger(__name__)


class WikiUpdater:
    """
    Wiki 增量更新管理器

    用法:
        updater = WikiUpdater()
        candidates = updater.scan_new_entities(text, source_chapter="第X章")
        updater.review_candidates(candidates)
    """

    def __init__(self, wiki_db: WikiDB = None, use_uie: bool = False):
        """
        初始化更新器

        Args:
            wiki_db: Wiki 数据库实例(可选,默认使用全局实例)
            use_uie: 是否启用 PaddleNLP UIE 进行实体抽取(默认 False,仅使用正则)
        """
        self.wiki_db = wiki_db or get_wiki_db()
        self.use_uie = use_uie
        self._entity_patterns = self._init_entity_patterns()
        self._rel_patterns = self._init_rel_patterns()
        
        # UIE 模型懒加载
        self.uie_ner = None
        if self.use_uie:
            try:
                from paddlenlp import Taskflow
                logger.info("正在加载 UIE NER 模型(首次约 30-60s)...")
                self.uie_ner = Taskflow("information_extraction", schema=["人物", "蛊虫", "流派", "势力", "地点"])
                logger.info("UIE NER 模型加载成功")
            except Exception as e:
                logger.warning(f"UIE 模型加载失败,将回退到正则模式: {e}")
                self.use_uie = False


            # 激活 Reasoner 并保存推导结果
            from rag_core.wiki_reasoner import WikiReasoner
            self.reasoner = WikiReasoner(self.wiki_db)
            saved_count = self.reasoner.save_deductions_to_pending()
            logger.info(f"已保存 {saved_count} 条推导结果到待审核队列")

    # 常见干扰词列表（匹配后排除）
    # 使用 frozenset 提高查询效率
    _noise_words = {
        # 对话词
        '知道', '难道', '心中', '喊道', '喊', '叫', '道', '说', '说道', '轻声道', '低声道',
        '大喊', '叫道', '回应', '叹道', '问道', '回答', '反问',

        # 副词/形容词
        '慢慢', '静静', '忽然', '顿时', '突然', '突然间', '渐渐', '缓缓',
        '一边', '一边...一边', '各种', '各种各样',
        '但是', '但是', '如果', '只要', '都会', '选择',
        '下意识地', '不可避免地', '看起来', '看起来就', '总之',
        '明白', '清楚', '显然', '确实', '的确', '确实',
        '猛地', '突然', '忽然', '忽然', '急忙', '连忙',
        '不可避免', '必然', '肯定', '肯定', '应该', '大概',

        # 转换/移动相关
        '一转', '二转', '三转', '四转', '五转', '六转', '七转', '八转', '九转',
        '慢慢转', '是非成败转', '辗转', '视线转', '脑筋也转', '转过转',
        '就能从奴转', '就能晋升成一转', '大多都能成为二转', '能成为三转',
        '三转直至九转', '每一转', '都是一转', '晋升二转', '三转',
        '通常会停在二转', '能修到三转', '甚至四转', '能修行到五转',
        '至于六转', '也没有出现过六转', '但是五转', '四转',
        '其中五转', '一直修行到了五转', '兴许能晋升成六转',

        # 蛊虫相关噪声
        '力量蛊和智慧蛊', '这只蛊', '蛊师有九转', '蛊师有一转',
        '分别是一转', '有一转', '都是通常蛊仙', '一方贩卖蛊仙',
        '而是为了让蛊', '土壤都是通常蛊', '自己一方贩卖蛊',
        '这种仙蛊', '经营之地', '家鲜活福地', '有八转蛊仙',
        '地和中洲蛊仙', '神秘八转蛊仙', '有八转蛊',
        '悄然地和中洲蛊', '海的神秘八转蛊', '正是因为仙道',
        '哪怕新兴家族', '他悄然地', '一位黑袍蛊仙', '黑袍蛊仙',
        '青年智道蛊仙', '它只是辅助仙蛊', '一位黑袍蛊', '黑袍蛊',
        '门的青年智道蛊', '他黑城', '力气两蛊', '分的魔道蛊仙',
        '倒是凡人蛊师', '山盟仙蛊', '宙道仙蛊', '反倒是凡人蛊',
        '偶尔会有寿蛊', '时运仙蛊', '要两只力道仙蛊',
        '大部分的魔道蛊', '强要两只力道', '大部分的魔道',
        '即猜到黎山', '而黎山', '对黎山', '叫黑城',
        '这两只力道仙蛊', '身上的力道道', '创造血道',
        '道仙蛊拔山', '世界由天地', '方正猛地', '方源无奈地',
        '逢凶化吉仙蛊', '方源那两只仙蛊', '的鸿运齐天仙蛊',
        '这鸿运齐天仙蛊', '似乎是消耗蛊', '炼鸿运齐天仙蛊',
        '是为了让蛊仙', '都是通常蛊仙', '一方贩卖蛊仙',
        '而是为了让蛊', '土壤都是通常蛊', '自己一方贩卖蛊',
        '这种仙蛊', '片无主福地', '的经营之地', '涉及大梦仙尊',
        '若是成为蛊仙', '解谜仙蛊', '核心仙蛊', '方源若是成为蛊',
        '家鲜活福地', '有八转蛊仙', '地和中洲蛊仙', '神秘八转蛊仙',
        '有八转蛊', '悄然地和中洲蛊', '海的神秘八转蛊',
        '正是因为仙道', '哪怕新兴家族', '他悄然地', '一位黑袍蛊仙',
        '黑袍蛊仙', '青年智道蛊仙', '它只是辅助仙蛊', '一位黑袍蛊',
        '黑袍蛊', '门的青年智道蛊', '他黑城', '力气两蛊',
        '分的魔道蛊仙', '倒是凡人蛊师', '山盟仙蛊', '宙道仙蛊',
        '反倒是凡人蛊', '偶尔会有寿蛊', '时运仙蛊', '要两只力道仙蛊',
        '大部分的魔道蛊', '强要两只力道', '大部分的魔道',
        '即猜到黎山', '而黎山', '对黎山', '叫黑城',
        '这两只力道仙蛊', '身上的力道道', '创造血道',
        '道仙蛊拔山', '世界由天地', '方正猛地', '方源无奈地',

        # 重复内容（文件中重复出现的行）
        '黑袍蛊', '山盟仙蛊', '宙道仙蛊', '反倒是凡人蛊', '大部分的魔道',
    }

    def _is_valid_entity(self, name: str) -> bool:
        """验证实体名称是否有效（非噪声）"""
        if not name or len(name) < 2 or len(name) > 8:
            return False
        # 快速失败：检查噪声词
        if name in self._noise_words:
            return False
        # 必须是纯中文（允许少量常见符号如'、'）
        import re
        if not re.match(r'^[一-龥]+$|^[一-龥]{2,4}$', name):
            return False
        # 不能有数量词（一位、一只、两个等）
        if any(word in name for word in ['一位', '一只', '一个', '两个', '三个', '这个', '那个', '这些']):
            return False
        # 排除纯动词/介词/副词
        common_verbs = ['持有', '手持', '使用', '拥有', '属于', '主修',
                       '修炼', '拜师', '击杀', '背叛', '控制', '运用']
        if name in common_verbs:
            return False
        # 对于有明确后缀的实体（小说场景），额外验证后缀
        # 但对于 UIE 泛化提取的实体，只保留基本长度/字符校验
        # 不再强制要求后缀
        return True

    def _extract_entity_with_boundary(self, text: str, entity_name: str) -> bool:
        """
        使用中文语境下的边界匹配实体
        
        方法一：使用中文语境下的边界（推荐）
        pattern = r'(?<![一-龥])方源(?![一-龥])'
        
        方法二：直接匹配，配合上下文验证
        pattern = r'方源'
        
        Args:
            text: 文本
            entity_name: 实体名称
            
        Returns:
            是否匹配
        """
        # 使用中文边界匹配
        pattern = r'(?<![一-龥])' + re.escape(entity_name) + r'(?![一-龥])'
        return bool(re.search(pattern, text))

    def _init_entity_patterns(self) -> Dict[str, List[str]]:
        """初始化实体识别模式 - 使用精确后缀匹配"""
        return {
            "人物": [
                r'([一-龥]{2,4}仙尊)',
                r'([一-龥]{2,4}魔尊)',
                r'([一-龥]{2,4}尊者)',
                r'([一-龥]{2,4}魔头)',
                r'([一-龥]{2,4}蛊仙)',
                r'([一-龥]{2,4}蛊师)',
                r'([一-龥]{2,4}真人)',
                r'([一-龥]{2,4}妖)',
                r'([一-龥]{2,4}灵)',
            ],
            "蛊虫": [
                r'([一-龥]{2,5}仙蛊)',
                r'([一-龥]{2,5}真蛊)',
                r'([一-龥]{2,5}凡蛊)',
                r'([一-龥]{2,5}魔蛊)',
            ],
            "流派": [
                r'([一-龥]{2,4}(?:血|道|力|情|魂|智|运|光|暗|生|死)道)',
                r'([一-龥]{2,4}(?:仙|魔)道)',
            ],
            "势力": [
                r'([一-龥]{2,4}世家)',
                r'([一-龥]{2,4}宗门)',
                r'([一-龥]{2,4}门派)',
                r'([一-龥]{2,4}家族)',
                r'([一-龥]{2,4}仙盟)',
                r'([一-龥]{2,4}魔教)',
            ],
            "地点": [
                r'([一-龥]{2,4}福地)',
                r'([一-龥]{2,4}洞天)',
                r'([一-龥]{2,4}神山)',
                r'([一-龥]{2,4}古地)',
                r'([一-龥]{2,4}雄城)',
            ],
            "境界": [
                r'(一转)',
                r'(二转)',
                r'(三转)',
                r'(四转)',
                r'(五转)',
                r'(六转)',
                r'(七转)',
                r'(八转)',
                r'(九转)',
            ],
        }

    def _init_rel_patterns(self) -> Dict[str, List[str]]:
        """初始化关系识别模式"""
        return {
            "持有": [
                r'(.+?)持有(.+?)',
                r'(.+?)有(.+?)',
                r'(.+?)拥有(.+?)',
                r'(.+?)随身携带(.+?)',
            ],
            "属于": [
                r'(.+?)属于(.+?)',
                r'(.+?)是(.+?)流派',
                r'(.+?)是(.+?)蛊虫',
                r'(.+?)属于(.+?)势力',
            ],
            "主修": [
                r'(.+?)主修(.+?)',
                r'(.+?)修炼(.+?)',
                r'(.+?)修习(.+?)',
            ],
            "师承": [
                r'(.+?)师从(.+?)',
                r'(.+?)是(.+?)的师傅',
                r'(.+?)是(.+?)的弟子',
                r'(.+?)拜(.+?)为师',
            ],
            "盟友": [
                r'(.+?)与(.+?)结盟',
                r'(.+?)是(.+?)的盟友',
            ],
            "敌对": [
                r'(.+?)与(.+?)敌对',
                r'(.+?)是(.+?)的敌人',
            ],
            "背叛": [
                r'(.+?)背叛(.+?)',
                r'(.+?)被(.+?)背叛',
            ],
            "击杀": [
                r'(.+?)击杀(.+?)',
                r'(.+?)杀死(.+?)',
                r'(.+?)斩(.+?)',
            ],
            "使用": [
                r'(.+?)使用(.+?)',
                r'(.+?)运用(.+?)',
            ],
            "控制": [
                r'(.+?)控制(.+?)',
                r'(.+?)操纵(.+?)',
            ],
        }

    def _extract_with_uie(self, text: str) -> List[Dict[str, str]]:
        """
        使用 PaddleNLP UIE 提取实体

        Args:
            text: 文本内容

        Returns:
            实体列表 [{"text": "方源", "type": "人物"}, ...]
        """
        if not self.uie_ner:
            return []
        
        try:
            results = self.uie_ner(text)
            entities = []
            # UIE 返回格式: [{'人物': [{'text': '方源', 'start': 0, 'end': 2, 'probability': 0.98}]}]
            # 或者: [[{"text": "方源", "type": "人物"}, ...]]
            if isinstance(results, list) and len(results) > 0:
                for result in results:
                    if isinstance(result, dict):
                        # 格式: {'人物': [{'text': '方源', ...}]}
                        for entity_type, entity_list in result.items():
                            if isinstance(entity_list, list):
                                for item in entity_list:
                                    if isinstance(item, dict):
                                        entities.append({
                                            "text": item.get("text", ""),
                                            "type": entity_type,
                                            "confidence": item.get("probability", 0.5)
                                        })
                    elif isinstance(result, list):
                        # 格式: [{"text": "方源", "type": "人物"}, ...]
                        for item in result:
                            if isinstance(item, dict):
                                entities.append({
                                    "text": item.get("text", ""),
                                    "type": item.get("type", "未分类")
                                })
            logger.info(f"UIE 提取到 {len(entities)} 个实体")
            return entities
        except Exception as e:
            logger.warning(f"UIE 提取失败: {e}")
            return []

    def scan_new_entities(
        self,
        text: str,
        source_chapter: str = None,
        min_confidence: int = 2
    ) -> List[Dict[str, Any]]:
        """
        扫描新文本中的潜在实体（支持正则+UIE混合抽取）

        Args:
            text: 文本内容
            source_chapter: 来源章节
            min_confidence: 最小置信度(匹配模式数量)

        Returns:
            新创建的实体列表
        """
        if not text or not text.strip():
            return []

        # 混合抽取：正则 + UIE
        all_entities = {}  # name -> {type, confidence, source}
        
        # 1. 正则抽取（确定性匹配）
        regex_entities = set()
        for entity_type, patterns in self._entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for name in matches:
                    name = name.strip(',。、;:""''')
                    if not self._is_valid_entity(name):
                        continue
                    if self.wiki_db.entity_exists(name):
                        continue
                    regex_entities.add(name)
                    if name not in all_entities:
                        all_entities[name] = {
                            "type": self._guess_entity_type(name),
                            "confidence": 1,
                            "method": "regex"
                        }
                    else:
                        all_entities[name]["confidence"] += 1
        
        # 2. UIE 抽取（泛化匹配，仅短文本或启用时）
        uie_entities = []
        if self.use_uie and len(text) < 5000:
            uie_entities = self._extract_with_uie(text)
        elif self.use_uie and len(text) >= 5000:
            # 长文本只抽取关键段落（人物对话、描写）
            import re as re_module
            dialogues = re_module.findall(r'[\u4e00-\u9fa5]{2,10}[\u3001，:：].*?[\u3002。！!]', text)
            for dialogue in dialogues[:20]:  # 最多抽取前 20 段对话
                uie_entities.extend(self._extract_with_uie(dialogue))
        
        # 合并 UIE 结果
        for entity in uie_entities:
            name = entity.get("text", "").strip()
            if not name or len(name) < 2 or len(name) > 8:
                continue
            if name in self._noise_words:
                continue
            if self.wiki_db.entity_exists(name):
                continue
            
            uie_type = entity.get("type", "未分类")
            # 映射 UIE 类型到内部类型
            type_map = {"人物": "人物", "蛊虫": "蛊虫", "流派": "流派", "势力": "势力", "地点": "地点"}
            mapped_type = type_map.get(uie_type, "未分类")
            
            if name not in all_entities:
                all_entities[name] = {
                    "type": mapped_type,
                    "confidence": 1,
                    "method": "uie"
                }
            else:
                # 正则和 UIE 都找到，提升置信度
                all_entities[name]["confidence"] += 1
                all_entities[name]["method"] = "regex+uie"
        
        # 过滤并批量插入
        new_entities = []
        for name, info in all_entities.items():
            if info["confidence"] >= min_confidence:
                properties = {"source_chapter": source_chapter} if source_chapter else None
                self.wiki_db.add_entity(name, info["type"], properties=properties, source_chapter=source_chapter)
                new_entities.append({
                    "name": name,
                    "type": info["type"],
                    "confidence": info["confidence"],
                    "source_chapter": source_chapter,
                    "method": info["method"]
                })

        logger.info(f"扫描到 {len(new_entities)} 个新实体并已入库")
        return new_entities

    def scan_new_relations(
        self,
        text: str,
        source_chapter: str = None
    ) -> List[Dict[str, Any]]:
        """
        扫描新文本中的潜在关系，并批量插入数据库

        Args:
            text: 文本内容
            source_chapter: 来源章节

        Returns:
            新创建的关系列表
        """
        if not text or not text.strip():
            return []

        candidates = []
        relation_count = {}

        # 扫描所有关系模式
        for rel_type, patterns in self._rel_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    # match 可能是 2-3 个元素
                    if isinstance(match, tuple):
                        source = match[0].strip()
                        target = match[1].strip() if len(match) > 1 else ""

                        # 跳过空值
                        if not source or not target:
                            continue

                        # 规范化名称
                        source = source.strip(',。、;:""''')
                        target = target.strip(',。、;:""''')

                        # 自动创建不存在的实体
                        if not self.wiki_db.entity_exists(source):
                            self.wiki_db.add_entity(source, "未分类", source_chapter=source_chapter)
                        if not self.wiki_db.entity_exists(target):
                            self.wiki_db.add_entity(target, "未分类", source_chapter=source_chapter)

                        # 统计置信度
                        relation_key = f"{source}|{rel_type}|{target}"
                        relation_count[relation_key] = relation_count.get(relation_key, 0) + 1

        # 过滤低置信度关系并批量插入
        new_relations = []
        for relation_key, confidence in relation_count.items():
            if confidence >= 2:
                parts = relation_key.split("|")
                source, rel_type, target = parts[0], parts[1], parts[2]

                # 批量插入关系
                self.wiki_db.add_relationship(source, target, rel_type, source_chapter=source_chapter)

                new_relations.append({
                    "source": source,
                    "target": target,
                    "rel_type": rel_type,
                    "confidence": confidence,
                    "source_chapter": source_chapter
                })

        logger.info(f"扫描到 {len(new_relations)} 个新关系并已入库")
        return new_relations

    def _guess_entity_type(self, name: str) -> str:
        """猜测实体类型"""
        name_lower = name.lower()

        if "仙尊" in name or "魔尊" in name or "尊者" in name:
            return "人物"
        elif "蛊" in name:
            return "蛊虫"
        elif "道" in name:
            return "流派"
        elif "家" in name or "族" in name or "派" in name or "门" in name:
            return "势力"
        elif "山" in name or "地" in name or "城" in name:
            return "地点"
        elif "转" in name:
            return "境界"
        else:
            return "未分类"

    def review_candidates(
        self,
        candidates: List[Dict[str, Any]],
        approved: List[str] = None,
        rejected: List[str] = None
    ) -> Dict[str, int]:
        """
        审核候选实体/关系

        Args:
            candidates: 候选列表
            approved: 批准的名称列表
            rejected: 拒绝的名称列表

        Returns:
            审核统计
        """
        if approved is None:
            approved = []
        if rejected is None:
            rejected = []

        stats = {
            "approved": 0,
            "rejected": 0,
            "skipped": 0
        }

        for candidate in candidates:
            name = candidate['name']

            if name in approved:
                # 批准实体
                try:
                    self.wiki_db.add_entity(
                        name=name,
                        entity_type=candidate['type'],
                        properties={"source_chapter": candidate['source_chapter']},
                        source_chapter=candidate['source_chapter']
                    )
                    stats["approved"] += 1
                    logger.info(f"批准实体: {name} (类型: {candidate['type']})")
                except Exception as e:
                    logger.error(f"批准实体失败 {name}: {e}")
                    stats["rejected"] += 1

            elif name in rejected:
                # 拒绝实体
                stats["rejected"] += 1
            else:
                # 跳过(未审核)
                stats["skipped"] += 1

        logger.info(f"审核完成: 批准 {stats['approved']}, 拒绝 {stats['rejected']}, 跳过 {stats['skipped']}")
        return stats

    def batch_add_from_text(
        self,
        text: str,
        source_chapter: str = None,
        min_confidence: int = 2
    ) -> Dict[str, int]:
        """
        批量添加实体和关系(自动审核)

        Args:
            text: 文本内容
            source_chapter: 来源章节
            min_confidence: 最小置信度

        Returns:
            添加统计
        """
        stats = {
            "entities_added": 0,
            "relations_added": 0
        }

        try:
            # 扫描实体（添加超时保护）
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError("scan_new_entities 超时")
            
            try:
                entity_candidates = self.scan_new_entities(text, source_chapter, min_confidence)
            except TimeoutError as e:
                logger.error(f"scan_new_entities 超时: {e}")
                entity_candidates = []
            
            for candidate in entity_candidates:
                try:
                    properties = {"source_chapter": candidate['source_chapter']} if candidate.get('source_chapter') else None
                    self.wiki_db.add_entity(
                        name=candidate['name'],
                        entity_type=candidate['type'],
                        properties=properties,
                        source_chapter=candidate['source_chapter']
                    )
                    stats["entities_added"] += 1
                except Exception as e:
                    logger.error(f"添加实体失败 {candidate['name']}: {e}")

            # 扫描关系
            relation_candidates = self.scan_new_relations(text, source_chapter)
            for candidate in relation_candidates:
                try:
                    self.wiki_db.add_relationship(
                        source_name=candidate['source'],
                        target_name=candidate['target'],
                        rel_type=candidate['rel_type'],
                        source_chapter=candidate['source_chapter']
                    )
                    stats["relations_added"] += 1
                except Exception as e:
                    logger.error(f"添加关系失败: {e}")

        except Exception as e:
            logger.error(f"批量添加失败: {e}")

        return stats

    def get_pending_review(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取待审核的实体列表（从数据库查询）

        Args:
            limit: 最大数量

        Returns:
            待审核列表
        """
        try:
            cursor = self.wiki_db.connect().cursor()
            cursor.execute('''
                SELECT id, entity_name, relation_type, properties, confidence, review_status,
                       created_at
                FROM pending_reviews
                WHERE review_status = 'pending'
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            self.wiki_db.connect().close()

            result = []
            for row in rows:
                result.append({
                    'id': row['id'],
                    'entity_name': row['entity_name'],
                    'relation_type': row['relation_type'],
                    'properties': row['properties'],
                    'confidence': row['confidence'],
                    'review_status': row['review_status'],
                    'created_at': row['created_at']
                })
            return result
        except Exception as e:
            logger.error(f"查询待审核列表失败: {e}")
            return []

    def export_candidates(self, candidates: List[Dict[str, Any]], output_path: str = None) -> str:
        """
        导出候选实体/关系为 JSON

        Args:
            candidates: 候选列表
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        if output_path is None:
            output_path = f"wiki_candidates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)

        logger.info(f"候选数据已导出到: {output_file}")
        return str(output_file)

    def import_candidates(self, input_path: str) -> List[Dict[str, Any]]:
        """
        从 JSON 导入候选实体/关系

        Args:
            input_path: 输入文件路径

        Returns:
            候选列表
        """
        input_file = Path(input_path)

        if not input_file.exists():
            logger.error(f"文件不存在: {input_path}")
            return []

        with open(input_file, 'r', encoding='utf-8') as f:
            candidates = json.load(f)

        logger.info(f"从 {input_path} 导入 {len(candidates)} 个候选")
        return candidates

    def get_stats(self) -> Dict[str, Any]:
        """
        获取更新统计

        Returns:
            统计信息
        """
        stats = self.wiki_db.get_stats()

        return {
            "total_entities": stats['total_entities'],
            "total_relationships": stats['total_relationships'],
            "entities_by_type": stats['entities'],
            "relations_by_type": stats['relationships']
        }

    # ==================== Phase 2: 推理引擎集成 ====================

    def trigger_reasoning(self) -> Dict[str, Any]:
        """
        触发推理引擎,自动推导新关系

        Returns:
            推理结果摘要
        """
        from rag_core.wiki_reasoner import WikiReasoner

        reasoner = WikiReasoner(self.wiki_db)
        summary = reasoner.get_rule_summary()

        logger.info(f"推理引擎执行完成: {summary['total_deductions']} 条推导")

        return summary

    def save_deductions(self) -> int:
        """
        将推导结果保存到待审核队列

        Returns:
            保存的记录数
        """
        from rag_core.wiki_reasoner import WikiReasoner

        reasoner = WikiReasoner(self.wiki_db)
        saved_count = reasoner.save_deductions_to_pending()

        logger.info(f"已保存 {saved_count} 条推导结果到待审核队列")

        return saved_count


    def scan_new_entities_llm(self, text: str, source_chapter: str = None) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        try:
            from rag_core.llm_extractor import LLMExtractor
            extractor = LLMExtractor()
            extraction_result = extractor.extract_all(text, source_chapter)
            new_entities = []
            for entity in extraction_result["llm"]:
                try:
                    self.wiki_db.add_entity(
                        name=entity["name"],
                        entity_type=entity["type"],
                        properties={"description": entity.get("description", "")},
                        source_chapter=source_chapter
                    )
                    new_entities.append({
                        "name": entity["name"],
                        "type": entity["type"],
                        "confidence": 1,
                        "source_chapter": source_chapter,
                        "method": "llm"
                    })
                except Exception as e:
                    logger.error("LLM entity add failed: " + str(e))
            logger.info("LLM scanned " + str(len(new_entities)) + " new entities")
            self._write_to_pending(extraction_result["regex"], source_chapter=source_chapter, method="regex")
            self._write_to_pending(extraction_result["jieba"], source_chapter=source_chapter, method="jieba")
            return new_entities
        except Exception as e:
            logger.warning("LLM extract failed: " + str(e))
            return self.scan_new_entities(text, source_chapter, min_confidence=2)

    def scan_new_relations_llm(self, text: str, source_chapter: str = None) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        try:
            from rag_core.llm_extractor import LLMExtractor
            extractor = LLMExtractor()
            extraction_result = extractor.extract_all(text, source_chapter)
            new_relations = []
            for rel in extraction_result["llm"]:
                try:
                    self.wiki_db.add_relationship(
                        source_name=rel["source"],
                        target_name=rel["target"],
                        rel_type=rel["type"],
                        properties={"description": rel.get("description", "")},
                        source_chapter=source_chapter
                    )
                    new_relations.append({
                        "source": rel["source"],
                        "target": rel["target"],
                        "rel_type": rel["type"],
                        "confidence": 1,
                        "source_chapter": source_chapter,
                        "method": "llm"
                    })
                except Exception as e:
                    logger.error("LLM relation add failed: " + str(e))
            logger.info("LLM scanned " + str(len(new_relations)) + " new relations")
            self._write_pending_relations(extraction_result["regex"], source_chapter=source_chapter, method="regex")
            self._write_pending_relations(extraction_result["jieba"], source_chapter=source_chapter, method="jieba")
            return new_relations
        except Exception as e:
            logger.warning("LLM relation extract failed: " + str(e))
            return self.scan_new_relations(text, source_chapter)

    def _write_to_pending(self, entities: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
        if not entities:
            return 0
        count = 0
        for entity in entities:
            name = entity.get("name", "")
            entity_type = entity.get("type", "unknown")
            description = entity.get("description", "")
            confidence = entity.get("confidence", 0)
            try:
                self.wiki_db.add_to_pending(
                    entity_name=name,
                    relation_type=entity_type,
                    properties={"description": description, "method": method, "source_chapter": source_chapter},
                    confidence=confidence
                )
                count += 1
            except Exception as e:
                logger.error("Pending entity write failed: " + str(e))
        return count

    def _write_pending_relations(self, relations: List[Dict[str, Any]], source_chapter: str = None, method: str = "unknown") -> int:
        if not relations:
            return 0
        count = 0
        for rel in relations:
            source_name = rel.get("source", "")
            target_name = rel.get("target", "")
            rel_type = rel.get("type", "related")
            description = rel.get("description", "")
            confidence = rel.get("confidence", 0)
            try:
                key = source_name + "--" + rel_type + "--" + target_name
                self.wiki_db.add_to_pending(
                    entity_name=key,
                    relation_type=key,
                    properties={"description": description, "method": method, "source_chapter": source_chapter, "source": source_name, "target": target_name, "rel_type": rel_type},
                    confidence=confidence
                )
                count += 1
            except Exception as e:
                logger.error("Pending relation write failed: " + str(e))
        return count