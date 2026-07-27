#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wiki 知识图谱管理 Web 界面（完整版 + 知识图谱 + LLM）

功能：
- 实体管理（查看、添加、编辑、删除、批准/拒绝）
- 关系管理（查看、添加、编辑、删除、批准/拒绝）
- 知识图谱可视化（ECharts，实时更新）
- LLM 辅助判断（调用 LLM 审核实体和关系）
- 数据同步（ChromaDB + Wiki DB）
- 统计信息
- 实体/关系上下文信息展示
"""
import sys
import sqlite3
import json
import shutil
import logging
import time
import requests
from pathlib import Path
from datetime import datetime

# 配置 logger
logger = logging.getLogger(__name__)

# LLM 审核结果缓存
llm_cache = {}
CACHE_EXPIRE_SECONDS = 300  # 缓存 5 分钟

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
from rag_core.wiki_db import WikiDB, get_wiki_db
from rag_config import AGNES_API_KEY, AGNES_API_BASE, BASE_DIR

# 延迟导入 KnowledgeBase，避免启动时初始化
KnowledgeBase = None
KnowledgeBaseClass = None

def get_knowledge_base():
    global KnowledgeBase, KnowledgeBaseClass
    if KnowledgeBaseClass is None:
        from rag_core.knowledge_base import KnowledgeBase as KB
        KnowledgeBaseClass = KB
    if KnowledgeBase is None:
        KnowledgeBase = KnowledgeBaseClass()
    return KnowledgeBase

app = Flask(__name__)

DB_PATH = BASE_DIR / 'storage' / 'knowledge_base.db'
CHROMA_DB_PATH = BASE_DIR / 'storage' / 'knowledge_base'


def get_db_connection():
    """获取数据库连接，强制开启外键约束"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db_schema():
    """确保 entities 表有 status 字段"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("PRAGMA table_info(entities)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'status' not in columns:
            conn.execute("ALTER TABLE entities ADD COLUMN status TEXT DEFAULT 'pending'")
            conn.execute("ALTER TABLE relationships ADD COLUMN status TEXT DEFAULT 'pending'")
            conn.commit()
            logger.info("已添加 status 字段到 entities 和 relationships 表")
    finally:
        conn.close()


def call_llm(prompt: str, max_tokens: int = 2000) -> str:
    """调用 Agnes API（或 OpenAI 兼容 API）"""
    if not AGNES_API_KEY:
        raise ValueError("AGNES_API_KEY 未设置")

    base_url = AGNES_API_BASE.rstrip('/') + '/v1'
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AGNES_API_KEY}"
    }
    data = {
        "model": "agnes-2.0-flash",
        "messages": [
            {"role": "system", "content": "你是一个专业的知识图谱审核助手，只返回 JSON 格式的结果。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=120
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            if attempt == 2:
                raise
            time.sleep(2)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1)
    raise RuntimeError("LLM 调用失败")


# HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wiki 知识图谱管理系统</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Microsoft YaHei', sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 1800px; margin: 0 auto; }

        /* Header */
        header {
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 { color: #333; font-size: 24px; }

        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-number {
            font-size: 32px;
            font-weight: bold;
            color: #1890ff;
            margin-bottom: 5px;
        }
        .stat-label { color: #666; }

        /* Navigation Tabs */
        .nav-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            background: #fff;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .nav-tab {
            padding: 10px 20px;
            background: none;
            border: none;
            cursor: pointer;
            border-radius: 4px;
            font-size: 14px;
            color: #666;
            transition: all 0.3s;
        }
        .nav-tab:hover { background: #f0f0f0; }
        .nav-tab.active {
            background: #1890ff;
            color: #fff;
        }

        /* Content Panels */
        .panel {
            background: #fff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }
        .panel-title { font-size: 18px; font-weight: bold; color: #333; }

        /* Search Bar */
        .search-bar {
            display: flex;
            gap: 10px;
        }
        .search-input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }

        /* Buttons */
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .btn-primary { background: #1890ff; color: #fff; }
        .btn-primary:hover { background: #096dd9; }
        .btn-success { background: #52c41a; color: #fff; }
        .btn-success:hover { background: #389e0d; }
        .btn-danger { background: #ff4d4f; color: #fff; }
        .btn-danger:hover { background: #cf1322; }
        .btn-warning { background: #faad14; color: #fff; }
        .btn-warning:hover { background: #d48806; }
        .btn-secondary { background: #999; color: #fff; }
        .btn-secondary:hover { background: #666; }
        .btn-purple { background: #722ed1; color: #fff; }
        .btn-purple:hover { background: #531dab; }
        .btn:hover { opacity: 0.9; }

        /* Tables */
        .data-table {
            width: 100%;
            border-collapse: collapse;
        }
        .data-table th, .data-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        .data-table th {
            background: #f5f5f5;
            font-weight: 600;
            color: #333;
        }
        .data-table tr:hover { background: #f9f9f9; }
        .data-table .type-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
        }
        .type-人物 { background: #e6f7ff; color: #1890ff; }
        .type-蛊虫 { background: #f6ffed; color: #52c41a; }
        .type-势力 { background: #fff7e6; color: #fa8c16; }
        .type-流派 { background: #fff0f6; color: #eb2f96; }
        .type-地点 { background: #f9f0ff; color: #722ed1; }
        .type-境界 { background: #f6ffed; color: #52c41a; }
        .type-未分类 { background: #f5f5f5; color: #999; }

        /* Action Buttons */
        .action-buttons { display: flex; gap: 8px; }
        .action-buttons .btn { padding: 6px 12px; font-size: 12px; }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }

        /* Modal */
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
            max-width: 600px;
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
            font-size: 14px;
        }
        .form-group input, .form-group textarea, .form-group select {
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

        /* Tooltip */
        .tooltip {
            position: absolute;
            background: rgba(0,0,0,0.8);
            color: #fff;
            padding: 10px 15px;
            border-radius: 4px;
            font-size: 12px;
            max-width: 300px;
            pointer-events: none;
            z-index: 2000;
            line-height: 1.6;
        }

        /* Graph Visualization */
        .graph-container {
            height: 700px;
            background: #fff;
            border-radius: 8px;
            padding: 20px;
            position: relative;
        }
        #graph-chart {
            width: 100%;
            height: 600px;
        }
        .graph-controls {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
            z-index: 100;
        }
        .graph-info {
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(255,255,255,0.9);
            padding: 10px 15px;
            border-radius: 4px;
            font-size: 12px;
            color: #666;
        }

        /* LLM Modal */
        .llm-modal-content {
            max-width: 800px;
            height: 70vh;
            overflow-y: auto;
        }

        /* Detail Panel */
        .detail-panel {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 300px;
            background: #fff;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            display: none;
            z-index: 100;
        }
        .detail-panel h3 {
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }
        .detail-item {
            margin-bottom: 10px;
        }
        .detail-label {
            font-weight: bold;
            color: #666;
            font-size: 12px;
        }
        .detail-value {
            color: #333;
            font-size: 14px;
        }

        /* Context Modal */
        .context-modal-content {
            max-width: 800px;
            height: 70vh;
            overflow-y: auto;
        }

        /* Loading */
        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #1890ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Toast */
        .toast {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 12px 24px;
            border-radius: 4px;
            color: #fff;
            font-size: 14px;
            z-index: 3000;
            animation: slideDown 0.3s ease;
        }

        @keyframes slideDown {
            from { top: -50px; opacity: 0; }
            to { top: 20px; opacity: 1; }
        }

        .connecting-hint {
            position: fixed;
            top: 70px;
            left: 50%;
            transform: translateX(-50%);
            background: #e6f7ff;
            border: 2px solid #1890ff;
            border-radius: 6px;
            padding: 8px 20px;
            z-index: 2000;
            font-size: 14px;
            color: #0050b3;
            display: none;
        }
        .connecting-hint .cancel-link {
            margin-left: 12px;
            color: #ff4d4f;
            cursor: pointer;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div id="connecting-hint" class="connecting-hint">
        正在创建关系：已选中 <strong id="connecting-source-name"></strong>，
        请点击目标节点完成连线
        <span class="connecting-link" onclick="cancelConnecting()">取消</span>
    </div>
    <div class="container">
        <header>
            <h1>Wiki 知识图谱管理系统</h1>
        </header>

        <!-- Stats Cards -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="stat-entities">0</div>
                <div class="stat-label">总实体数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="stat-relations">0</div>
                <div class="stat-label">总关系数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="stat-pending-entities">0</div>
                <div class="stat-label">待审核实体</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="stat-pending-relations">0</div>
                <div class="stat-label">待审核关系</div>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="nav-tab active" data-panel="graph">知识图谱</button>
            <button class="nav-tab" data-panel="llm">LLM 辅助判断</button>
            <button class="nav-tab" data-panel="search">知识库搜索</button>
        </div>

        <!-- Graph Panel -->
        <div id="panel-graph" class="panel">
            <div class="panel-header">
                <div class="panel-title">知识图谱可视化</div>
                <div class="graph-controls">
                    <button class="btn btn-primary" onclick="openAddEntityModal()">+ 添加实体</button>
                    <button class="btn btn-primary" onclick="openAddRelationModal()">+ 添加关系</button>
                    <button class="btn btn-secondary" onclick="loadGraph()">刷新</button>
                    <button class="btn btn-secondary" onclick="exportGraph()">导出</button>
                </div>
            </div>
            <div class="graph-container" id="graph-container">
                <div id="graph-chart"></div>
                <div class="graph-info">
                    实体数: <span id="graph-entity-count">0</span> | 关系数: <span id="graph-relation-count">0</span>
                    <span style="margin-left: 16px;">
                        显示数量:
                        <select id="graph-limit" onchange="reloadGraphData()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px; margin-left: 6px;">
                            <option value="50">50</option>
                            <option value="100">100</option>
                            <option value="200" selected>200</option>
                            <option value="500">500</option>
                            <option value="0">全部</option>
                        </select>
                        <label style="cursor: pointer; margin-left: 12px; color: #666;">
                            <input type="checkbox" id="graph-connected-only" checked onchange="reloadGraphData()"> 仅已连接
                        </label>
                    </span>
                </div>
                <div id="detail-panel" class="detail-panel">
                    <h3>实体详情</h3>
                    <div id="detail-content"></div>
                    <div class="detail-actions" style="margin-top: 12px;">
                    <button class="btn btn-primary" onclick="editSelectedEntity()">编辑</button>
                    <button class="btn btn-danger" onclick="deleteSelectedEntity()">删除</button>
                    <button class="btn btn-success" onclick="startConnectingFromSelectedEntity()">连线创建关系</button>
                    </div>
                    <h4 style="margin-top: 16px;">关联关系</h4>
                    <div id="related-relations"></div>
                </div>
                <div id="detail-empty" class="detail-panel" style="display: block;">
                    <h3>实体详情</h3>
                    <p style="color: #999; text-align: center; padding: 40px 0;">点击图谱中的节点查看实体详情</p>
                </div>
            </div>
        </div>

        <!-- LLM Panel -->
        <div id="panel-llm" class="panel" style="display: none;">
            <div class="panel-header">
                <div class="panel-title">LLM 辅助判断</div>
                <div class="search-bar">
                    <select id="llm-type" class="search-input" style="width: 150px;">
                        <option value="entity">审核实体</option>
                        <option value="relation">审核关系</option>
                    </select>
                    <button class="btn btn-purple" onclick="runLLMReview()">开始审核</button>
                </div>
            </div>
            <div id="llm-results" style="margin-top: 20px;">
                <div class="empty-state">选择实体或关系类型，点击"开始审核"让 LLM 帮助判断</div>
            </div>
        </div>

        <!-- Sync Panel (已在 libsql 统一存储中移除) -->

        <!-- Search Panel -->
        <div id="panel-search" class="panel" style="display: none;">
            <div class="panel-header">
                <div class="panel-title">知识库语义搜索</div>
            </div>
            <div style="margin-bottom: 20px;">
                <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                    <input type="text" id="search-query" class="search-input" placeholder="输入搜索关键词，如：交叉检验、特征工程..." style="flex: 1;">
                    <select id="search-k" style="width: 100px; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">
                        <option value="5">Top 5</option>
                        <option value="10" selected>Top 10</option>
                        <option value="20">Top 20</option>
                    </select>
                    <button class="btn btn-primary" onclick="searchKnowledge()">搜索</button>
                    <button class="btn btn-secondary" onclick="clearSearch()">清空</button>
                </div>
                <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
                    <label style="cursor: pointer; color: #666;">
                        <input type="checkbox" id="search-show-score" checked> 显示相似度分数
                    </label>
                    <label style="cursor: pointer; color: #666;">
                        <input type="checkbox" id="search-show-chunks" checked> 显示完整文本
                    </label>
                    <label style="cursor: pointer; color: #666;">
                        <input type="checkbox" id="search-highlight"> 高亮关键词
                    </label>
                </div>
            </div>
            <div id="search-status" style="margin-bottom: 10px; color: #666;">
                <span id="search-total">知识库共 0 个文档块</span>
            </div>
            <div id="search-results" style="max-height: 600px; overflow-y: auto;">
                <div class="empty-state">输入关键词开始语义搜索</div>
            </div>
        </div>
    </div>

    <!-- Add/Edit Entity Modal -->
    <div id="entity-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header" id="entity-modal-title">添加实体</div>
            <div class="form-group">
                <label>实体名称</label>
                <input type="text" id="entity-name" placeholder="输入实体名称">
            </div>
            <div class="form-group">
                <label>实体类型</label>
                <select id="entity-type" onchange="onEntityTypeChange()">
                    <option value="人物">人物</option>
                    <option value="蛊虫">蛊虫</option>
                    <option value="势力">势力</option>
                    <option value="流派">流派</option>
                    <option value="地点">地点</option>
                    <option value="境界">境界</option>
                    <option value="未分类">未分类</option>
                    <option value="__custom__">其他... (手动输入)</option>
                </select>
                <input type="text" id="entity-type-custom" placeholder="输入自定义分类" style="display:none; margin-top: 6px;">
            </div>
            <div class="form-group">
                <label>属性（JSON格式）</label>
                <textarea id="entity-properties" placeholder='{"主修": "力道", "资质": "甲等"}'></textarea>
            </div>
            <div class="form-group">
                <label>来源章节</label>
                <input type="text" id="entity-source" placeholder="例如：第1章">
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeEntityModal()">取消</button>
                <button class="btn btn-success" onclick="saveEntity()">保存</button>
            </div>
        </div>
    </div>

    <!-- Add/Edit Relation Modal -->
    <div id="relation-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header" id="relation-modal-title">添加关系</div>
            <div class="form-group">
                <label>源实体</label>
                <select id="relation-source"><option value="">选择源实体</option></select>
            </div>
            <div class="form-group">
                <label>关系类型</label>
                <select id="relation-type">
                    <option value="持有">持有</option>
                    <option value="属于">属于</option>
                    <option value="主修">主修</option>
                    <option value="师承">师承</option>
                    <option value="盟友">盟友</option>
                    <option value="敌对">敌对</option>
                    <option value="击杀">击杀</option>
                    <option value="使用">使用</option>
                    <option value="控制">控制</option>
                </select>
            </div>
            <div class="form-group">
                <label>目标实体</label>
                <select id="relation-target"><option value="">选择目标实体</option></select>
            </div>
            <div class="form-group">
                <label>来源章节</label>
                <input type="text" id="relation-source-chapter" placeholder="例如：第1章">
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeRelationModal()">取消</button>
                <button class="btn btn-success" onclick="saveRelation()">保存</button>
            </div>
        </div>
    </div>

    <!-- LLM Review Modal -->
    <div id="llm-modal" class="modal">
        <div class="modal-content llm-modal-content">
            <div class="modal-header">
                <span id="llm-modal-title">LLM 审核结果</span>
                <button class="btn btn-secondary" onclick="closeLLMModal()" style="float: right;">关闭</button>
            </div>
            <div id="llm-content">
                <div class="empty-state">LLM 正在审核中...</div>
            </div>
        </div>
    </div>

    <!-- Context Modal -->
    <div id="context-modal" class="modal">
        <div class="modal-content context-modal-content">
            <div class="modal-header">
                <span id="context-modal-title">实体上下文信息</span>
                <button class="btn btn-secondary" onclick="closeContextModal()" style="float: right;">关闭</button>
            </div>
            <div id="context-content">
                <div class="empty-state">加载中...</div>
            </div>
        </div>
    </div>

    <script>
        // 全局变量
        let entities = [];
        let relations = [];
        let editingEntityId = null;
        let editingRelationId = null;
        let graphChart = null;
        let selectedEntity = null;
        let connectingSource = null;
        let connectingSourceName = null;

        // ========== 面板切换 ==========
        function showPanel(panelName, evt) {
            console.log('[showPanel]', panelName);
            document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
            let activeTab = evt ? evt.currentTarget : document.querySelector(`.nav-tab[data-panel="${panelName}"]`);
            if (activeTab) activeTab.classList.add('active');

            document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
            const panel = document.getElementById('panel-' + panelName);
            if (panel) {
                panel.style.display = 'block';
            } else {
                console.warn('Panel not found:', panelName);
                return;
            }

            // 仅在图表面板加载图谱
            if (panelName === 'graph') {
                loadGraph();
            }
        }

        // ========== 初始化 ==========
        document.addEventListener('DOMContentLoaded', function() {
            // 导航绑定
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.addEventListener('click', function(e) {
                    const name = this.dataset.panel;
                    if (name) showPanel(name, e);
                });
            });

            // 搜索框回车绑定
            document.getElementById('search-query').addEventListener('keydown', function(e) {
                if (e.key === 'Enter') searchKnowledge();
            });

            // 加载数据
            loadStats();
            loadEntities();
            loadRelations();
            // 等待 entities 和 relations 加载完成后渲染图谱
            Promise.all([loadEntities(), loadRelations()]).then(function() {
                loadGraph();
            });
        });

        // ========== 页面关闭提示 ==========
        window.addEventListener('beforeunload', function(e) {
            if (entities.length > 0 || relations.length > 0) {
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // ========== 其余函数（loadStats, loadEntities, ...）保持不变 ==========
        // 请将您的 loadStats, loadEntities, loadRelations, renderEntityTable, ... 等函数放在这里
        // 注意不要放在任何回调函数内部，保持顶级作用域。

        // 加载统计数据
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                document.getElementById('stat-entities').textContent = data.total_entities;
                document.getElementById('stat-relations').textContent = data.total_relations;
                document.getElementById('stat-pending-entities').textContent = data.pending_entities;
                document.getElementById('stat-pending-relations').textContent = data.pending_relations;
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('加载统计失败: ' + e.message, 'error');
            }
        }

        // 重新加载图谱数据（数量/复选框变化时触发）
        async function reloadGraphData() {
            await Promise.all([loadEntities(), loadRelations()]);
            loadGraph();
        }

        // 加载实体列表
        async function loadEntities() {
            try {
                let url = '/api/entities';
                // 从图表面板读取参数
                const connectedChk = document.getElementById('graph-connected-only');
                const limitSel = document.getElementById('graph-limit');
                if (connectedChk && connectedChk.checked) {
                    url += '?connected_only=true';
                } else {
                    url += '?connected_only=false';
                }
                if (limitSel) {
                    let limitVal = parseInt(limitSel.value);
                    url += '&limit=' + (limitVal > 0 ? limitVal : 10000);
                } else {
                    url += '&limit=500';
                }
                const res = await fetch(url);
                const data = await res.json();

                entities = data.entities;
                loadStats();
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('加载实体失败: ' + e.message, 'error');
            }
        }

        // 渲染实体表格（已移至图谱面板）
        function renderEntityTable() { /* moved to graph */ }

        // 实体模态框操作
        var CUSTOM_TYPES_KEY = 'wiki_custom_entity_types';
        var PRESET_TYPES = ['人物', '蛊虫', '势力', '流派', '地点', '境界', '未分类'];

        function getCustomTypes() {
            try {
                var saved = localStorage.getItem(CUSTOM_TYPES_KEY);
                return saved ? JSON.parse(saved) : [];
            } catch(e) { return []; }
        }

        function saveCustomType(name) {
            var types = getCustomTypes();
            if (types.indexOf(name) < 0 && PRESET_TYPES.indexOf(name) < 0 && name !== '__custom__') {
                types.push(name);
                localStorage.setItem(CUSTOM_TYPES_KEY, JSON.stringify(types));
            }
        }

        function rebuildTypeSelect(selectedValue) {
            var select = document.getElementById('entity-type');
            var html = '';
            PRESET_TYPES.forEach(function(t) {
                html += '<option value="' + escapeHtml(t) + '"' + (t === selectedValue ? ' selected' : '') + '>' + escapeHtml(t) + '</option>';
            });
            var customTypes = getCustomTypes();
            customTypes.forEach(function(t) {
                html += '<option value="' + escapeHtml(t) + '"' + (t === selectedValue ? ' selected' : '') + '>' + escapeHtml(t) + '</option>';
            });
            html += '<option value="__custom__">其他... (手动输入)</option>';
            select.innerHTML = html;
        }

        function getEffectiveEntityType() {
            var select = document.getElementById('entity-type');
            if (select.value === '__custom__') {
                return document.getElementById('entity-type-custom').value.trim() || '未分类';
            }
            return select.value;
        }

        function onEntityTypeChange() {
            var select = document.getElementById('entity-type');
            var custom = document.getElementById('entity-type-custom');
            if (select.value === '__custom__') {
                custom.style.display = 'block';
            } else {
                custom.style.display = 'none';
            }
        }

        function openAddEntityModal() {
            editingEntityId = null;
            document.getElementById('entity-modal-title').textContent = '添加实体';
            document.getElementById('entity-name').value = '';
            rebuildTypeSelect('未分类');
            document.getElementById('entity-type-custom').style.display = 'none';
            document.getElementById('entity-type-custom').value = '';
            document.getElementById('entity-properties').value = '{}';
            document.getElementById('entity-source').value = '';
            document.getElementById('entity-modal').style.display = 'block';
        }

        function openEditEntityModal(id) {
            const entity = entities.find(e => e.id === id);
            if (!entity) return;

            editingEntityId = id;
            document.getElementById('entity-modal-title').textContent = '编辑实体';
            document.getElementById('entity-name').value = entity.name || '';
            var entityType = entity.type || '未分类';
            var isPreset = PRESET_TYPES.indexOf(entityType) >= 0;
            var isCustom = getCustomTypes().indexOf(entityType) >= 0;
            if (isPreset || isCustom) {
                rebuildTypeSelect(entityType);
                document.getElementById('entity-type-custom').style.display = 'none';
                document.getElementById('entity-type-custom').value = '';
            } else {
                rebuildTypeSelect('__custom__');
                document.getElementById('entity-type-custom').style.display = 'block';
                document.getElementById('entity-type-custom').value = entityType === '未分类' ? '' : entityType;
            }
            document.getElementById('entity-properties').value = entity.properties ? JSON.stringify(JSON.parse(entity.properties), null, 2) : '{}';
            document.getElementById('entity-source').value = entity.source_chapter || '';
            document.getElementById('entity-modal').style.display = 'block';
        }

        function closeEntityModal() {
            document.getElementById('entity-modal').style.display = 'none';
        }

        // 保存实体
        async function saveEntity() {
            const name = document.getElementById('entity-name').value.trim();
            const type = getEffectiveEntityType();
            const propertiesStr = document.getElementById('entity-properties').value;
            const source = document.getElementById('entity-source').value;

            if (!name) {
                showToast('请输入实体名称', 'error');
                return;
            }

            try {
                const properties = JSON.parse(propertiesStr || '{}');
                const res = await fetch('/api/entities', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, type, properties, source_chapter: source})
                });
                const data = await res.json();
                if (data.success) {
                    saveCustomType(type);
                    showToast('保存成功', 'success');
                    closeEntityModal();
                    loadEntities();
                    loadStats();
                    loadGraph();
                } else {
                    showToast('保存失败: ' + data.error, 'error');
                }
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('保存失败: ' + e.message, 'error');
            }
        }

        // 删除实体
        async function deleteEntity(id) {
            if (!confirm('确认删除此实体？')) return;

            try {
                const res = await fetch(`/api/entities/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    showToast('删除成功', 'success');
                    loadEntities();
                    loadStats();
                    loadGraph();
                } else {
                    showToast('删除失败: ' + data.error, 'error');
                }
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('删除失败: ' + e.message, 'error');
            }
        }

        // 批准实体
        async function approveEntity(id) {
            try {
                await fetch(`/api/entities/${id}/approve`, { method: 'POST' });
                showToast('已批准', 'success');
                loadEntities();
                loadStats();
                loadGraph();
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('操作失败: ' + e.message, 'error');
            }
        }

        // 加载关系列表
        async function loadRelations() {
            try {
                let url = '/api/relations';
                const limitSel = document.getElementById('graph-limit');
                let limitVal = parseInt(limitSel ? limitSel.value : 500);
                let limit = limitVal > 0 ? limitVal : 10000;
                url += '?limit=' + limit;
                const res = await fetch(url);
                const data = await res.json();

                relations = data.relations;
                loadStats();
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('加载关系失败: ' + e.message, 'error');
            }
        }

        // 渲染关系表格（已移至图谱面板）
        function renderRelationTable() { /* moved to graph */ }

        // 关系模态框操作
        function openAddRelationModal() {
            editingRelationId = null;
            document.getElementById('relation-modal-title').textContent = '添加关系';
            var sourceSelect = document.getElementById('relation-source');
            sourceSelect.innerHTML = '<option value="">选择源实体</option>';
            entities.forEach(function(e) {
                var name = e.name || '(未命名实体)';
                sourceSelect.innerHTML += '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '</option>';
            });
        document.getElementById('relation-type').value = '持有';
            var targetSelect = document.getElementById('relation-target');
            targetSelect.innerHTML = '<option value="">选择目标实体</option>';
            entities.forEach(function(e) {
                var name = e.name || '(未命名实体)';
                targetSelect.innerHTML += '<option value="' + escapeHtml(name) + '">' + escapeHtml(name) + '</option>';
            });
            document.getElementById('relation-source-chapter').value = '';
            document.getElementById('relation-modal').style.display = 'block';
        }

        function closeRelationModal() {
            document.getElementById('relation-modal').style.display = 'none';
        }

        // 保存关系
        async function saveRelation() {
            const source = document.getElementById('relation-source').value.trim();
            const type = document.getElementById('relation-type').value;
            const target = document.getElementById('relation-target').value.trim();
            const sourceChapter = document.getElementById('relation-source-chapter').value;

            // 防御 null 字符串
            var safeSource = (source === 'null' || source === 'undefined') ? '' : source;
            var safeTarget = (target === 'null' || target === 'undefined') ? '' : target;

            if (!safeSource || !safeTarget) {
                showToast('请选择源实体和目标实体', 'error');
                return;
            }

            try {
                const postBody = JSON.stringify({source_name: safeSource, rel_type: type, target_name: safeTarget, source_chapter: sourceChapter});

                const res = await fetch('/api/relations', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    cache: 'no-store',
                    body: postBody
                });
                const data = await res.json();

                if (data.success) {
                    showToast('保存成功', 'success');
                    closeRelationModal();
                    cancelConnecting();
                    await loadRelations();
                    loadStats();
                    loadGraph();
                } else {
                    showToast('保存失败: ' + data.error, 'error');
                }
            } catch (e) {
                console.error('Fetch Error:', e);
                showToast('保存失败: ' + e.message, 'error');
            }
        }

        // 删除关系
        async function deleteRelation(id) {
            if (!confirm('确认删除此关系？')) return;

            try {
                const res = await fetch(`/api/relations/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    showToast('删除成功', 'success');
                    loadRelations();
                    loadStats();
                    loadGraph();
                } else {
                    showToast('删除失败: ' + data.error, 'error');
                }
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('删除失败: ' + e.message, 'error');
            }
        }

        // 批准关系
        async function approveRelation(id) {
            try {
                await fetch(`/api/relations/${id}/approve`, { method: 'POST' });
                showToast('已批准', 'success');
                loadRelations();
                loadStats();
                loadGraph();
            } catch (e) {
                console.error("Fetch Error:", e);
                showToast('操作失败: ' + e.message, 'error');
            }
        }

        // 显示实体上下文
        async function showEntityContext(entityName, role) {
            const content = document.getElementById('context-content');
            const title = document.getElementById('context-modal-title');
            document.getElementById('context-modal').style.display = 'block';

            title.textContent = role === 'source' ? `源实体上下文: ${escapeHtml(entityName)}` : `目标实体上下文: ${escapeHtml(entityName)}`;
            content.innerHTML = '<div class="empty-state">加载中...</div>';

            try {
                const res = await fetch(`/api/relations?entity=${encodeURIComponent(entityName)}&role=${role}`);
                const data = await res.json();
if (data.relations.length === 0) {
                    content.innerHTML = '<div class="empty-state">该实体没有找到相关关系</div>';
                    return;
                }

                content.innerHTML = `
                    <div style="line-height: 1.8;">
                        <h3 style="color: #1890ff; margin-bottom: 15px;">${escapeHtml(entityName)} 的关系列表</h3>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>关系类型</th>
                                    <th>${role === 'source' ? '目标实体' : '源实体'}</th>
                                    <th>来源</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.relations.map(rel => `
                                    <tr>
                                        <td><span class="type-badge type-流派" style="background: #e6f7ff;">${rel.rel_type}</span></td>
                                        <td style="font-weight: bold;">${escapeHtml(rel.target_name || rel.source_name || '未知')}</td>
                                        <td>${rel.source_chapter || '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            } catch (e) {
                content.innerHTML = `<div class="empty-state">加载失败: ${e.message}</div>`;
            }
        }

        function closeContextModal() {
            document.getElementById('context-modal').style.display = 'none';
        }

        // ========== 图谱详情面板 ==========
        function showEntityDetail(entityObj) {
            selectedEntity = entityObj;
            document.getElementById('detail-panel').style.display = 'block';
            document.getElementById('detail-empty').style.display = 'none';
            var html = '<table class="data-table"><tr><th>属性</th><th>值</th></tr>';
            html += '<tr><td>名称</td><td>' + (entityObj.name || '') + '</td></tr>';
            html += '<tr><td>类型</td><td>' + (entityObj.type || '未分类') + '</td></tr>';
            html += '<tr><td>来源</td><td>' + (entityObj.source_chapter || '') + '</td></tr>';
            if (entityObj.properties) {
                try {
                    var props = typeof entityObj.properties === 'string' ? JSON.parse(entityObj.properties) : entityObj.properties;
                    if (props && typeof props === 'object') {
                        Object.keys(props).forEach(function(k) {
                            html += '<tr><td>' + k + '</td><td>' + props[k] + '</td></tr>';
                        });
                    }
                } catch(e) {}
            }
            html += '</table>';
            document.getElementById('detail-content').innerHTML = html;
            var rels = getEntityRelations(entityObj.id);
            var relHtml = '';
            if (rels.length === 0) {
                relHtml = '<p style="color:#999">暂无关系</p>';
            } else {
                rels.forEach(function(r) {
                    relHtml += '<div style="padding:8px;border-bottom:1px solid #eee;">';
                    relHtml += (r.source_name || r.source_id) + ' -> <strong>' + (r.rel_type || '') + '</strong> -> ' + (r.target_name || r.target_id);
                    relHtml += ' <button class="btn btn-danger" style="padding:2px 8px;font-size:12px" onclick="deleteRelationById(' + r.id + ')">删除</button>';
                    relHtml += '</div>';
                });
            }
            document.getElementById('related-relations').innerHTML = relHtml;
        }

        function getEntityRelations(entityId) {
            return relations.filter(function(r) {
                return r.source_id === entityId || r.target_id === entityId;
            });
        }

        async function deleteRelationById(relId) {
            if (!confirm('确定删除此关系？')) return;
            try {
                var res = await fetch('/api/relations/' + relId, { method: 'DELETE' });
                var data = await res.json();
                if (data.success) {
                    showToast('关系已删除', 'success');
                    await loadRelations();
                    loadGraph();
                    if (selectedEntity) showEntityDetail(selectedEntity);
                } else {
                    showToast('删除失败: ' + (data.error || '未知错误'), 'error');
                }
            } catch(e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        }

        function editSelectedEntity() {
            if (!selectedEntity) return;
            openEditEntityModal(selectedEntity.id);
        }

        function startConnectingFromSelectedEntity() {
            if (!selectedEntity) return;
            startConnectingFromEntity(selectedEntity);
        }

        function cancelConnecting() {
            connectingSource = null;
            connectingSourceName = null;
            document.getElementById('connecting-hint').style.display = 'none';
            graphChart.dispatchAction({ type: 'unselect', seriesIndex: 0 });
            graphChart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
        }

        function startConnectingFromEntity(entityObj) {
            connectingSource = entityObj.id;
            connectingSourceName = entityObj.name;
            document.getElementById('connecting-source-name').textContent = entityObj.name;
            document.getElementById('connecting-hint').style.display = 'block';
        }

        function completeConnection(targetEntity) {
            if (!connectingSource) return;
            var srcName = connectingSourceName;
            var tgtName = targetEntity.name;
            cancelConnecting();
            var srcId = connectingSource;
            var tgtId = targetEntity.id;
            // 直接打开弹窗并预填
            editingRelationId = null;
            document.getElementById('relation-modal-title').textContent = '创建关系';
            var srcSelect = document.getElementById('relation-source');
            srcSelect.innerHTML = '<option value="' + escapeHtml(srcName) + '" selected>' + escapeHtml(srcName) + '</option>';
            srcSelect.disabled = true;
            var tgtSelect = document.getElementById('relation-target');
            tgtSelect.innerHTML = '<option value="' + escapeHtml(tgtName) + '" selected>' + escapeHtml(tgtName) + '</option>';
            tgtSelect.disabled = true;
            document.getElementById('relation-type').value = '持有';
            document.getElementById('relation-source-chapter').value = '';
            document.getElementById('relation-modal').style.display = 'block';
        }

        async function openAddRelationModalForConnecting(srcId, srcName, tgtId, tgtName) {
            editingRelationId = null;
            document.getElementById('relation-modal-title').textContent = '创建关系';

            var srcSelect = document.getElementById('relation-source');
            srcSelect.innerHTML = '<option value="' + srcName + '" selected>' + srcName + '</option>';
            srcSelect.disabled = true;

            var tgtSelect = document.getElementById('relation-target');
            tgtSelect.innerHTML = '<option value="' + tgtName + '" selected>' + tgtName + '</option>';
            tgtSelect.disabled = true;

            document.getElementById('relation-type').value = '';
            document.getElementById('relation-source-chapter').value = '';

            document.getElementById('relation-modal').style.display = 'block';
        }

        async function deleteSelectedEntity() {
            if (!selectedEntity) return;
            if (!confirm('确定删除实体 "' + selectedEntity.name + '"?')) return;
            try {
                var res = await fetch('/api/entities/' + selectedEntity.id, { method: 'DELETE' });
                var data = await res.json();
                if (data.success) {
                    showToast('实体已删除', 'success');
                    selectedEntity = null;
                    document.getElementById('detail-panel').style.display = 'none';
                    document.getElementById('detail-empty').style.display = 'block';
                    await loadEntities();
                    await loadRelations();
                    loadGraph();
                    loadStats();
                } else {
                    showToast('删除失败: ' + (data.error || '未知错误'), 'error');
                }
            } catch(e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        }

        // 数据同步
        // syncToChromaDB 已在 libsql 统一存储中移除（无需同步）

        // ==================== 知识库语义搜索 ====================
        let searchCache = null;

        async function searchKnowledge() {
            const query = document.getElementById('search-query').value.trim();
            if (!query) {
                showToast('请输入搜索关键词', 'warning');
                return;
            }

            const k = parseInt(document.getElementById('search-k').value);
            const resultsDiv = document.getElementById('search-results');
            resultsDiv.innerHTML = '<div class="empty-state"><span class="loading"></span> 正在搜索知识库...</div>';

            try {
                const res = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query, top_k: k })
                });
                const data = await res.json();

                if (data.success) {
                    searchCache = { query: query, results: data.results };
                    renderSearchResults(data.results, query);
                    document.getElementById('search-total').textContent = `知识库共 ${data.total_chunks} 个文档块`;
                } else {
                    resultsDiv.innerHTML = `<div class="empty-state" style="color: #ff4d4f;">搜索失败: ${data.error}</div>`;
                }
            } catch (e) {
                console.error("Search Error:", e);
                resultsDiv.innerHTML = `<div class="empty-state" style="color: #ff4d4f;">搜索失败: ${e.message}</div>`;
            }
        }

        function renderSearchResults(results, query) {
            const resultsDiv = document.getElementById('search-results');
            const showScore = document.getElementById('search-show-score').checked;
            const showChunks = document.getElementById('search-show-chunks').checked;
            const highlight = document.getElementById('search-highlight').checked;

            if (!results || results.length === 0) {
                resultsDiv.innerHTML = '<div class="empty-state">未找到匹配的文档块</div>';
                return;
            }

            resultsDiv.innerHTML = results.map((r, i) => {
                // 高亮处理
                let chunkText = r.content || r.text || '';
                if (typeof chunkText === 'string') {
                    // 截断过长文本
                    if (chunkText.length > 500) {
                        chunkText = chunkText.substring(0, 500) + '...';
                    }
                }

                // score 是 ChromaDB distance，越小越好
                // 转换为 0-1 相似度显示
                const simScore = r.score !== undefined ? Math.max(0, (2 - Math.min(r.score, 2)) / 2) : 0;
                const scorePercent = (simScore * 100).toFixed(1);
                const scoreColor = simScore > 0.5 ? '#52c41a' : simScore > 0.3 ? '#faad14' : '#ff4d4f';

                // 文件名提取
                const sourcePath = r.source || '';
                const fileName = sourcePath.split(/[/\\\\]/).pop() || sourcePath;

                // 文本预览（截断版本）

                return `
                    <div style="margin-bottom: 15px; padding: 15px; background: #f9f9f9; border-radius: 8px; border-left: 3px solid ${scoreColor};">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div style="font-size: 13px; color: #888;">
                                <span>#${i + 1}</span>
                                <span style="margin-left: 10px;">来源: <strong>${escapeHtml(fileName)}</strong></span>
                                ${showScore ? `<span style="margin-left: 10px; color: ${scoreColor};">相似度: ${scorePercent}%</span>` : ''}
                            </div>
                        </div>
                        ${showChunks ? `<div style="color: #333; line-height: 1.6; white-space: pre-wrap; word-break: break-all;">${escapeHtml(chunkText)}</div>` : ''}
                    </div>
                `;
            }).join('');
        }

        function clearSearch() {
            document.getElementById('search-query').value = '';
            document.getElementById('search-results').innerHTML = '<div class="empty-state">输入关键词开始语义搜索</div>';
            searchCache = null;
        }

        // 搜索框按 Enter 触发搜索
        document.getElementById('search-query').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') searchKnowledge();
        });

        // End 知识库搜索

        // 知识图谱可视化
        function loadGraph() {
            console.log('[graph] loadGraph called, entities=', entities.length, ' relations=', relations.length);
            const container = document.getElementById('graph-chart');
            if (!container) { console.error('[graph] container #graph-chart not found'); return; }

            if (graphChart) {
                graphChart.dispose();
            }

            // 准备数据
            const typeSet = [...new Set(entities.map(e => e.type || '未分类'))];
            const typeMap = {};
            typeSet.forEach((t, i) => { typeMap[t] = i; });

            const nodes = entities.map(e => ({
                id: e.name || 'unknown',
                name: e.name || '未知',
                category: typeMap[e.type || '未分类'] || 0,
                symbolSize: Math.max(30, Math.min(80, 25 + (e.name || '').length * 6)),
                itemStyle: {
                    color: 'hsl(' + ((typeMap[e.type || '未分类'] || 0) * 137.508 % 360) + ', 70%, 60%)'
                },
                _raw: e
            }));

            // 构建实体名称 set 用于过滤无效关系
            const entityNameSet = new Set(entities.map(e => e.name));

            const links = relations.filter(r => {
                // 过滤掉 source 或 target 不存在于实体列表中的关系
                const srcOk = r.source_name && entityNameSet.has(r.source_name);
                const tgtOk = r.target_name && entityNameSet.has(r.target_name);
                return srcOk && tgtOk;
            }).map(r => ({
                source: r.source_name,
                target: r.target_name,
                name: r.rel_type,
                lineStyle: { width: 2, curveness: 0.3 }
            }));

            console.log('[graph] nodes:', nodes.length, 'links:', links.length);
            console.log('[graph] container size:', container.offsetWidth, 'x', container.offsetHeight);

            // 延迟初始化——等待面板 display:block 后浏览器 reflow
            setTimeout(function() {
                console.log('[graph] container size after timeout:', container.offsetWidth, 'x', container.offsetHeight);
                graphChart = echarts.init(container);

                const option = {
                    title: {
                        text: 'Wiki 知识图谱',
                        left: 'center'
                    },
                    tooltip: {
                        formatter: function(params) {
                            if (params.dataType === 'node') {
                                const e = params.data._raw;
                                var html = '<strong>' + escapeHtml(e.name || '未知') + '</strong><br/>';
                                html += '类型: ' + escapeHtml(e.type || '未分类') + '<br/>';
                                if (e.properties) {
                                    try {
                                        var props = typeof e.properties === 'string' ? JSON.parse(e.properties) : e.properties;
                                        if (props && typeof props === 'object') {
                                            Object.keys(props).forEach(function(k) {
                                                html += escapeHtml(k) + ': ' + escapeHtml(String(props[k])) + '<br/>';
                                            });
                                        } else {
                                            html += '属性: ' + escapeHtml(String(e.properties)) + '<br/>';
                                        }
                                    } catch (err) {
                                        html += '属性: ' + escapeHtml(String(e.properties)) + '<br/>';
                                    }
                                }
                                return html;
                            } else {
                                return escapeHtml(params.data.source || '未知') + ' - ' + escapeHtml(params.data.name || '未知') + ' - ' + escapeHtml(params.data.target || '未知');
                            }
                        }
                    },
                    legend: [{
                        data: typeSet,
                        orient: 'horizontal',
                        top: 30
                    }],
                    series: [{
                        type: 'graph',
                        layout: 'force',
                        data: nodes,
                        links: links,
                        categories: typeSet.map(function(t){ return { name: t }; }),
                        roam: true,
                        label: { show: true, position: 'right' },
                        force: {
                            repulsion: 300,
                            edgeLength: 120
                        },
                        lineStyle: {
                            color: 'source',
                            curveness: 0.3
                        },
                        emphasis: {
                            focus: 'adjacency',
                            lineStyle: { width: 4 }
                        }
                    }]
                };

                graphChart.setOption(option);
                console.log('[graph] setOption done');

                graphChart.off('click');
                graphChart.on('click', function(params) {
                    if (params.dataType === 'node' && params.data._raw) {
                        if (connectingSource !== null) {
                            if (params.data._raw.id === connectingSource) {
                                showToast('不能连接自身', 'error');
                                return;
                            }
                            completeConnection(params.data._raw);
                        } else {
                            showEntityDetail(params.data._raw);
                        }
                    }
                });

                document.getElementById('graph-entity-count').textContent = entities.length;
                document.getElementById('graph-relation-count').textContent = relations.length;
            }, 100);
        }

        // 导出图谱
        function exportGraph() {
            if (graphChart) {
                const url = graphChart.getDataURL({
                    type: 'png',
                    pixelRatio: 2,
                    backgroundColor: '#fff'
                });
                const a = document.createElement('a');
                a.href = url;
                a.download = 'wiki-graph.png';
                a.click();
            }
        }

        // LLM 审核功能
        async function runLLMReview() {
            const type = document.getElementById('llm-type').value;

            if (type === 'entity') {
                await reviewEntities();
            } else {
                await reviewRelations();
            }
        }

        async function reviewEntities() {
            const content = document.getElementById('llm-results');
            document.getElementById('llm-modal-title').textContent = 'LLM 审核实体';
            document.getElementById('llm-modal').style.display = 'block';
            content.innerHTML = '<div class="empty-state"><span class="loading"></span> LLM 正在审核实体...</div>';

            try {
                const res = await fetch('/api/llm/review-entities');
                const data = await res.json();
                if (data.success) {
                    try {
                        const result = JSON.parse(data.result);
                        let html = `
                            <div style="line-height: 1.8;">
                                <h3 style="color: #1890ff; margin-bottom: 15px;">LLM 审核结果</h3>
                                <div style="margin-bottom: 15px;">
                                    <h4 style="color: #52c41a; margin-bottom: 8px;">通过: ${result.valid ? result.valid.length : 0} 项</h4>
                                    <div style="background: #f6ffed; padding: 10px; border-radius: 4px; border: 1px solid #b7eb8f; max-height: 200px; overflow-y: auto;">${Array.isArray(result.valid) ? result.valid.map(item => `<div style="margin: 4px 0; color: #389e0d;">✓ ${escapeHtml(String(item))}</div>`).join('') : '<div style="color: #999;">无</div>'}</div>
                                </div>
                                <div style="margin-bottom: 15px;">
                                    <h4 style="color: #ff4d4f; margin-bottom: 8px;">拒绝: ${result.invalid ? result.invalid.length : 0} 项</h4>
                                    <div style="background: #fff1f0; padding: 10px; border-radius: 4px; border: 1px solid #ffa39e; max-height: 200px; overflow-y: auto;">${Array.isArray(result.invalid) ? result.invalid.map(item => `<div style="margin: 4px 0; color: #cf1322;">✗ ${escapeHtml(String(item))}</div>`).join('') : '<div style="color: #999;">无</div>'}</div>
                                </div>
                                <div style="background: #e6f7ff; padding: 10px; border-radius: 4px; border: 1px solid #91d5ff; margin-bottom: 15px;">
                                    <h4 style="color: #1890ff; margin-bottom: 5px;">说明</h4>
                                    <div style="color: #096dd9; white-space: pre-wrap;">${escapeHtml(result.reason || '无')}</div>
                                </div>
                                <button class="btn btn-primary" onclick="applyLLMReview('entity', JSON.stringify(result))">应用审核结果</button>
                            </div>
                        `;
                        content.innerHTML = html;
                    } catch (e) {
                        content.innerHTML = `
                            <div style="line-height: 1.8;">
                                <h3 style="color: #1890ff; margin-bottom: 15px;">LLM 审核结果</h3>
                                <pre style="background: #f5f5f5; padding: 15px; border-radius: 4px; white-space: pre-wrap; max-height: 500px; overflow-y: auto;">${escapeHtml(data.result)}</pre>
                            </div>
                        `;
                    }
                                } else {
                    content.innerHTML = `<div class="empty-state">审核失败: ${escapeHtml(data.error)}</div>`;
                }
            } catch (e) {
                content.innerHTML = `<div class="empty-state">审核失败: ${escapeHtml(e.message)}</div>`;
            }
        }

        async function reviewRelations() {
            const content = document.getElementById('llm-results');
            document.getElementById('llm-modal-title').textContent = 'LLM 审核关系';
            document.getElementById('llm-modal').style.display = 'block';
            content.innerHTML = '<div class="empty-state"><span class="loading"></span> LLM 正在审核关系...</div>';

            try {
                const res = await fetch('/api/llm/review-relations');
                const data = await res.json();
                if (data.success) {
                    try {
                        const result = JSON.parse(data.result);
                        let html = `
                            <div style="line-height: 1.8;">
                                <h3 style="color: #1890ff; margin-bottom: 15px;">LLM 审核结果</h3>
                                <div style="margin-bottom: 15px;">
                                    <h4 style="color: #52c41a; margin-bottom: 8px;">通过: ${result.valid ? result.valid.length : 0} 项</h4>
                                    <div style="background: #f6ffed; padding: 10px; border-radius: 4px; border: 1px solid #b7eb8f; max-height: 200px; overflow-y: auto;">${Array.isArray(result.valid) ? result.valid.map(item => `<div style="margin: 4px 0; color: #389e0d;">✓ ${escapeHtml(String(item[0]))} - ${escapeHtml(String(item[2]))} - ${escapeHtml(String(item[1]))}</div>`).join('') : '<div style="color: #999;">无</div>'}</div>
                                </div>
                                <div style="margin-bottom: 15px;">
                                    <h4 style="color: #ff4d4f; margin-bottom: 8px;">拒绝: ${result.invalid ? result.invalid.length : 0} 项</h4>
                                    <div style="background: #fff1f0; padding: 10px; border-radius: 4px; border: 1px solid #ffa39e; max-height: 200px; overflow-y: auto;">${Array.isArray(result.invalid) ? result.invalid.map(item => `<div style="margin: 4px 0; color: #cf1322;">✗ ${escapeHtml(String(item[0]))} - ${escapeHtml(String(item[2]))} - ${escapeHtml(String(item[1]))}</div>`).join('') : '<div style="color: #999;">无</div>'}</div>
                                </div>
                                <div style="background: #e6f7ff; padding: 10px; border-radius: 4px; border: 1px solid #91d5ff; margin-bottom: 15px;">
                                    <h4 style="color: #1890ff; margin-bottom: 5px;">说明</h4>
                                    <div style="color: #096dd9; white-space: pre-wrap;">${escapeHtml(result.reason || '无')}</div>
                                </div>
                                <button class="btn btn-primary" onclick="applyLLMReview('relation', JSON.stringify(result))">应用审核结果</button>
                            </div>
                        `;
                        content.innerHTML = html;
                    } catch (e) {
                        content.innerHTML = `
                            <div style="line-height: 1.8;">
                                <h3 style="color: #1890ff; margin-bottom: 15px;">LLM 审核结果</h3>
                                <pre style="background: #f5f5f5; padding: 15px; border-radius: 4px; white-space: pre-wrap; max-height: 500px; overflow-y: auto;">${escapeHtml(data.result)}</pre>
                            </div>
                        `;
                    }
                                } else {
                    content.innerHTML = `<div class="empty-state">审核失败: ${escapeHtml(data.error)}</div>`;
                }
            } catch (e) {
                content.innerHTML = `<div class="empty-state">审核失败: ${escapeHtml(e.message)}</div>`;
            }
        }

        async function applyLLMReview(type, result) {
            // 如果 result 是字符串，先解析为对象
            if (typeof result === 'string') {
                result = JSON.parse(result);
            }
            
            let entities = [];
            let relations = [];

            if (type === 'entity') {
                entities = result.valid || [];
            } else {
                relations = result.valid || [];
            }

            if (!entities.length && !relations.length) {
                showToast('没有可应用的审核结果', 'error');
                return;
            }

            if (!confirm(`确认应用审核结果吗？
通过: ${entities.length + relations.length} 项

此操作将批量批准这些项目。`)) {
                return;
            }

            let successCount = 0;
            let failCount = 0;

            try {
                if (entities.length > 0) {
                    const res = await fetch('/api/entities/batch-approve', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({entity_ids: entities})
                    });
                    const data = await res.json();
                    if (data.success) {
                        successCount += data.approved_count || entities.length;
                        failCount += (entities.length - successCount);
                    } else {
                        failCount += entities.length;
                    }
                }

                if (relations.length > 0) {
                    const res = await fetch('/api/relations/batch-approve', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({relation_ids: relations})
                    });
                    const data = await res.json();
                    if (data.success) {
                        successCount += data.approved_count || relations.length;
                        failCount += (relations.length - successCount);
                    } else {
                        failCount += relations.length;
                    }
                }

                if (successCount > 0) {
                    showToast(`成功应用 ${successCount} 项审核结果`, 'success');
                    document.getElementById('llm-modal').style.display = 'none';
                    loadStats();
                    loadEntities();
                    loadRelations();
                }
                if (failCount > 0) {
                    showToast(`应用失败: ${failCount} 项`, 'error');
                }
            } catch (e) {
                showToast(`应用失败: ${e.message}`, 'error');
            }
        }

        function closeLLMModal() {
            document.getElementById('llm-modal').style.display = 'none';
        }

        // Toast 提示
        function showToast(message, type = 'info') {
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.style.backgroundColor = type === 'error' ? '#ff4d4f' : type === 'success' ? '#52c41a' : '#1890ff';
            toast.textContent = message;
            document.body.appendChild(toast);

            setTimeout(() => {
                toast.remove();
            }, 3000);
        }

        // HTML 转义
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 页面关闭前提示
        window.addEventListener('beforeunload', function(e) {
            if (entities.length > 0 || relations.length > 0) {
                e.preventDefault();
                e.returnValue = '';
            }
        });
    </script>
</body>
</html>
"""
@app.route('/')
def index():
    """主页"""
    ensure_db_schema()
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    ensure_db_schema()
    import sys
    conn = get_db_connection()
    try:
        cursor = conn.execute('SELECT COUNT(*) FROM entities')
        total_entities = cursor.fetchone()[0]

        cursor = conn.execute('SELECT COUNT(*) FROM relationships')
        total_relations = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM entities WHERE status IS NULL OR status = 'pending'")
        pending_entities = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM relationships WHERE status IS NULL OR status = 'pending'")
        pending_relations = cursor.fetchone()[0]

        result = {
            "total_entities": total_entities,
            "total_relations": total_relations,
            "pending_entities": pending_entities,
            "pending_relations": pending_relations
        }
        return jsonify(result)
    finally:
        conn.close()


