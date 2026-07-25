#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版 Wiki 知识图谱管理系统测试
"""
import sys
import sqlite3
from pathlib import Path
from rag_config import BASE_DIR

DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'

def test_db():
    """测试数据库连接"""
    print("Testing database connection...")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute('SELECT COUNT(*) FROM entities')
    total_entities = cursor.fetchone()[0]
    cursor = conn.execute('SELECT COUNT(*) FROM relationships')
    total_relations = cursor.fetchone()[0]
    conn.close()
    print(f"Entities: {total_entities}")
    print(f"Relations: {total_relations}")

if __name__ == '__main__':
    test_db()
