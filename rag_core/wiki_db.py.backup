"""
Wiki 数据库模块 - 结构化事实存储

功能：
- 存储实体（人物、蛊虫、流派、势力等）
- 存储实体间关系
- 提供精确查询接口
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

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
    Wiki 数据库管理器（SQLite）

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
            db_path: 数据库文件路径，默认为 langchain-rag/data/wiki/wiki.db
        """
        project_root = Path(__file__).parent.parent  # rag_core -> langchain-rag
        self.db_dir = project_root / "data" / "wiki"
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path or str(self.db_dir / "wiki.db")
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

    def add_entity(
        self,
        name: str,
        entity_type: str,
        properties: Dict[str, Any] = None,
        aliases: List[str] = None,
        source_chapter: str = None,
        entity_id: str = None
    ) -> bool:
        """
        添加实体

        Args:
            name: 实体名称
            entity_type: 实体类型（人物/蛊虫/流派/势力/事件/地点/境界）
            properties: 属性字典
            aliases: 别名列表
            source_chapter: 首次出现章节
            entity_id: 实体 ID（可选，默认自动生成）

        Returns:
            是否成功
        """
        try:
            # 生成实体 ID（如果未提供）
            if entity_id is None:
                # 使用拼音或简化的 ID
                entity_id = self._generate_entity_id(name)

            conn = self.connect()
            cursor = conn.cursor()

            # 检查是否已存在
            if self.entity_exists(name):
                logger.warning(f"实体已存在: {name}")
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

            logger.info(f"实体已添加: {name} (ID: {entity_id}, 类型: {entity_type})")
            return True

        except Exception as e:
            logger.error(f"添加实体失败 {name}: {e}")
            return False

    def update_entity(
        self,
        name: str,
        properties: Dict[str, Any] = None,
        aliases: List[str] = None
    ) -> bool:
        """
        更新实体属性

        Args:
            name: 实体名称
            properties: 新属性字典
            aliases: 新别名列表

        Returns:
            是否成功
        """
        try:
            entity_id = self.get_entity_id(name)
            if not entity_id:
                logger.warning(f"实体不存在: {name}")
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 获取当前数据
            cursor.execute('SELECT properties, aliases FROM entities WHERE id = ?', (entity_id,))
            row = cursor.fetchone()
            current_properties = json.loads(row['properties']) if row['properties'] else {}
            current_aliases = json.loads(row['aliases']) if row['aliases'] else []

            # 合并属性
            if properties:
                current_properties.update(properties)

            # 合并别名
            if aliases:
                for alias in aliases:
                    if alias not in current_aliases:
                        current_aliases.append(alias)

            # 更新
            cursor.execute('''
                UPDATE entities
                SET properties = ?, aliases = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                json.dumps(current_properties, ensure_ascii=False),
                json.dumps(current_aliases, ensure_ascii=False),
                entity_id
            ))

            conn.commit()
            conn.close()

            logger.info(f"实体已更新: {name}")
            return True

        except Exception as e:
            logger.error(f"更新实体失败 {name}: {e}")
            return False

    def get_entity(self, name: str) -> Optional[Dict]:
        """
        获取实体完整信息

        Args:
            name: 实体名称

        Returns:
            实体字典，不存在返回 None
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, type, properties, aliases, source_chapter
                FROM entities WHERE name = ?
            ''', (name,))

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
            logger.error(f"获取实体失败 {name}: {e}")
            return None

    def get_entities(self) -> List[Dict]:
        """
        查询所有实体（包括 review_status）

        Returns:
            实体列表
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, type, properties, aliases, source_chapter, review_status
                FROM entities
                ORDER BY name
            ''')

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row['id'],
                    "name": row['name'],
                    "type": row['type'],
                    "properties": json.loads(row['properties']) if row['properties'] else {},
                    "aliases": json.loads(row['aliases']) if row['aliases'] else [],
                    "source_chapter": row['source_chapter'],
                    "review_status": row['review_status'] or 'pending'
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"查询实体列表失败: {e}")
            return []

    def get_entities_by_type(self, entity_type: str) -> List[Dict]:
        """
        按类型查询所有实体

        Args:
            entity_type: 实体类型

        Returns:
            实体列表
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, type, properties, aliases, source_chapter
                FROM entities WHERE type = ?
                ORDER BY name
            ''', (entity_type,))

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
            logger.error(f"按类型查询失败 {entity_type}: {e}")
            return []

    # ==================== 关系操作 ====================

    def add_relationship(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        properties: Dict[str, Any] = None,
        source_chapter: str = None
    ) -> bool:
        """
        添加关系

        Args:
            source_name: 源实体名称
            target_name: 目标实体名称
            rel_type: 关系类型（持有/属于/主修/背叛/盟友/师承等）
            properties: 关系属性
            source_chapter: 来源章节

        Returns:
            是否成功
        """
        try:
            # 获取实体 ID
            source_id = self.get_entity_id(source_name)
            target_id = self.get_entity_id(target_name)

            if not source_id or not target_id:
                logger.warning(f"实体不存在: {source_name} 或 {target_name}")
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 检查关系是否已存在
            cursor.execute('''
                SELECT id FROM relationships
                WHERE source_id = ? AND target_id = ? AND rel_type = ?
            ''', (source_id, target_id, rel_type))

            if cursor.fetchone():
                logger.warning(f"关系已存在: {source_name} -{rel_type}-> {target_name}")
                conn.close()
                return False

            # 插入关系
            cursor.execute('''
                INSERT INTO relationships (source_id, target_id, rel_type, properties, source_chapter, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
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

    def delete_relation(self, relation_id: int) -> bool:
        """
        删除关系

        Args:
            relation_id: 关系 ID

        Returns:
            是否成功
        """
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

    def approve_relation(self, relation_id: str) -> bool:
        """
        批准关系（直接批准）

        Args:
            relation_id: 关系ID

        Returns:
            bool: 是否成功
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE relationships
                SET status = 'approved'
                WHERE id = ?
            ''', (relation_id,))

            conn.commit()
            conn.close()

            logger.info(f"关系批准: {relation_id}")
            return True

        except Exception as e:
            logger.error(f"关系批准失败: {e}")
            return False

    def get_relations(self, entity_name_or_id: str, rel_type: str = None) -> List[Dict]:
        """
        查询实体的所有关系

        Args:
            entity_name_or_id: 实体名称或 ID
            rel_type: 关系类型（可选，不传则返回所有类型）

        Returns:
            关系列表
        """
        try:
            # 如果是名称，转换为 ID
            entity_id = self.get_entity_id(entity_name_or_id) or entity_name_or_id
            
            conn = self.connect()
            cursor = conn.cursor()

            if rel_type:
                cursor.execute('''
                    SELECT r.id, e1.name as source_name, e2.name as target_name, r.rel_type, r.properties, r.source_chapter
                    FROM relationships r
                    JOIN entities e1 ON r.source_id = e1.id
                    JOIN entities e2 ON r.target_id = e2.id
                    WHERE r.source_id = ? AND r.rel_type = ?
                ''', (entity_id, rel_type))
            else:
                cursor.execute('''
                    SELECT r.id, e1.name as source_name, e2.name as target_name, r.rel_type, r.properties, r.source_chapter
                    FROM relationships r
                    JOIN entities e1 ON r.source_id = e1.id
                    JOIN entities e2 ON r.target_id = e2.id
                    WHERE r.source_id = ?
                ''', (entity_id,))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row['id'],
                    "source": row['source_name'],
                    "target": row['target_name'],
                    "rel_type": row['rel_type'],
                    "properties": json.loads(row['properties']) if row['properties'] else {},
                    "source_chapter": row['source_chapter']
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"查询关系失败 {entity_id}: {e}")
            return []

    def get_entity_relations(self, entity_name: str, max_depth: int = 1) -> Dict:
        """
        查询实体关系网络

        Args:
            entity_name: 实体名称
            max_depth: 最大深度

        Returns:
            关系网络字典
        """
        entity_id = self.get_entity_id(entity_name)
        if not entity_id:
            return {"entity": entity_name, "relations": []}

        relations = self.get_relations(entity_id, rel_type=None)

        # 扩展到多跳（可选）
        if max_depth > 1:
            visited = {entity_id}
            for rel in relations[:]:  # 遍历副本
                if rel['target_type'] == "实体":  # 假设 relations 包含 target_type
                    pass

        return {
            "entity": entity_name,
            "relations": relations
        }

    # ==================== 查询接口 ====================

    def get_fact_query_answer(self, query: str) -> Optional[str]:
        """
        处理事实类查询

        示例：
            - "方源主修什么流派？"
            - "方源持有哪些蛊虫？"
            - "元始仙尊的弟子有哪些？"

        Args:
            query: 查询文本

        Returns:
            答案文本，无法回答返回 None
        """
        try:
            # 解析查询
            parts = self._parse_fact_query(query)
            if not parts:
                return None

            entity_name, rel_type = parts

            # 获取实体
            entity = self.get_entity(entity_name)
            if not entity:
                return f"知识库中未找到实体: {entity_name}"

            # 根据关系类型查询
            if rel_type in ["持有", "属于"]:
                # 查询关系
                relations = self.get_relations(entity['id'], rel_type=rel_type)
                if not relations:
                    return f"{entity_name} 没有相关的 {rel_type} 关系"

                # 格式化答案
                targets = [rel['target'] for rel in relations]
                return f"{entity_name} {rel_type} 的对象: {', '.join(targets)}"

            elif rel_type in ["主修", "师承", "盟友", "敌对"]:
                # 查询关系
                relations = self.get_relations(entity['id'], rel_type=rel_type)
                if not relations:
                    return f"{entity_name} 没有相关的 {rel_type} 关系"

                # 格式化答案
                targets = [rel['target'] for rel in relations]
                return f"{entity_name} 的 {rel_type} 对象: {', '.join(targets)}"

            else:
                # 其他关系类型
                relations = self.get_relations(entity['id'], rel_type=rel_type)
                if not relations:
                    return f"{entity_name} 没有相关的 {rel_type} 关系"

                # 格式化答案
                return f"{entity_name} 的 {rel_type} 关系:\n" + "\n".join([
                    f"- {rel['target']}"
                    for rel in relations
                ])

        except Exception as e:
            logger.error(f"处理事实查询失败 {query}: {e}")
            return None

    def _parse_fact_query(self, query: str) -> Optional[tuple]:
        """
        解析事实类查询

        返回：(实体名, 关系类型)

        示例：
            "方源主修什么流派？" → ("方源", "主修")
            "方源持有哪些蛊虫？" → ("方源", "持有")
        """
        query = query.strip()

        # 关系关键词映射
        rel_keywords = {
            "主修": "主修",
            "属于": "属于",
            "持有": "持有",
            "师承": "师承",
            "盟友": "盟友",
            "敌对": "敌对",
            "背叛": "背叛",
        }

        # 查找关系关键词
        for rel_kw, rel_type in rel_keywords.items():
            if rel_kw in query:
                # 提取实体名（简化版）
                parts = query.split(rel_kw, 1)
                entity_name = parts[0].strip()
                return entity_name, rel_type

        return None

    # ==================== 辅助方法 ====================

    def _generate_entity_id(self, name: str) -> str:
        """生成实体 ID"""
        # 简单实现：使用拼音首字母或哈希
        # 实际可以使用 pypinyin 库
        import hashlib
        return "entity_" + hashlib.md5(name.encode()).hexdigest()[:8]

    def get_all_entities(self) -> List[Dict]:
        """获取所有实体"""
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, name, type, properties, aliases, source_chapter
                FROM entities ORDER BY name
            ''')

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

    def get_pending_review(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取待审核的实体列表

        Args:
            limit: 最大数量

        Returns:
            待审核列表
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 从 entities 表获取有属性的实体（待审核）
            cursor.execute('''
                SELECT name, type, properties, source_chapter
                FROM entities
                WHERE properties IS NOT NULL
                ORDER BY id DESC
                LIMIT ?
            ''', (limit,))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "name": row['name'],
                    "type": row['type'],
                    "properties": row['properties'],
                    "source_chapter": row['source_chapter']
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取待审核实体失败: {e}")
            return []

    # ==================== Phase 1: 负反馈闭环 + 时间维度 ====================

    def correct_entity_property(
        self,
        entity_name: str,
        property_name: str,
        new_value: Any,
        change_reason: str = None,
        changed_by: str = "system"
    ) -> bool:
        """
        修正实体属性（带历史记录和负反馈闭环）

        Args:
            entity_name: 实体名称
            property_name: 属性名
            new_value: 新值
            change_reason: 修正原因
            changed_by: 操作人

        Returns:
            是否成功
        """
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                logger.warning(f"实体不存在: {entity_name}")
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 获取当前属性
            cursor.execute('SELECT properties FROM entities WHERE id = ?', (entity_id,))
            row = cursor.fetchone()
            current_properties = json.loads(row['properties']) if row['properties'] else {}
            old_value = current_properties.get(property_name)

            # 记录旧值到修正日志
            if old_value is not None:
                cursor.execute('''
                    INSERT INTO correction_log (entity_id, old_value, new_value, change_reason)
                    VALUES (?, ?, ?, ?)
                ''', (entity_id, str(old_value), str(new_value), change_reason or "系统自动修正"))

            # 记录历史版本
            cursor.execute('''
                INSERT INTO entity_history (entity_id, old_properties, new_properties, change_reason, changed_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (entity_id,
                  json.dumps(current_properties, ensure_ascii=False) if current_properties else None,
                  json.dumps({property_name: new_value}, ensure_ascii=False),
                  change_reason or "用户手动修正",
                  changed_by))

            # 更新实体属性
            current_properties[property_name] = new_value
            cursor.execute('''
                UPDATE entities
                SET properties = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(current_properties, ensure_ascii=False), entity_id))

            conn.commit()
            conn.close()

            logger.info(f"实体属性已修正: {entity_name}.{property_name} = {new_value} (原因: {change_reason})")
            return True

        except Exception as e:
            logger.error(f"修正实体属性失败 {entity_name}: {e}")
            return False

    def get_entity_history(self, entity_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取实体的历史版本

        Args:
            entity_name: 实体名称
            limit: 最大数量

        Returns:
            历史版本列表
        """
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                return []

            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, entity_id, old_properties, new_properties, change_reason, changed_by, valid_from, valid_to, is_correction, created_at
                FROM entity_history
                WHERE entity_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (entity_id, limit))

            rows = cursor.fetchall()
            conn.close()

            # Debug: 打印第一行的键
            if rows:
                logger.debug(f"History row keys: {list(rows[0].keys())}")

            return [
                {
                    "id": row['id'],
                    "entity_id": row['entity_id'],
                    "old_properties": json.loads(row['old_properties']) if row['old_properties'] else {},
                    "new_properties": json.loads(row['new_properties']) if row['new_properties'] else {},
                    "change_reason": row['change_reason'],
                    "changed_by": row['changed_by'],
                    "valid_from": row['valid_from'],
                    "valid_to": row['valid_to'],
                    "is_correction": bool(row['is_correction']),
                    "created_at": row['created_at']
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取实体历史失败 {entity_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

        except Exception as e:
            logger.error(f"获取实体历史失败 {entity_name}: {e}")
            return []

    def rollback_entity_version(self, entity_name: str, version_id: int) -> bool:
        """
        回滚实体到指定历史版本

        Args:
            entity_name: 实体名称
            version_id: 历史版本 ID

        Returns:
            是否成功
        """
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                logger.warning(f"实体不存在: {entity_name}")
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 获取历史版本
            cursor.execute('''
                SELECT old_properties, new_properties, change_reason, changed_by, valid_to
                FROM entity_history
                WHERE id = ? AND entity_id = ?
            ''', (version_id, entity_id))

            row = cursor.fetchone()
            if not row:
                logger.warning(f"历史版本不存在: {version_id}")
                conn.close()
                return False

            # 设置 valid_to 为当前时间（标记为过期）
            cursor.execute('''
                UPDATE entity_history
                SET valid_to = CURRENT_TIMESTAMP
                WHERE id = ? AND entity_id = ?
            ''', (version_id, entity_id))

            # 恢复到 old_properties
            old_properties = json.loads(row['old_properties']) if row['old_properties'] else {}
            cursor.execute('''
                UPDATE entities
                SET properties = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(old_properties, ensure_ascii=False), entity_id))

            conn.commit()
            conn.close()

            logger.info(f"实体已回滚到版本 {version_id}: {entity_name}")
            return True

        except Exception as e:
            logger.error(f"回滚实体失败 {entity_name}: {e}")
            return False

    def get_pending_reviews(
        self,
        review_status: str = 'pending',
        limit: int = 20,
        entity_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        获取待审核的实体/关系列表（增强版）

        Args:
            review_status: 审核状态 (pending/approved/rejected)
            limit: 最大数量
            entity_type: 实体类型过滤

        Returns:
            待审核列表
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 构建查询
            if entity_type:
                cursor.execute('''
                    SELECT id, entity_id, entity_name, entity_type, properties, relation_type,
                           source_id, target_id, confidence, source_text, source_chapter,
                           review_status, reviewed_by, reviewed_at, created_at
                    FROM pending_reviews
                    WHERE review_status = ? AND entity_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (review_status, entity_type, limit))
            else:
                cursor.execute('''
                    SELECT id, entity_id, entity_name, entity_type, properties, relation_type,
                           source_id, target_id, confidence, source_text, source_chapter,
                           review_status, reviewed_by, reviewed_at, created_at
                    FROM pending_reviews
                    WHERE review_status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (review_status, limit))

            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row['id'],
                    "entity_id": row['entity_id'],
                    "entity_name": row['entity_name'],
                    "entity_type": row['entity_type'],
                    "properties": row['properties'],
                    "relation_type": row['relation_type'],
                    "source_id": row['source_id'],
                    "target_id": row['target_id'],
                    "confidence": row['confidence'],
                    "source_text": row['source_text'],
                    "source_chapter": row['source_chapter'],
                    "review_status": row['review_status'],
                    "reviewed_by": row['reviewed_by'],
                    "reviewed_at": row['reviewed_at'],
                    "created_at": row['created_at']
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"获取待审核项失败: {e}")
            return []

    def approve_review(self, review_id: int, reviewed_by: str = "system") -> bool:
        """
        审核通过待审核项

        Args:
            review_id: 审核项 ID
            reviewed_by: 审核人

        Returns:
            是否成功
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 获取审核项
            cursor.execute('''
                SELECT entity_id, entity_name, entity_type, properties, relation_type,
                       source_id, target_id, source_text, source_chapter
                FROM pending_reviews
                WHERE id = ? AND review_status = 'pending'
            ''', (review_id,))

            row = cursor.fetchone()
            if not row:
                logger.warning(f"待审核项不存在或已被审核: {review_id}")
                conn.close()
                return False

            # 根据类型处理
            if row['entity_type'] and row['properties']:
                # 实体属性审核
                properties = json.loads(row['properties']) if row['properties'] else {}
                self.add_entity(
                    name=row['entity_name'],
                    entity_type=row['entity_type'],
                    properties=properties,
                    source_chapter=row['source_chapter']
                )
            elif row['relation_type'] and row['source_id'] and row['target_id']:
                # 关系审核
                self.add_relationship(
                    source_name=row['entity_name'],
                    target_name=row['target_id'],
                    rel_type=row['relation_type'],
                    source_chapter=row['source_chapter']
                )
            else:
                logger.warning(f"待审核项格式不正确: {review_id}")
                conn.close()
                return False

            # 更新审核状态
            cursor.execute('''
                UPDATE pending_reviews
                SET review_status = 'approved', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reviewed_by, review_id))

            conn.commit()
            conn.close()

            logger.info(f"审核通过: {review_id}")
            return True

        except Exception as e:
            logger.error(f"审核通过失败: {e}")
            return False

    def reject_review(self, review_id: int, reject_reason: str = "", reviewed_by: str = "system") -> bool:
        """
        审核拒绝待审核项

        Args:
            review_id: 审核项 ID
            reject_reason: 拒绝原因
            reviewed_by: 审核人

        Returns:
            是否成功
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            # 更新审核状态
            cursor.execute('''
                UPDATE pending_reviews
                SET review_status = 'rejected', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reviewed_by, review_id))

            conn.commit()
            conn.close()

            logger.info(f"审核拒绝: {review_id} (原因: {reject_reason})")
            return True

        except Exception as e:
            logger.error(f"审核拒绝失败: {e}")
            return False

    def approve_entity(self, entity_id: str) -> bool:
        """
        批准实体（直接批准，不进入审核队列）

        Args:
            entity_id: 实体ID

        Returns:
            bool: 是否成功
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE entities
                SET status = 'approved'
                WHERE id = ?
            ''', (entity_id,))

            conn.commit()
            conn.close()

            logger.info(f"实体批准: {entity_id}")
            return True

        except Exception as e:
            logger.error(f"实体批准失败: {e}")
            return False

    def reject_entity(self, entity_id: str, reject_reason: str = "") -> bool:
        """
        拒绝实体（直接拒绝，不进入审核队列）

        Args:
            entity_id: 实体ID
            reject_reason: 拒绝原因

        Returns:
            bool: 是否成功
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE entities
                SET review_status = 'rejected', reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', ('system', entity_id))

            conn.commit()
            conn.close()

            logger.info(f"实体拒绝: {entity_id} (原因: {reject_reason})")
            return True

        except Exception as e:
            logger.error(f"实体拒绝失败: {e}")
            return False

    def delete_entity(self, entity_id: str) -> bool:
        """
        删除实体

        Args:
            entity_id: 实体ID

        Returns:
            bool: 是否成功
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('DELETE FROM entities WHERE id = ?', (entity_id,))

            conn.commit()
            conn.close()

            logger.info(f"实体已删除: {entity_id}")
            return True

        except Exception as e:
            logger.error(f"删除实体失败: {e}")
            return False

    def update_entity_type(self, entity_id: str, entity_type: str) -> bool:
        """
        更新实体类型

        Args:
            entity_id: 实体ID
            entity_type: 新类型

        Returns:
            bool: 是否成功
        """
        try:
            conn = self.connect()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE entities
                SET type = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (entity_type, entity_id))

            conn.commit()
            conn.close()

            logger.info(f"实体类型已更新: {entity_id} -> {entity_type}")
            return True

        except Exception as e:
            logger.error(f"更新实体类型失败: {e}")
            return False

    # ==================== Phase 3: 事实锚点管理 ====================

    def add_fact(self, entity_name: str, fact_type: str, fact_value: str,
                 confidence: float = 1.0, source: str = "manual",
                 verified_by: str = "system") -> bool:
        """
        添加一条经过验证的事实（硬约束）

        Args:
            entity_name: 实体名称
            fact_type: 事实类型（如：主修、持有、拥有、流派等）
            fact_value: 事实值
            confidence: 置信度（默认 1.0，表示确定事实）
            source: 来源（manual/auto/reasoning）
            verified_by: 验证人

        Returns:
            是否成功
        """
        try:
            entity_id = self.get_entity_id(entity_name)
            if not entity_id:
                logger.warning(f"实体不存在: {entity_name}")
                return False

            conn = self.connect()
            cursor = conn.cursor()

            # 检查是否已存在相同事实
            cursor.execute('''
                SELECT id FROM facts
                WHERE entity_id = ? AND fact_type = ? AND fact_value = ?
            ''', (entity_id, fact_type, fact_value))

            existing = cursor.fetchone()
            if existing:
                logger.info(f"事实已存在: {entity_name} -{fact_type}-> {fact_value}")
                conn.close()
                return True

            # 插入新事实
            cursor.execute('''
                INSERT INTO facts
                (entity_id, entity_name, fact_type, fact_value, confidence, source, verified_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                entity_id,
                entity_name,
                fact_type,
                fact_value,
                confidence,
                source,
                verified_by
            ))
            conn.commit()
            conn.close()

            logger.info(f"事实已添加: {entity_name}.{fact_type} = {fact_value} (置信度: {confidence})")
            return True

        except Exception as e:
            logger.error(f"添加事实失败: {e}")
            return False

    def get_facts_for_entity(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        获取实体的所有事实

        Args:
            entity_name: 实体名称

        Returns:
            事实列表
        """
        try:
            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, entity_id, entity_name, fact_type, fact_value,
                       confidence, source, verified_by, verified_at, created_at
                FROM facts
                WHERE entity_name = ?
                ORDER BY confidence DESC, created_at DESC
            ''', (entity_name,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"查询事实失败: {e}")
            return []

    def get_facts_for_query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        根据查询文本检索相关事实

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            事实列表
        """
        try:
            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 简单关键词匹配（可扩展为向量检索）
            keywords = query.split()
            if not keywords:
                conn.close()
                return []

            # 构建 OR 条件
            conditions = ' OR '.join(['fact_value LIKE ?' for _ in keywords])
            params = [f'%{kw}%' for kw in keywords]

            cursor.execute(f'''
                SELECT id, entity_id, entity_name, fact_type, fact_value,
                       confidence, source, verified_by, verified_at, created_at
                FROM facts
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
        """
        删除一条事实

        Args:
            fact_id: 事实 ID

        Returns:
            是否成功
        """
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

    def get_all_facts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取所有事实

        Args:
            limit: 返回数量限制

        Returns:
            事实列表
        """
        try:
            conn = self.connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, entity_id, entity_name, fact_type, fact_value,
                       confidence, source, verified_by, verified_at, created_at
                FROM facts
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            ''', (limit,))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"查询所有事实失败: {e}")
            return []


# ==================== 全局实例 ====================

# 全局 WikiDB 实例（单例模式）