@app.errorhandler(500)
def handle_500(error):
    """自定义 500 错误处理"""
    return jsonify({"error": str(error)}), 500


@app.route('/api/entities', methods=['GET', 'POST'])
def api_entities():
    """获取实体列表 / 创建实体"""
    if request.method == 'POST':
        try:
            data = request.json
            name = data.get('name', '').strip()
            entity_type = data.get('type', '未分类').strip()
            properties = data.get('properties', {})
            source_chapter = data.get('source_chapter', '').strip()

            if not name:
                return jsonify({"success": False, "error": "实体名称不能为空"}), 400

            # 检查实体是否已存在
            conn = get_db_connection()
            cursor = conn.execute('SELECT id FROM entities WHERE name = ?', (name,))
            existing = cursor.fetchone()

            if existing:
                # 更新现有实体
                entity_id = existing[0]
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE entities SET type = ?, properties = ?, source_chapter = ?, status = 'pending'
                    WHERE id = ?
                ''', (entity_type, json.dumps(properties, ensure_ascii=False), source_chapter, entity_id))
                conn.commit()
                conn.close()
                return jsonify({"success": True, "action": "update", "id": entity_id})
            else:
                # 创建新实体
                import uuid
                entity_id = f"entity_{uuid.uuid4().hex[:8]}"
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO entities (id, name, type, properties, source_chapter, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                ''', (entity_id, name, entity_type, json.dumps(properties, ensure_ascii=False), source_chapter))
                conn.commit()
                conn.close()
                return jsonify({"success": True, "action": "create", "id": entity_id})

        except Exception as e:
            return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500

    # GET 请求：获取实体列表
    conn = get_db_connection()
    try:
        query = request.args.get('query', '')  # 搜索关键词（可选）
        entity_filter = request.args.get('entity_name', '')  # 单实体扩展模式
        limit = request.args.get('limit', 500, type=int)
        connected_only = request.args.get('connected_only', '').lower() in ('1', 'true', 'yes')

        if query:
            # 搜索模式
            cursor = conn.execute('''
                SELECT id, name, type, properties, source_chapter, status
                FROM entities
                WHERE name LIKE ? OR type LIKE ?
                ORDER BY id DESC
                LIMIT ?
            ''', (f'%{query}%', f'%{query}%', limit))
            entities = [dict(row) for row in cursor.fetchall()]
        elif entity_filter:
            # 按实体名扩展：返回与该实体有关系 + 附近节点
            cursor = conn.execute('''
                SELECT DISTINCT e.id, e.name, e.type, e.properties, e.source_chapter, e.status
                FROM entities e
                LEFT JOIN relationships r ON e.id = r.source_id OR e.id = r.target_id
                LEFT JOIN entities se ON r.source_id = se.id
                LEFT JOIN entities te ON r.target_id = te.id
                WHERE se.name = ? OR te.name = ?
                LIMIT ?
            ''', (entity_filter, entity_filter, limit))
            entities = [dict(row) for row in cursor.fetchall()]
        else:
            if connected_only:
                # 仅返回有关系的实体
                cursor = conn.execute('''
                    SELECT e.id, e.name, e.type, e.properties, e.source_chapter, e.status
                    FROM entities e
                    WHERE e.id IN (
                        SELECT DISTINCT source_id FROM relationships
                        UNION
                        SELECT DISTINCT target_id FROM relationships
                    )
                    ORDER BY e.id DESC
                    LIMIT ?
                ''', (limit,))
                entities = [dict(row) for row in cursor.fetchall()]
            else:
                # 优先显示有关系的实体 + 不够时补孤立的
                cursor = conn.execute('''
                    SELECT e.id, e.name, e.type, e.properties, e.source_chapter, e.status
                    FROM entities e
                    WHERE e.id IN (
                        SELECT DISTINCT source_id FROM relationships
                        UNION
                        SELECT DISTINCT target_id FROM relationships
                    )
                    ORDER BY e.id DESC
                    LIMIT ?
                ''', (limit,))
                entities = [dict(row) for row in cursor.fetchall()]

                if len(entities) < limit:
                    cursor2 = conn.execute('''
                        SELECT e.id, e.name, e.type, e.properties, e.source_chapter, e.status
                        FROM entities e
                        WHERE e.id NOT IN (
                            SELECT DISTINCT source_id FROM relationships
                            UNION
                            SELECT DISTINCT target_id FROM relationships
                        )
                        ORDER BY e.id DESC
                        LIMIT ?
                    ''', (limit - len(entities),))
                    entities.extend([dict(row) for row in cursor2.fetchall()])

        return jsonify({"entities": entities})
    finally:
        conn.close()


