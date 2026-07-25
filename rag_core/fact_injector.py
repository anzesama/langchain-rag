"""
事实锚点约束注入器

功能：
- 从 Wiki 检索与查询相关的事实
- 将事实作为硬约束注入到 LLM prompt
- 确保 LLM 回答与已知事实一致

核心思想：
"无论问题走不走 Wiki 路由，都先检索 Wiki 中与问题实体相关的事实，
拼接到 prompt 顶部，并明确指示 LLM：以下事实是确定的，
如果你的回答与之冲突，必须修正。"
"""

import logging
from typing import List, Dict, Any, Optional
from rag_core.wiki_db import get_wiki_db

logger = logging.getLogger(__name__)


class FactConstraintInjector:
    """
    事实约束注入器

    用法:
        injector = FactConstraintInjector()
        constraints = injector.get_constraints("方源的主修是什么？")
        prompt = f"{constraints}\\n{original_prompt}"
    """

    def __init__(self, max_facts: int = 5, min_confidence: float = 0.8):
        """
        初始化事实约束注入器

        Args:
            max_facts: 最多返回的事实数量
            min_confidence: 最低置信度阈值
        """
        self.max_facts = max_facts
        self.min_confidence = min_confidence
        self.wiki_db = get_wiki_db()

    def get_constraints(self, query: str) -> str:
        """
        获取事实约束字符串

        Args:
            query: 用户查询

        Returns:
            格式化的事实约束字符串
        """
        facts = self.wiki_db.get_facts_for_query(query, top_k=self.max_facts)

        if not facts:
            return ""

        # 过滤低置信度事实
        facts = [f for f in facts if f['confidence'] >= self.min_confidence]

        if not facts:
            return ""

        # 格式化事实约束
        constraint_lines = ["# 已知事实约束（硬约束）"]
        constraint_lines.append("以下事实是确定的，如果 LLM 的回答与之冲突，必须修正。")
        constraint_lines.append("")

        for i, fact in enumerate(facts, 1):
            constraint_lines.append(
                f"{i}. [{fact['entity_name']}] {fact['fact_type']} = {fact['fact_value']}"
                f" (置信度：{fact['confidence']}, 来源：{fact['source']})"
            )

        constraint_lines.append("")
        constraint_lines.append("---")
        constraint_lines.append("")

        return "\n".join(constraint_lines)

    def get_constraints_for_entity(self, entity_name: str) -> str:
        """
        获取指定实体的所有事实约束

        Args:
            entity_name: 实体名称

        Returns:
            格式化的事实约束字符串
        """
        facts = self.wiki_db.get_facts_for_entity(entity_name)

        if not facts:
            return ""

        # 过滤低置信度事实
        facts = [f for f in facts if f['confidence'] >= self.min_confidence]

        if not facts:
            return ""

        # 格式化事实约束
        constraint_lines = [f"# {entity_name} 的已知事实约束"]
        constraint_lines.append("")

        for i, fact in enumerate(facts, 1):
            constraint_lines.append(
                f"{i}. {fact['fact_type']} = {fact['fact_value']}"
                f" (置信度：{fact['confidence']})"
            )

        constraint_lines.append("")
        constraint_lines.append("---")
        constraint_lines.append("")

        return "\n".join(constraint_lines)

    def inject_into_prompt(self, query: str, original_prompt: str) -> str:
        """
        将事实约束注入到原始 prompt 中

        Args:
            query: 用户查询
            original_prompt: 原始 prompt

        Returns:
            注入事实约束后的完整 prompt
        """
        constraints = self.get_constraints(query)

        if not constraints:
            return original_prompt

        return f"{constraints}{original_prompt}"
