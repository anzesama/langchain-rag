# 在 wiki_db.py 的 get_stats() 方法之后添加以下方法

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