@app.route('/api/entities/<entity_id>', methods=['DELETE'])
def delete_entity(entity_id):
    """删除实体"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM entities WHERE id = ?', (entity_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/entities/<entity_id>/approve', methods=['POST'])
def approve_entity(entity_id):
    """批准实体"""
    try:
        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()
        result = wiki_db.approve_entity(entity_id)
        return jsonify({"success": result})
    except Exception as e:
        logger.error(f"批准实体失败: {e}")
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/relations/<relation_id>', methods=['DELETE'])
def delete_relation(relation_id):
    """删除关系"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM relationships WHERE id = ?', (relation_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/relations/<relation_id>/approve', methods=['POST'])
def approve_relation(relation_id):
    """批准关系"""
    try:
        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()
        result = wiki_db.approve_relation(relation_id)
        return jsonify({"success": result})
    except Exception as e:
        logger.error(f"批准关系失败: {e}")
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/relations', methods=['GET'])
def get_relations():
    """获取所有关系"""
    conn = get_db_connection()
    try:
        limit = request.args.get('limit', 500, type=int)  # 默认最多500条
        entity_name = request.args.get('entity', '')
        role = request.args.get('role', 'both')  # source / target / both

        if entity_name:
            # 按实体筛选
            if role == 'source':
                cursor = conn.execute('''
                    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
                           src.name as source_name, tgt.name as target_name
                    FROM relationships r
                    LEFT JOIN entities src ON r.source_id = src.id
                    LEFT JOIN entities tgt ON r.target_id = tgt.id
                    WHERE src.name = ?
                    ORDER BY r.id DESC
                    LIMIT ?
                ''', (entity_name, limit))
            elif role == 'target':
                cursor = conn.execute('''
                    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
                           src.name as source_name, tgt.name as target_name
                    FROM relationships r
                    LEFT JOIN entities src ON r.source_id = src.id
                    LEFT JOIN entities tgt ON r.target_id = tgt.id
                    WHERE tgt.name = ?
                    ORDER BY r.id DESC
                    LIMIT ?
                ''', (entity_name, limit))
            else:
                cursor = conn.execute('''
                    SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
                           src.name as source_name, tgt.name as target_name
                    FROM relationships r
                    LEFT JOIN entities src ON r.source_id = src.id
                    LEFT JOIN entities tgt ON r.target_id = tgt.id
                    WHERE src.name = ? OR tgt.name = ?
                    ORDER BY r.id DESC
                    LIMIT ?
                ''', (entity_name, entity_name, limit))
        else:
            cursor = conn.execute('''
                SELECT r.id, r.source_id, r.target_id, r.rel_type, r.source_chapter,
                       src.name as source_name, tgt.name as target_name
                FROM relationships r
                LEFT JOIN entities src ON r.source_id = src.id
                LEFT JOIN entities tgt ON r.target_id = tgt.id
                WHERE src.name IS NOT NULL AND src.name != ''
                  AND tgt.name IS NOT NULL AND tgt.name != ''
                ORDER BY r.id DESC
                LIMIT ?
            ''', (limit,))
        relations = [dict(row) for row in cursor.fetchall()]
        return jsonify({"relations": relations, "total": len(relations)})
    except Exception as e:
        logger.error(f"获取关系失败: {e}")
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500
    finally:
        conn.close()


