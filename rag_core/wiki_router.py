"""
Wiki 路由层 - 判断查询类型并路由到合适的处理方式

功能：
- 判断查询是事实类还是语义类
- 事实类查询 → Wiki 数据库
- 语义类查询 → ChromaDB RAG
"""

import logging
from typing import Set, Optional

from rag_config import logger

logger = logging.getLogger(__name__)


class WikiRouter:
    """
    Wiki 路由器

    用法:
        router = WikiRouter()
        route = router.route("方源主修什么流派？")
        if route == "wiki":
            result = wiki_db.get_fact_query_answer(query)
        else:
            result = rag_pipeline.retrieve(query)
    """

    def __init__(self, known_entities: Set[str] = None):
        """
        初始化路由器

        Args:
            known_entities: 已知实体名称集合（从 Wiki 数据库加载）
        """
        self.known_entities = known_entities or set()

    def route(self, query: str) -> str:
        """
        路由查询到 Wiki 或 RAG

        路由规则：
        1. 事实类查询 → Wiki
           - 包含"是什么" + 实体名
           - 包含"主修/属于/持有" + 实体名
           - 包含"有哪些" + 类型词

        2. 语义类查询 → RAG
           - 包含"为什么/怎么/如何"
           - 包含情绪词（"心情"、"感受"）
           - 问题长度 > 20字且不含实体名

        Args:
            query: 用户查询

        Returns:
            "wiki" 或 "rag"
        """
        if not query or not query.strip():
            return "rag"

        query = query.strip()

        # 1. 实体名提取
        has_entity = any(e in query for e in self.known_entities)

        # 2. 事实关键词
        fact_keywords = [
            "是什么", "主修", "属于", "持有", "有哪些",
            "关系", "弟子", "师承", "盟友", "敌对"
        ]
        has_fact = any(kw in query for kw in fact_keywords)

        # 3. 语义关键词
        semantic_keywords = [
            "为什么", "怎么", "如何", "心情", "感受",
            "原因", "原因", "怎么样", "如何看待"
        ]
        has_semantic = any(kw in query for kw in semantic_keywords)

        # 4. 判断逻辑
        # 事实类查询：有实体 + 有事实关键词 + 无语义关键词
        if has_entity and has_fact and not has_semantic:
            logger.info(f"[路由] 事实类查询 → Wiki: {query}")
            return "wiki"

        # 语义类查询：有语义关键词 或 无实体且问题较长
        if has_semantic:
            logger.info(f"[路由] 语义类查询 → RAG: {query}")
            return "rag"

        # 默认 → RAG
        logger.info(f"[路由] 默认 → RAG: {query}")
        return "rag"

    def route_with_llm(self, query: str, wiki_db) -> str:
        """
        使用 LLM 辅助判断（可选，提升准确率）

        Args:
            query: 用户查询
            wiki_db: Wiki 数据库实例

        Returns:
            "wiki" 或 "rag"
        """
        # 先用关键词判断
        route = self.route(query)
        if route != "rag":
            return route

        # 如果关键词判断失败，使用 LLM 辅助
        try:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0,
                max_tokens=10
            )

            prompt = f"""判断以下查询的类型：
查询: {query}

选项: 事实类 / 语义类

只返回一个词（"事实类" 或 "语义类"）"""

            response = llm.invoke(prompt)
            result = response.content.strip()

            if "事实类" in result:
                logger.info(f"[路由] LLM判断 → Wiki: {query}")
                return "wiki"
            else:
                logger.info(f"[路由] LLM判断 → RAG: {query}")
                return "rag"

        except Exception as e:
            logger.warning(f"LLM路由判断失败，回退到关键词判断: {e}")
            return self.route(query)

    def get_known_entities(self) -> Set[str]:
        """获取已知实体集合"""
        return self.known_entities

    def add_known_entity(self, entity_name: str):
        """添加已知实体"""
        self.known_entities.add(entity_name)

    def load_known_entities(self, wiki_db) -> None:
        """
        从 Wiki 数据库加载已知实体

        Args:
            wiki_db: Wiki 数据库实例
        """
        entities = wiki_db.get_entities_by_type("人物")
        for entity in entities:
            self.known_entities.add(entity['name'])

        entities = wiki_db.get_entities_by_type("蛊虫")
        for entity in entities:
            self.known_entities.add(entity['name'])

        entities = wiki_db.get_entities_by_type("势力")
        for entity in entities:
            self.known_entities.add(entity['name'])

        logger.info(f"已加载 {len(self.known_entities)} 个已知实体")


# ==================== 全局实例 ====================

# 全局路由器实例
_wiki_router_instance: Optional[WikiRouter] = None


def get_wiki_router(force_reload: bool = False) -> WikiRouter:
    """
    获取全局 WikiRouter 实例（自动从数据库加载已知实体）
    
    Args:
        force_reload: 是否强制重新加载（默认 False，首次加载后缓存）
    """
    global _wiki_router_instance
    if _wiki_router_instance is None or force_reload:
        from rag_core.wiki_db import get_wiki_db
        _wiki_router_instance = WikiRouter()
        wiki_db = get_wiki_db()
        wiki_db.init_db()
        _wiki_router_instance.load_known_entities(wiki_db)
    return _wiki_router_instance


def reset_wiki_router():
    """重置全局 WikiRouter 实例"""
    global _wiki_router_instance
    _wiki_router_instance = None
