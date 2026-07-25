#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wiki 审核 Web 界面（增强版）

功能：
- 查看待审核的实体和关系
- 批准/拒绝实体
- 批准/拒绝关系
- 手动添加实体
- 数据同步（ChromaDB + Wiki DB）
"""
import sys
import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime

# Fix GBK encoding
if sys.platform == 'win32':
    import io
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template_string, request, jsonify
from rag_core.knowledge_base import KnowledgeBase
from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_config import BASE_DIR

app = Flask(__name__)

DB_PATH = BASE_DIR / 'data' / 'wiki' / 'wiki.db'
CHROMA_DB_PATH = BASE_DIR / 'storage' / 'knowledge_base'


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wiki 审核系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Microsoft YaHei', sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab {
            padding: 10px 20px;
            background: #fff;
            border: none;
            cursor: pointer;
            border-radius: 5px;
            font-size: 16px;
            transition: all 0.3s;
        }
        .tab.active {
            background: #1890ff;
            color: #fff;
        }
        .tab:hover { opacity: 0.8; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card {
            background: #fff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .card h2 { margin-bottom: 15px; color: #333; }
        .entity-list, .relation-list { list-style: none; }
        .entity-item, .relation-item {
            padding: 15px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .entity-item:hover, .relation-item:hover { background: #f9f9f9; }
        .entity-info, .relation-info { flex: 1; }
        .entity-name { font-weight: bold; font-size: 18px; color: #333; }
        .entity-type { color: #666; font-size: 14px; }
        .relation-info { display: flex; align-items: center; gap: 10px; }
        .relation-text { font-size: 16px; }
        .relation-type { color: #1890ff; font-weight: bold; }
        .actions { display: flex; gap: 10px; }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .btn-approve { background: #52c41a; color: #fff; }
        .btn-approve:hover { background: #389e0d; }
        .btn-reject { background: #ff4d4f; color: #fff; }
        .btn-reject:hover { background: #cf1322; }
        .btn-view { background: #1890ff; color: #fff; }
        .btn-view:hover { background: #096dd9; }
        .btn-add { background: #722ed1; color: #fff; }
        .btn-add:hover { background: #531dab; }
        .btn-sync { background: #faad14; color: #fff; }
        .btn-sync:hover { background: #d48806; }
        .btn:hover { opacity: 0.9; }
        .entity-details { margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }
        .detail-row { margin-bottom: 8px; }
        .detail-label { font-weight: bold; color: #666; }
        .detail-value { color: #333; }
        .empty { text-align: center; padding: 40px; color: #999; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-card {
            background: #fff;
            border-radius: 8px;
            padding: 20px;
            flex: 1;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .stat-number { font-size: 32px; font-weight: bold; color: #1890ff; }
        .stat-label { color: #666; margin-top: 5px; }
        
        /* 模态框 */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
        }
        .modal-content {
            background: #fff;
            border-radius: 8px;
            padding: 30px;
            max-width: 500px;
            margin: 100px auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .modal-header {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }
        .form-group { margin-bottom: 15px; }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #666;
        }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        .form-group textarea {
            height: 100px;
            resize: vertical;
        }
        .modal-footer {
            display: flex;
            gap: 10px;
            margin-top: 20px;
            justify-content: flex-end;
        }
        .close-btn {
            background: #999;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Wiki 审核系统</h1>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number" id="pending-entities">0</div>
                <div class="stat-label">待审核实体</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="pending-relations">0</div>
                <div class="stat-label">待审核关系</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" onclick="showTab('entities')">实体审核</button>
            <button class="tab" onclick="showTab('relations')">关系审核</button>
            <button class="tab" onclick="showTab('sync')">数据同步</button>
        </div>

        <div id="entities" class="tab-content active">
            <div class="card">
                <h2>待审核实体列表</h2>
                <ul class="entity-list" id="entity-list">
                    <li class="empty">加载中...</li>
                </ul>
            </div>
        </div>

        <div id="relations" class="tab-content">
            <div class="card">
                <h2>待审核关系列表</h2>
                <ul class="relation-list" id="relation-list">
                    <li class="empty">加载中...</li>
                </ul>
            </div>
        </div>

        <div id="sync" class="tab-content">
            <div class="card">
                <h2>数据同步</h2>
                <p style="color: #666; margin-bottom: 20px;">将 Wiki 数据同步到 ChromaDB 向量数据库</p>
                <button class="btn btn-sync" onclick="syncToChromaDB()">开始同步</button>
                <div id="sync-status" style="margin-top: 20px; padding: 15px; background: #f0f0f0; border-radius: 5px; display: none;">
                    <div id="sync-progress">准备中...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- 手动添加实体模态框 -->
    <div id="add-entity-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">手动添加实体</div>
            <div class="form-group">
                <label>实体名称</label>
                <input type="text" id="add-entity-name" placeholder="输入实体名称">
            </div>
            <div class="form-group">
                <label>实体类型</label>
                <input type="text" id="add-entity-type" placeholder="例如：人物、蛊虫、势力">
            </div>
            <div class="form-group">
                <label>属性（JSON格式）</label>
                <textarea id="add-entity-properties" placeholder='{"主修": "力道", "资质": "甲等"}'></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn close-btn" onclick="closeAddEntityModal()">取消</button>
                <button class="btn btn-approve" onclick="addEntity()">添加</button>
            </div>
        </div>
    </div>

    <script>
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tab).classList.add('active');

            if (tab === 'entities') {
                loadEntities();
            } else if (tab === 'relations') {
                loadRelations();
            } else if (tab === 'sync') {
                // 切换到同步标签时，检查同步状态
                checkSyncStatus();
            }
        }

        function loadEntities() {
            fetch('/api/entities')
                .then(res => res.json())
                .then(data => {
                    const list = document.getElementById('entity-list');
                    if (data.entities.length === 0) {
                        list.innerHTML = '<li class="empty">暂无待审核实体</li>';
                        return;
                    }
                    list.innerHTML = data.entities.map(entity => `
                        <li class="entity-item">
                            <div class="entity-info">
                                <div class="entity-name">${entity.name}</div>
                                <div class="entity-type">${entity.type} - ${entity.source_chapter}</div>
                                <div class="entity-details">
                                    ${Object.entries(entity.properties || {}).map(([k, v]) => `
                                        <div class="detail-row">
                                            <span class="detail-label">${k}:</span>
                                            <span class="detail-value">${v}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                            <div class="actions">
                                <button class="btn btn-add" onclick="showAddEntityModal('${entity.name}', '${entity.type}')">手动添加</button>
                                <button class="btn btn-approve" onclick="approveEntity('${entity.id}')">批准</button>
                                <button class="btn btn-reject" onclick="rejectEntity('${entity.id}')">拒绝</button>
                            </div>
                        </li>
                    `).join('');
                });
        }

        function loadRelations() {
            fetch('/api/relations')
                .then(res => res.json())
                .then(data => {
                    const list = document.getElementById('relation-list');
                    if (data.relations.length === 0) {
                        list.innerHTML = '<li class="empty">暂无待审核关系</li>';
                        return;
                    }
                    list.innerHTML = data.relations.map(rel => `
                        <li class="relation-item">
                            <div class="relation-info">
                                <div class="relation-text">
                                    <span style="color: #666;">${rel.source}</span>
                                    <span class="relation-type">[${rel.rel_type}]</span>
                                    <span style="color: #666;">${rel.target}</span>
                                </div>
                                <div style="color: #999; font-size: 12px;">${rel.source_chapter}</div>
                            </div>
                            <div class="actions">
                                <button class="btn btn-add" onclick="showAddEntityModal('${rel.source}', '${rel.target}')">手动添加</button>
                                <button class="btn btn-approve" onclick="approveRelation(${rel.id})">批准</button>
                                <button class="btn btn-reject" onclick="rejectRelation(${rel.id})">拒绝</button>
                            </div>
                        </li>
                    `).join('');
                });
        }

        async function approveEntity(id) {
            await fetch(`/api/entities/${id}/approve`, { method: 'POST' });
            loadEntities();
            loadStats();
        }

        async function rejectEntity(id) {
            await fetch(`/api/entities/${id}/reject`, { method: 'POST' });
            loadEntities();
            loadStats();
        }

        async function approveRelation(id) {
            await fetch(`/api/relations/${id}/approve`, { method: 'POST' });
            loadRelations();
            loadStats();
        }

        async function rejectRelation(id) {
            await fetch(`/api/relations/${id}/reject`, { method: 'POST' });
            loadRelations();
            loadStats();
        }

        async function loadStats() {
            const res = await fetch('/api/stats');
            const data = await res.json();
            document.getElementById('pending-entities').textContent = data.pending_entities;
            document.getElementById('pending-relations').textContent = data.pending_relations;
        }

        // 模态框操作
        function showAddEntityModal(name, type) {
            document.getElementById('add-entity-name').value = name;
            document.getElementById('add-entity-type').value = type;
            document.getElementById('add-entity-modal').style.display = 'block';
        }

        function closeAddEntityModal() {
            document.getElementById('add-entity-modal').style.display = 'none';
        }

        async function addEntity() {
            const name = document.getElementById('add-entity-name').value;
            const type = document.getElementById('add-entity-type').value;
            const properties = document.getElementById('add-entity-properties').value;

            if (!name) {
                alert('请输入实体名称');
                return;
            }

            try {
                const res = await fetch('/api/entities', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, type, properties})
                });
                const data = await res.json();
                if (data.success) {
                    alert('添加成功');
                    closeAddEntityModal();
                    loadEntities();
                    loadStats();
                } else {
                    alert('添加失败: ' + data.error);
                }
            } catch (e) {
                alert('添加失败: ' + e.message);
            }
        }

        // 数据同步
        async function syncToChromaDB() {
            const statusDiv = document.getElementById('sync-status');
            const progressDiv = document.getElementById('sync-progress');
            statusDiv.style.display = 'block';
            progressDiv.innerHTML = '开始同步...';

            try {
                const res = await fetch('/api/sync', { method: 'POST' });
                const data = await res.json();

                if (data.success) {
                    progressDiv.innerHTML = `
                        <div style="color: #52c41a; font-weight: bold;">同步完成！</div>
                        <div style="color: #666; margin-top: 5px;">已同步实体: ${data.entities_synced}</div>
                        <div style="color: #666;">已同步关系: ${data.relations_synced}</div>
                    `;
                } else {
                    progressDiv.innerHTML = `<div style="color: #ff4d4f;">同步失败: ${data.error}</div>`;
                }
            } catch (e) {
                progressDiv.innerHTML = `<div style="color: #ff4d4f;">同步失败: ${e.message}</div>`;
            }
        }

        async function checkSyncStatus() {
            try {
                const res = await fetch('/api/sync/status');
                const data = await res.json();
                if (data.status) {
                    const statusDiv = document.getElementById('sync-status');
                    const progressDiv = document.getElementById('sync-progress');
                    statusDiv.style.display = 'block';
                    progressDiv.innerHTML = data.status;
                }
            } catch (e) {
                // 忽略错误
            }
        }

        // 初始加载
        loadStats();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """主页"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/entities')