@app.route('/api/relations', methods=['POST'])
def add_relation():
    """添加关系"""
    try:
        data = request.json
        source_name = data.get('source_name', '').strip()
        rel_type = data.get('rel_type', '持有').strip()
        target_name = data.get('target_name', '').strip()
        source_chapter = data.get('source_chapter', '')

        if not source_name or not target_name:
            return jsonify({"success": False, "error": "源实体和目标实体不能为空"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        wiki_db.add_relationship(
            source_name=source_name,
            target_name=target_name,
            rel_type=rel_type,
            source_chapter=source_chapter
        )

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"add_relation 失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/entities/batch-delete', methods=['POST'])
def batch_delete_entities():
    """批量删除实体"""
    try:
        data = request.json
        entity_ids = data.get('entity_ids', [])

        if not entity_ids:
            return jsonify({"success": False, "error": "未提供实体ID列表"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        deleted_count = 0
        for entity_id in entity_ids:
            try:
                wiki_db.delete_entity(entity_id)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"删除实体 {entity_id} 失败: {e}")

        return jsonify({"success": True, "deleted_count": deleted_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/entities/batch-approve', methods=['POST'])
def batch_approve_entities():
    """批量批准实体"""
    try:
        data = request.json
        entity_ids = data.get('entity_ids', [])

        if not entity_ids:
            return jsonify({"success": False, "error": "未提供实体ID列表"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        approved_count = 0
        for entity_id in entity_ids:
            try:
                wiki_db.approve_entity(entity_id)
                approved_count += 1
            except Exception as e:
                logger.warning(f"批准实体 {entity_id} 失败: {e}")

        return jsonify({"success": True, "approved_count": approved_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/relations/batch-approve', methods=['POST'])
def batch_approve_relations():
    """批量批准关系"""
    try:
        data = request.json
        relation_ids = data.get('relation_ids', [])

        if not relation_ids:
            return jsonify({"success": False, "error": "未提供关系ID列表"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        approved_count = 0
        for relation_id in relation_ids:
            try:
                wiki_db.approve_relation(relation_id)
                approved_count += 1
            except Exception as e:
                logger.warning(f"批准关系 {relation_id} 失败: {e}")

        return jsonify({"success": True, "approved_count": approved_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/entities/batch-reject', methods=['POST'])
def batch_reject_entities():
    """批量拒绝实体"""
    try:
        data = request.json
        entity_ids = data.get('entity_ids', [])

        if not entity_ids:
            return jsonify({"success": False, "error": "未提供实体ID列表"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        rejected_count = 0
        for entity_id in entity_ids:
            try:
                wiki_db.reject_entity(entity_id)
                rejected_count += 1
            except Exception as e:
                logger.warning(f"拒绝实体 {entity_id} 失败: {e}")

        return jsonify({"success": True, "rejected_count": rejected_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/relations/batch-delete', methods=['POST'])
def batch_delete_relations():
    """批量删除关系"""
    try:
        data = request.json
        relation_ids = data.get('relation_ids', [])

        if not relation_ids:
            return jsonify({"success": False, "error": "未提供关系ID列表"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        deleted_count = 0
        for relation_id in relation_ids:
            try:
                wiki_db.delete_relation(relation_id)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"删除关系 {relation_id} 失败: {e}")

        return jsonify({"success": True, "deleted_count": deleted_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/entities/export', methods=['POST'])
def export_entities():
    """导出实体为 JSON"""
    try:
        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        entities = wiki_db.get_entities()
        return jsonify({"success": True, "entities": entities})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/entities/import', methods=['POST'])
def import_entities():
    """导入实体 JSON"""
    try:
        data = request.json
        entities = data.get('entities', [])

        if not entities:
            return jsonify({"success": False, "error": "未提供实体数据"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()

        imported_count = 0
        for entity in entities:
            try:
                wiki_db.add_entity(
                    name=entity.get('name'),
                    entity_type=entity.get('type', '未分类'),
                    properties=entity.get('properties', '{}'),
                    source_chapter=entity.get('source_chapter', '')
                )
                imported_count += 1
            except Exception as e:
                logger.warning(f"导入实体 {entity.get('name')} 失败: {e}")

        return jsonify({"success": True, "imported_count": imported_count})
    except Exception as e:
        return jsonify({"success": False, "error": "操作失败，请查看日志"}), 500


@app.route('/api/llm/review-relations', methods=['GET', 'POST'])
def llm_review_relations():
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            SELECT r.id, e1.name as source_name, e2.name as target_name, r.rel_type, r.source_chapter
            FROM relationships r
            JOIN entities e1 ON r.source_id=e1.id
            JOIN entities e2 ON r.target_id=e2.id
            LIMIT 20
        ''')
        relations = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not relations:
        return jsonify({"success": False, "error": "没有待审核的关系"})

    relations_text = json.dumps(relations, ensure_ascii=False, indent=2)

    # 检查缓存
    cache_key = f"llm_review_relations_{hash(relations_text)}"
    if cache_key in llm_cache:
        cached_result, cached_time = llm_cache[cache_key]
        if time.time() - cached_time < CACHE_EXPIRE_SECONDS:
            return jsonify({"success": True, "result": cached_result, "from_cache": True})

    llm_prompt = f"""你是一个专业的知识图谱审核助手。请审核以下 Wiki 关系列表，判断哪些是有效的关系，哪些是噪声。

关系列表：
{relations_text}

审核标准：
1. 关系类型应符合常见分类（持有、属于、主修、背叛、盟友、师承等）
2. 源实体和目标实体都应存在于知识库中
3. 关系描述应具体、可验证，不能是模糊的描述
4. 排除重复关系、错误关系或无意义的关系
"""

    llm_response = call_llm(llm_prompt, max_tokens=2000)
    result = json.loads(llm_response)

    # 缓存结果
    llm_cache[cache_key] = (result, time.time())

    return jsonify({"success": True, "result": result})

@app.route('/api/llm/review-entities', methods=['GET', 'POST'])
def llm_review_entities():
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            SELECT id, name, type, properties, source_chapter
            FROM entities
            WHERE properties IS NOT NULL AND properties != '{{}}'
            LIMIT 20
        ''')
        entities = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not entities:
        return jsonify({"success": False, "error": "没有待审核的实体"})

    # 构建 LLM 输入
    entities_text = json.dumps(entities, ensure_ascii=False, indent=2)

    # 检查缓存
    cache_key = f"llm_review_entities_{hash(entities_text)}"
    if cache_key in llm_cache:
        cached_result, cached_time = llm_cache[cache_key]
        if time.time() - cached_time < CACHE_EXPIRE_SECONDS:
            return jsonify({"success": True, "result": cached_result, "from_cache": True})

    llm_prompt = f"""你是一个专业的知识图谱审核助手。请审核以下 Wiki 实体列表，判断哪些是有效的实体，哪些是噪声。

实体列表：
{entities_text}

审核标准：
1. 实体名称应为2-8个汉字，不能包含数字、英文或特殊符号
2. 实体类型应符合常见分类（蛊虫、流派、势力等）
3. 属性字段应包含具体的、可验证的信息
4. 排除纯句子、段落或无意义的字符
"""

    llm_response = call_llm(llm_prompt, max_tokens=2000)
    result = json.loads(llm_response)

    # 缓存结果
    llm_cache[cache_key] = (result, time.time())

    return jsonify({"success": True, "result": result})


# ==================== 知识库搜索 ====================

@app.route('/api/search', methods=['POST'])
def search_knowledge():
    """语义搜索知识库文档块"""
    try:
        data = request.json
        query = data.get('query', '').strip()
        top_k = data.get('top_k', 10)

        if not query:
            return jsonify({"success": False, "error": "搜索关键词不能为空"})

        from rag_core.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()

        # 使用 search_raw 获取原始搜索结果（不经过 LLM）
        results = kb.search_raw(query, top_k=top_k)

        # 获取总 chunk 数
        stats = kb.get_stats()
        total = stats.get('total_documents', stats.get('total_chunks', 0))

        return jsonify({
            "success": True,
            "query": query,
            "results": results,
            "total_chunks": total,
            "top_k": top_k
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


if __name__ == '__main__':
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info('=' * 60)
    logger.info('Wiki Manager starting on port 5000...')
    logger.info('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)
