#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版 Flask 应用测试
"""
from flask import Flask, jsonify
from pathlib import Path
import sqlite3
import sys
from rag_config import BASE_DIR

DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
print(f'DB_PATH: {DB_PATH}')
print(f'Exists: {DB_PATH.exists()}')

app = Flask(__name__)

@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    print("DEBUG: api_stats called", file=sys.stderr)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute('SELECT COUNT(*) FROM entities')
    total_entities = cursor.fetchone()[0]
    print(f"DEBUG: total_entities={total_entities}", file=sys.stderr)

    cursor = conn.execute('SELECT COUNT(*) FROM relationships')
    total_relations = cursor.fetchone()[0]
    print(f"DEBUG: total_relations={total_relations}", file=sys.stderr)

    conn.close()

    result = {
        "total_entities": total_entities,
        "total_relations": total_relations,
        "pending_entities": 0,
        "pending_relations": 117
    }
    print(f"DEBUG: result={result}", file=sys.stderr)
    response = jsonify(result)
    print(f"DEBUG: response={response}", file=sys.stderr)
    return response

if __name__ == '__main__':
    print("Starting Flask server...")
    print("Routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.rule} -> {rule.endpoint}")
    app.run(host='0.0.0.0', port=5000, debug=False)