def api_entities():
    """获取待审核实体列表"""
    conn = get_db_connection()
    cursor = conn.execute('''
        SELECT id, name, type, properties, source_chapter
        FROM entities
        WHERE properties IS NOT NULL
        ORDER BY id DESC
        LIMIT 50
    ''')
    entities = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({"entities": entities})


@app.route('/api/relations')
def api_relations():
    """获取待审核关系列表"""
    conn = get_db_connection()
    cursor = conn.execute('''
        SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
               e1.name as source_name, e2.name as target_name
        FROM relationships r
        JOIN entities e1 ON r.source_id = e1.id
        JOIN entities e2 ON r.target_id = e2.id
        ORDER BY r.id DESC
        LIMIT 50
    ''')
    relations = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({"relations": relations})


@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    conn = get_db_connection()

    # 待审核实体数
    cursor = conn.execute('SELECT COUNT(*) FROM entities WHERE properties IS NOT NULL')
    pending_entities = cursor.fetchone()[0]

    # 待审核关系数
    cursor = conn.execute('SELECT COUNT(*) FROM relationships')
    pending_relations = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "pending_entities": pending_entities,
        "pending_relations": pending_relations
    })


@app.route('/api/entities/<entity_id>/approve', methods=['POST'])
def approve_entity(entity_id):
    """批准实体"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 更新审核状态（如果使用 pending_reviews 表）
        # 这里简单处理：实体已经存在，不需要额外操作
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/entities/<entity_id>/reject', methods=['POST'])
def reject_entity(entity_id):
    """拒绝实体"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 删除实体
        cursor.execute('DELETE FROM entities WHERE id = ?', (entity_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/relations/<relation_id>/approve', methods=['POST'])
def approve_relation(relation_id):
    """批准关系"""
    try:
        # 关系已经存在，不需要额外操作
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/relations/<relation_id>/reject', methods=['POST'])
def reject_relation(relation_id):
    """拒绝关系"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 删除关系
        cursor.execute('DELETE FROM relationships WHERE id = ?', (relation_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/entities', methods=['POST'])
def add_entity():
    """手动添加实体"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        type_ = data.get('type', '未分类').strip()
        properties = data.get('properties', '{}')

        if not name:
            return jsonify({"success": False, "error": "实体名称不能为空"}), 400

        # 确保数据库存在
        db_path = Path('D:/class/project-config/data/wiki/wiki.db')
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        wiki_db = WikiDB(str(db_path))
        wiki_db.init_db()

        # 添加实体
        wiki_db.add_entity(name, type_, json.loads(properties) if properties else {})

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/sync', methods=['POST'])
def sync_to_chroma():
    """同步 Wiki 数据到 ChromaDB"""
    try:
        db_path = Path('D:/class/project-config/data/wiki/wiki.db')
        chroma_path = Path('D:/class/project-config/storage/knowledge_base')

        # 初始化 Wiki DB
        wiki_db = WikiDB(str(db_path))
        wiki_db.init_db()

        # 初始化 ChromaDB
        kb = KnowledgeBase()
        kb.vectorstore = kb._EmbeddingWrapper(kb.embeddings)

        # 获取所有实体
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT id, name, type, properties FROM entities')
        entities = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # 获取所有关系
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT r.id, e1.name as source_name, e2.name as target_name, r.rel_type
            FROM relationships r
            JOIN entities e1 ON r.source_id = e1.id
            JOIN entities e2 ON r.target_id = e2.id
        ''')
        relations = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # 同步实体到 ChromaDB
        entities_synced = 0
        for entity in entities:
            try:
                content = f"{entity['name']} ({entity['type']})\n"
                if entity['properties']:
                    content += f"属性: {json.dumps(entity['properties'], ensure_ascii=False)}"

                # 添加到 ChromaDB
                kb.add_document(
                    filepath=db_path.parent / f"wiki_entity_{entity['id']}.txt",
                    content=content,
                    metadata={
                        'type': 'wiki_entity',
                        'entity_name': entity['name'],
                        'entity_type': entity['type']
                    }
                )
                entities_synced += 1
            except Exception as e:
                print(f"同步实体失败 {entity['name']}: {e}")

        # 同步关系到 ChromaDB
        relations_synced = 0
        for rel in relations:
            try:
                content = f"{rel['source_name']} -{rel['rel_type']}-> {rel['target_name']}"
                
                # 添加到 ChromaDB
                kb.add_document(
                    filepath=db_path.parent / f"wiki_relation_{rel['id']}.txt",
                    content=content,
                    metadata={
                        'type': 'wiki_relation',
                        'source': rel['source_name'],
                        'target': rel['target_name'],
                        'relation_type': rel['rel_type']
                    }
                )
                relations_synced += 1
            except Exception as e:
                print(f"同步关系失败 {rel['source_name']} -{rel['rel_type']}-> {rel['target_name']}: {e}")

        return jsonify({
            "success": True,
            "entities_synced": entities_synced,
            "relations_synced": relations_synced
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/sync/status')
def sync_status():
    """获取同步状态"""
    return jsonify({"status": ""})


if __name__ == '__main__':
    print("=" * 70)
    print("  Wiki 审核系统（增强版）")
    print("=" * 70)
    print(f"数据库: {DB_PATH}")
    print(f"ChromaDB: {CHROMA_DB_PATH}")
    print("=" * 70)
    print("\n访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
