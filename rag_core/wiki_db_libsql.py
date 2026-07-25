"""
Wiki 数据库模块 - 结构化事实存储（libsql 版本）

功能：
- 存储实体（人物、蛊虫、流派、势力等）
- 存储实体间关系
- 提供精确查询接口
- 与 ChromaDB/SQLite 版本接口兼容
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
import hashlib

logger = logging.getLogger(__name__)


# ==================== 全局实例 ====================

# 全局 WikiDB 实例（单例模式）
_wiki_db_instance = None

def get_wiki_db():
    """获取全局 WikiDB 实例"""
    global _wiki_db_instance
    if _wiki_db_instance is None:
        _wiki_db_instance = WikiDB()
        _wiki_db_instance.init_db()
    return _wiki_db_instance


class WikiDB:
    """
    Wiki 数据库管理器（libsql 版本 - 与 SQLite 本地开发兼容）

    用法:
        wiki = WikiDB()
        wiki.init_db()
        wiki.add_entity("方源", "人物", {"主修": "力道", "资质": "甲等9成"})
        wiki.add_relationship("方源", "全力以赴蛊", "持有")
        relations = wiki.get_entity_relations("fang_yuan")
    """

    def __init__(self, db_path: str = None):
        """
        初始化 Wiki 数据库

        Args:
            db_path: 数据库文件路径，默认为 storage/knowledge_base.db
        """
        project_root = Path(__file__).parent.parent  # rag_core -> langchain-rag
        self.storage_dir = project_root / "storage"

        # 使用统一的 libsql 数据库文件存储所有数据
        if db_path is None:
            self.db_path = str(self.storage_dir / "knowledge_base.db")
        else:
            self.db_path = db_path

        self.conn = None

        # 初始化数据库表结构
        self.init_db()

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")  # 开启外键约束
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_db(self):
        """初始化数据库表结构"""
        conn = self.connect()
        cursor = conn.cursor()

        # 实体表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT,
                aliases TEXT,
                source_chapter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 关系表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                properties TEXT,
                source_chapter TEXT,
                FOREIGN KEY(source_id) REFERENCES entities(id),
                FOREIGN KEY(target_id) REFERENCES entities(id)
            )
        ''')

        # 索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(rel_type)')

        # Phase 1: 新增表（负反馈闭环 + 时间维度）
        # 实体历史版本表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                old_properties TEXT,
                new_properties TEXT,
                change_reason TEXT,
                changed_by TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_to TIMESTAMP,
                is_correction BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(entity_id) REFERENCES entities(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_history_entity ON entity_history(entity_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_history_created ON entity_history(created_at)')

        # 待审核队列表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT,
                entity_name TEXT NOT NULL,
                entity_type TEXT,
                properties TEXT,
                relation_type TEXT,
                source_id TEXT,
                target_id TEXT,
                confidence REAL DEFAULT 0.5,
                source_text TEXT,
                source_chapter TEXT,
                review_status TEXT DEFAULT 'pending',
                reviewed_by TEXT,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(entity_id) REFERENCES entities(id),
                FOREIGN KEY(source_id) REFERENCES entities(id),
                FOREIGN KEY(target_id) REFERENCES entities(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_entity ON pending_reviews(entity_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_reviews(review_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_confidence ON pending_reviews(confidence)')

        # 修正日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS correction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                change_reason TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(entity_id) REFERENCES entities(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_correction_entity ON correction_log(entity_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_correction_changed ON correction_log(changed_at)')

        # Phase 3: 事实锚点表（经过验证的硬约束事实）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                verified_by TEXT,
                verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(entity_id) REFERENCES entities(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_facts_value ON facts(fact_value)')

        conn.commit()
        conn.close()

        logger.info(f"Wiki 数据库初始化完成: {self.db_path}")

    # ==================== 实体操作 ====================

    def entity_exists(self, name: str) -> bool:
        """
        检查实体是否存在

        Args:
            name: 实体名称

        Returns:
            是否存在
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM entities WHERE name = ?', (name,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_entity_id(self, name: str) -> Optional[str]:
        """
        获取实体 ID

        Args:
            name: 实体名称

        Returns:
            实体 ID，不存在返回 None
        """
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM entities WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        return row['id'] if row else None

    def add_entity(self, name, entity_type, properties=None, aliases=None, source_chapter=None, entity_id=None):
        """添加实体"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 生成实体 ID
            if entity_id is None:
                entity_id = self._generate_entity_id(name)

            # 检查是否已存在
            cursor.execute('SELECT id FROM entities WHERE name = ?', (name,))
            if cursor.fetchone():
                conn.close()
                return False

            # 插入实体
            cursor.execute('''
                INSERT INTO entities (id, name, type, properties, aliases, source_chapter)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                entity_id,
                name,
                entity_type,
                json.dumps(properties, ensure_ascii=False) if properties else None,
                json.dumps(aliases, ensure_ascii=False) if aliases else None,
                source_chapter
            ))

            conn.commit()
            conn.close()
            logger.info(f"实体已添加: {name}")
            return True
        except Exception as e:
            logger.error(f"添加实体失败: {e}")
            return False

    def approve_entity(self, entity_id: str) -> bool:
        """批准实体（当前版本不执行状态更新，表结构已简化为无 status 列）"""
        try:
            # 新版实体表没有 status 列，所以只检查实体是否存在
            entity_name = self.get_entity_name(entity_id)
            if entity_name:
                logger.info(f"实体批准（确认存在）: {entity_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"实体批准失败: {e}")
            return False

    def get_entity(self, name: str) -> Optional[Dict]:
        """获取实体信息"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('SELECT id, name, type, properties, aliases, source_chapter FROM entities WHERE name = ?', (name,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {
                "id": row['id'],
                "name": row['name'],
                "type": row['type'],
                "properties": json.loads(row['properties']) if row['properties'] else {},
                "aliases": json.loads(row['aliases']) if row['aliases'] else [],
                "source_chapter": row['source_chapter']
            }
        except Exception as e:
            logger.error(f"获取实体失败: {e}")
            return None

    def get_all_entities(self) -> List[Dict]:
        """获取所有实体"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('SELECT id, name, type, properties, aliases, source_chapter FROM entities ORDER BY name')
            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row['id'],
                    "name": row['name'],
                    "type": row['type'],
                    "properties": json.loads(row['properties']) if row['properties'] else {},
                    "aliases": json.loads(row['aliases']) if row['aliases'] else [],
                    "source_chapter": row['source_chapter']
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取所有实体失败: {e}")
            return []

    def get_entity_history(self, entity_name: str, limit: int = 10) -> List[Dict]:
        """获取实体历史版本"""
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                return []

            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM entity_history
                WHERE entity_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (entity_id, limit))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取实体历史失败: {e}")
            return []

    # ==================== 关系操作 ====================

    def add_relationship(self, source_name, target_name, rel_type, properties=None, source_chapter=None):
        """添加关系"""
        try:
            source_id = self.get_entity_id(source_name)
            target_id = self.get_entity_id(target_name)

            if not source_id or not target_id:
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute('''
                SELECT id FROM relationships
                WHERE source_id = ? AND target_id = ? AND rel_type = ?
            ''', (source_id, target_id, rel_type))

            if cursor.fetchone():
                conn.close()
                return False

            # 插入关系
            cursor.execute('''
                INSERT INTO relationships (source_id, target_id, rel_type, properties, source_chapter)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                source_id,
                target_id,
                rel_type,
                json.dumps(properties, ensure_ascii=False) if properties else None,
                source_chapter
            ))

            conn.commit()
            conn.close()
            logger.info(f"关系已添加: {source_name} -{rel_type}-> {target_name}")
            return True
        except Exception as e:
            logger.error(f"添加关系失败: {e}")
            return False

    def approve_relation(self, relation_id: str) -> bool:
        """批准关系（当前版本不执行状态更新，表结构已简化为无 status 列）"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 新版关系表没有 status 列，检查关系是否存在
            cursor.execute('SELECT id FROM relationships WHERE id = ?', (relation_id,))
            if cursor.fetchone():
                logger.info(f"关系批准（确认存在）: {relation_id}")
                conn.close()
                return True
            conn.close()
            return False
        except Exception as e:
            logger.error(f"关系批准失败: {e}")
            return False

    def delete_relation(self, relation_id: int) -> bool:
        """删除关系"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('DELETE FROM relationships WHERE id = ?', (relation_id,))
            conn.commit()
            conn.close()
            logger.info(f"关系已删除: {relation_id}")
            return True
        except Exception as e:
            logger.error(f"删除关系失败: {e}")
            return False

    def get_relations(self, entity_id: str, rel_type: str = None) -> List[Dict]:
        """获取实体的关系列表"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            if rel_type:
                cursor.execute('''
                    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.properties, r.source_chapter,
                           e1.name as source_name, e2.name as target_name
                    FROM relationships r
                    JOIN entities e1 ON r.source_id = e1.id
                    JOIN entities e2 ON r.target_id = e2.id
                    WHERE r.source_id = ? AND r.rel_type = ?
                    ORDER BY r.id
                ''', (entity_id, rel_type))
            else:
                cursor.execute('''
                    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.properties, r.source_chapter,
                           e1.name as source_name, e2.name as target_name
                    FROM relationships r
                    JOIN entities e1 ON r.source_id = e1.id
                    JOIN entities e2 ON r.target_id = e2.id
                    WHERE r.source_id = ?
                    ORDER BY r.id
                ''', (entity_id,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取关系失败: {e}")
            return []

    def get_entity_relations(self, entity_id: str) -> Dict:
        """获取实体的关系网络"""
        relations = self.get_relations(entity_id)
        return {
            "id": entity_id,
            "relations": [
                {
                    "id": rel['id'],
                    "source": rel['source_name'],
                    "target": rel['target_name'],
                    "rel_type": rel['rel_type'],
                    "properties": json.loads(rel['properties']) if rel['properties'] else {},
                    "source_chapter": rel['source_chapter']
                }
                for rel in relations
            ]
        }

    # ==================== 事实锚点操作 ====================

    def add_fact(self, entity_name: str, fact_type: str, fact_value: str,
                 confidence: float = 1.0, source: str = "manual",
                 verified_by: str = "system") -> bool:
        """添加事实（硬约束）"""
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute('''
                SELECT id FROM facts
                WHERE entity_id = ? AND fact_type = ? AND fact_value = ?
            ''', (entity_id, fact_type, fact_value))

            if cursor.fetchone():
                conn.close()
                return True

            # 插入事实
            cursor.execute('''
                INSERT INTO facts (entity_id, entity_name, fact_type, fact_value, confidence, source, verified_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                entity_id, entity_name, fact_type, fact_value,
                confidence, source, verified_by
            ))

            conn.commit()
            conn.close()
            logger.info(f"事实已添加: {entity_name}.{fact_type} = {fact_value} (置信度: {confidence})")
            return True
        except Exception as e:
            logger.error(f"添加事实失败: {e}")
            return False

    def get_facts_for_entity(self, entity_id: str) -> List[Dict]:
        """获取实体的所有事实"""
        try:
            entity_name = self.get_entity_name(entity_id)
            if not entity_name:
                return []

            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM facts
                WHERE entity_id = ?
                ORDER BY confidence DESC, created_at DESC
            ''', (entity_id,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取事实失败: {e}")
            return []

    def get_facts_for_query(self, query: str, top_k: int = 5) -> List[Dict]:
        """查询相关事实"""
        try:
            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 简单关键词匹配
            keywords = query.split()
            if not keywords:
                conn.close()
                return []

            conditions = ' OR '.join(['fact_value LIKE ?' for _ in keywords])
            params = [f'%{kw}%' for kw in keywords]

            cursor.execute(f'''
                SELECT * FROM facts
                WHERE {conditions}
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            ''', params + [top_k])

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"查询事实失败: {e}")
            return []

    def remove_fact(self, fact_id: int) -> bool:
        """删除事实"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('DELETE FROM facts WHERE id = ?', (fact_id,))
            conn.commit()
            conn.close()
            logger.info(f"事实已删除: {fact_id}")
            return True
        except Exception as e:
            logger.error(f"删除事实失败: {e}")
            return False

    # ==================== 待审核管理 ====================

    def get_pending_reviews(self, limit: int = 20) -> List[Dict]:
        """获取待审核项"""
        try:
            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM pending_reviews
                WHERE review_status = 'pending'
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取待审核项失败: {e}")
            return []

    def approve_review(self, review_id: int) -> bool:
        """审核通过"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE pending_reviews
                SET review_status = 'approved', reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (review_id,))

            conn.commit()
            conn.close()
            logger.info(f"审核通过: {review_id}")
            return True
        except Exception as e:
            logger.error(f"审核失败: {e}")
            return False

    def reject_review(self, review_id: int) -> bool:
        """审核拒绝"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE pending_reviews
                SET review_status = 'rejected', reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (review_id,))

            conn.commit()
            conn.close()
            logger.info(f"审核拒绝: {review_id}")
            return True
        except Exception as e:
            logger.error(f"拒绝失败: {e}")
            return False

    def get_entity_name(self, entity_id: str) -> Optional[str]:
        """获取实体名称
        Args:
            entity_id: 实体 ID
        Returns:
            实体名称，不存在返回 None
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM entities WHERE id = ?', (entity_id,))
            row = cursor.fetchone()
            conn.close()
            return row['name'] if row else None
        except Exception as e:
            logger.error(f"获取实体名失败: {e}")
            return None

    def get_stats(self) -> Dict:
        """获取统计信息"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 实体统计
            cursor.execute('SELECT COUNT(*), type FROM entities GROUP BY type')
            entity_stats = {row['type']: row['COUNT(*)'] for row in cursor.fetchall()}

            # 关系统计
            cursor.execute('SELECT COUNT(*), rel_type FROM relationships GROUP BY rel_type')
            rel_stats = {row['rel_type']: row['COUNT(*)'] for row in cursor.fetchall()}

            conn.close()

            return {
                "entities": entity_stats,
                "relationships": rel_stats,
                "total_entities": sum(entity_stats.values()),
                "total_relationships": sum(rel_stats.values())
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def _generate_entity_id(self, name: str) -> str:
        """生成实体 ID"""
        return "entity_" + hashlib.md5(name.encode()).hexdigest()[:8]