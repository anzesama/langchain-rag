"""
Wiki 数据库模块 - 结构化事实存储（libsql 版本）

功能：
- 存储实体（人物、机器人、流程、势力等）
- 存储实体间关系
- 提供精确查询接口

注意：此模块现在使用 libsql 版本的 WikiDB。
导入会自动使用 libsql 版本（wiki_db_libsql.py）。
"""

# 从 libsql 版本导入所有公共 API
# 这样做的好处是：所有其他文件中 `from rag_core.wiki_db import WikiDB, get_wiki_db` 不需要修改
# 因为我们在这里直接从 libsql 版本重新导出

from rag_core.wiki_db_libsql import (
    WikiDB,
    get_wiki_db,
    _wiki_db_instance,
)

# 导出 logger（兼容旧代码）
import logging
logger = logging.getLogger(__name__)

# 确保所有公共 API 都从 libsql 版本导出
__all__ = ['WikiDB', 'get_wiki_db']