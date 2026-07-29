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
from rag_core.llm_refiner import LLMRefiner
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
    """确保数据库结构正确 — entities 状态字段 + settings 表"""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor = conn.execute("PRAGMA table_info(entities)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'status' not in columns:
            conn.execute("ALTER TABLE entities ADD COLUMN status TEXT DEFAULT 'pending'")
            conn.execute("ALTER TABLE relationships ADD COLUMN status TEXT DEFAULT 'pending'")
        
        # 插入默认 LLM 配置（不存在时）
        defaults = {
            'llm_endpoint': AGNES_API_BASE,
            'llm_api_key': AGNES_API_KEY or '',
            'llm_model': 'agnes-2.0-flash',
            'domain_type': 'machine-learning',
            'llm_max_tokens': '3000',
            'llm_temperature': '0.1',
        }
        for key, val in defaults.items():
            conn.execute(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                (key, val)
            )
        conn.commit()
        logger.info("DB schema updated — settings 表已就绪")
    finally:
        conn.close()


def get_llm_settings():
    """从 settings 表读取 LLM 配置"""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'llm_%' OR key LIKE 'domain%'"
        ).fetchall()
        return {row['key']: row['value'] for row in rows}
    finally:
        conn.close()


def call_llm(prompt: str, max_tokens: int = 2000) -> str:
    """调用 LLM API（通过 settings 表读取配置）"""
    settings = get_llm_settings()
    api_key = settings.get('llm_api_key', AGNES_API_KEY or '')
    if not api_key:
        raise ValueError("LLM API Key 未在设置中配置")

    base_url = settings.get('llm_endpoint', AGNES_API_BASE).rstrip('/')
    model = settings.get('llm_model', 'agnes-2.0-flash')
    temp = float(settings.get('llm_temperature', '0.1'))
    max_tok = int(settings.get('llm_max_tokens', str(max_tokens)))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的知识图谱审核助手，只返回 JSON 格式的结果。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": temp,
        "max_tokens": max_tok
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
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.3.3/dist/echarts.min.js"></script>
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
            <button class="nav-tab" data-panel="llm">LLM 精筛与提取</button>
            <button class="nav-tab" data-panel="search">知识库搜索</button>
            <button class="nav-tab" data-panel="graph-search">图搜索</button>
            <button class="nav-tab" data-panel="cleanup">审核清理</button>
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
                <div class="panel-title">LLM 精筛与关系提取</div>
            </div>

            <!-- 区域配置 -->
            <div style="margin-bottom: 16px; padding: 12px; background: #f9f9f9; border-radius: 4px;">
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <label style="font-weight: bold;">领域分类:</label>
                    <select id="domain-select" onchange="updateDomain()" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px;">
                        <option value="machine-learning" selected>ML/数据科学</option>
                        <option value="novel">小说/剧情</option>
                        <option value="ontology">技术概念本体</option>
                    </select>
                    <label style="font-weight: bold;">LLM API:</label>
                    <input type="text" id="llm-endpoint" placeholder="http://..." style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 240px;">
                    <input type="text" id="llm-key" placeholder="sk-..." style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 160px;">
                    <input type="text" id="llm-model" placeholder="model name" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; width: 140px;">
                    <button class="btn btn-secondary" onclick="saveLLMSettings()" style="font-size: 13px; padding: 6px 14px;">保存设置</button>
                </div>
            </div>

            <!-- 来源选择 -->
            <div style="margin-bottom: 16px; padding: 12px; background: #f9f9f9; border-radius: 4px;">
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <label style="font-weight: bold;">来源文件:</label>
                    <select id="source-select" style="padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; flex: 1; min-width: 200px;">
                        <option value="">-- 选择来源文件 --</option>
                    </select>
                    <button class="btn btn-purple" onclick="runRefineEntities()" style="padding: 8px 16px;">精筛实体</button>
                    <button class="btn btn-primary" onclick="runExtractRelations()" style="padding: 8px 16px;">提取关系</button>
                </div>
            </div>

            <!-- 结果区域 -->
            <div id="llm-results">
                <div class="empty-state">选择来源文件，执行 LLM 精筛或关系提取</div>
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

    <!-- 审核清理面板 -->
    <div class="panel" id="panel-cleanup" style="display: none;">
        <div class="panel-header">
            <div class="panel-title">审核清理</div>
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-secondary" onclick="selectAllClean()" id="btn-select-all-clean" style="font-size: 13px;">全选当前</button>
                <button class="btn btn-secondary" onclick="deselectAllClean()" id="btn-deselect-all" style="font-size: 13px;">取消全选</button>
                <button class="btn btn-danger" onclick="batchDeleteCleanup()" id="btn-batch-delete" disabled>批量删除所选</button>
            </div>
        </div>

        <!-- 过滤条件 -->
        <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; align-items: center;">
            <label>名称长度:</label>
            <select id="filter-len" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="all">全部</option>
                <option value="short">短 (≤3字)</option>
                <option value="mid">中 (4-80字)</option>
                <option value="long">长 (>80字)</option>
            </select>

            <label>关系状态:</label>
            <select id="filter-rel" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="all">全部</option>
                <option value="connected">有连接关系</option>
                <option value="isolated">无连接关系</option>
            </select>

            <label>类型:</label>
            <select id="filter-type" onchange="renderCleanupList()" style="padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;">
                <option value="all">全部</option>
            </select>

            <span id="cleanup-stats" style="margin-left: auto; color: #666; font-size: 13px;"></span>
        </div>

        <!-- 实体列表 -->
        <div style="max-height: 650px; overflow-y: auto; border: 1px solid #eee; border-radius: 4px;">
            <table style="width: 100%; border-collapse: collapse;" id="cleanup-table">
                <thead>
                    <tr style="background: #fafafa; position: sticky; top: 0; z-index: 1;">
                        <th style="padding: 8px; width: 40px;"><input type="checkbox" id="select-all" onchange="toggleAllClean(this)"></th>
                        <th style="padding: 8px; text-align: left;">实体名</th>
                        <th style="padding: 8px; width: 80px;">类型</th>
                        <th style="padding: 8px; width: 60px;">长度</th>
                        <th style="padding: 8px; width: 60px;">关系</th>
                        <th style="padding: 8px; width: 120px;">操作</th>
                    </tr>
                </thead>
                <tbody id="cleanup-tbody"></tbody>
            </table>
        </div>
    </div>

    <!-- 图搜索面板 -->
    <div class="panel" id="panel-graph-search" style="display: none;">
        <div class="panel-header">
            <div class="panel-title">&#x1f50d; 图搜索</div>
            <div style="display: flex; gap: 8px; flex: 1;">
                <input type="text" id="gs-input" placeholder="输入关键词搜索知识图谱..." 
                       style="flex: 1; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px;"
                       onkeydown="if(event.key==='Enter') graphSearch()">
                <button class="btn btn-primary" onclick="graphSearch()">搜索</button>
                <button class="btn btn-secondary" onclick="clearGraphSearch()">清空</button>
            </div>
        </div>

        <div style="display: flex; gap: 16px;">
            <div style="flex: 1; min-width: 0;">
                <div id="graph-search-chart" style="height: 500px; border: 1px solid #eee; border-radius: 4px;"></div>
                <div style="margin-top: 8px; padding: 8px; background: #f5f5f5; border-radius: 4px; font-size: 12px; color: #333;">
                    <span id="gs-stats">未搜索</span>
                    <span style="float: right; color: #999;">点击节点展开更多关联</span>
                </div>
            </div>

            <div style="width: 350px; border: 1px solid #eee; border-radius: 4px; padding: 12px; overflow-y: auto; max-height: 570px;">
                <div style="font-weight: bold; margin-bottom: 8px;">关联事实</div>
                <div id="gs-fact-list" style="font-size: 13px; color: #666;">-- 输入关键词回车搜索 --</div>
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
        let cleanupEntities = [];
        let cleanupSelected = new Set();
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
            if (panelName === 'llm') {
                loadLLMSettings();
                loadSources();
            }
            if (panelName === 'cleanup') {
                loadCleanupData();
            }
            if (panelName === 'graph-search') {
                setTimeout(function() {
                    if (gsChart) gsChart.resize();
                }, 100);
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

            // 清理面板事件代理（删除按钮）
            document.addEventListener('click', function(e) {
                var btn = e.target.closest('.btn-cleanup-delete');
                if (btn) {
                    var eid = btn.getAttribute('data-eid');
                    if (eid) deleteOneEntity(eid);
                }
            });

            // 加载数据
            loadStats();
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

        // ========== 审核清理面板 ==========
        async function loadCleanupData() {
            try {
                // 强制加载全量数据（图表面板可能只加载了部分）
                const entResp = await fetch('/api/entities?connected_only=false&limit=10000');
                const entData = await entResp.json();
                const allEntities = entData.entities;

                const relResp = await fetch('/api/relations?limit=10000');
                const relData = await relResp.json();
                const allRelations = relData.relations;

                // 同步全局变量
                entities = allEntities;
                relations = allRelations;

                // 计算每个实体的关系数
                const relCountMap = {};
                allRelations.forEach(r => {
                    if (r.source_name) { relCountMap[r.source_name] = (relCountMap[r.source_name] || 0) + 1; }
                    if (r.target_name) { relCountMap[r.target_name] = (relCountMap[r.target_name] || 0) + 1; }
                });

                cleanupEntities = allEntities.map(e => ({
                    ...e,
                    _relCount: relCountMap[e.name] || 0
                }));
                cleanupSelected.clear();

                console.log('[cleanup] 已加载实体:', cleanupEntities.length, '关系:', allRelations.length);
                console.log('[cleanup] 实体示例:', cleanupEntities.slice(0, 3));

                // 填充类型过滤下拉
                const types = [...new Set(cleanupEntities.map(e => e.type || '未分类'))];
                const typeSel = document.getElementById('filter-type');
                typeSel.innerHTML = '<option value="all">全部</option>' +
                    types.map(t => '<option value="' + t + '">' + t + '</option>').join('');

                renderCleanupList();
            } catch(e) {
                console.error('加载清洗数据失败:', e);
                document.getElementById('cleanup-tbody').innerHTML = '<tr><td colspan="6" style="padding: 20px; text-align: center; color: red;">加载失败: ' + e.message + '</td></tr>';
            }
        }

        function renderCleanupList() {
            if (!cleanupEntities || cleanupEntities.length === 0) return;

            const lenFilter = document.getElementById('filter-len').value;
            const relFilter = document.getElementById('filter-rel').value;
            const typeFilter = document.getElementById('filter-type').value;

            let filtered = cleanupEntities.filter(e => {
                // 名称长度过滤
                const nlen = (e.name || '').length;
                if (lenFilter === 'short' && nlen > 3) return false;
                if (lenFilter === 'mid' && (nlen <= 3 || nlen > 80)) return false;
                if (lenFilter === 'long' && nlen <= 80) return false;
                // 关系过滤
                if (relFilter === 'connected' && e._relCount === 0) return false;
                if (relFilter === 'isolated' && e._relCount > 0) return false;
                // 类型过滤
                if (typeFilter !== 'all' && (e.type || '未分类') !== typeFilter) return false;
                return true;
            });

            document.getElementById('cleanup-stats').textContent =
                '匹配 ' + filtered.length + ' / ' + cleanupEntities.length + ' 个实体';

            let html = '';
            filtered.forEach(e => {
                const checked = cleanupSelected.has(e.id) ? 'checked' : '';
                let nameDisp = e.name || '（空）';
                if (nameDisp.length > 60) nameDisp = nameDisp.substring(0, 60) + '...';
                html += '<tr style="border-bottom: 1px solid #eee;">';
                html += '<td style="padding: 4px; text-align: center;"><input type="checkbox" value="' + e.id + '" ' + checked + ' onchange="toggleCleanup(this)"></td>';
                html += '<td style="padding: 4px;" title="' + (e.name || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '">' + nameDisp + '</td>';
                html += '<td style="padding: 4px; text-align: center; font-size: 12px;">' + (e.type || '未分类') + '</td>';
                html += '<td style="padding: 4px; text-align: center;">' + (e.name || '').length + '</td>';
                html += '<td style="padding: 4px; text-align: center;">' + e._relCount + '</td>';
                html += '<td style="padding: 4px; text-align: center;"><button class="btn btn-sm btn-danger btn-cleanup-delete" data-eid="' + e.id + '" style="padding: 2px 8px; font-size: 12px; background: #ff4d4f; color: #fff; border: none; border-radius: 3px; cursor: pointer;">删除</button></td>';
                html += '</tr>';
            });
            document.getElementById('cleanup-tbody').innerHTML = html;

            // 更新全选复选框状态
            document.getElementById('select-all').checked =
                filtered.length > 0 && filtered.every(e => cleanupSelected.has(e.id));
            document.getElementById('btn-batch-delete').disabled = cleanupSelected.size === 0;
            document.getElementById('btn-batch-delete').textContent = '批量删除所选 (' + cleanupSelected.size + ')';
        }

        function toggleCleanup(checkbox) {
            if (checkbox.checked) cleanupSelected.add(checkbox.value);
            else cleanupSelected.delete(checkbox.value);
            renderCleanupList();
        }

        function toggleAllClean(master) {
            const lenFilter = document.getElementById('filter-len').value;
            const relFilter = document.getElementById('filter-rel').value;
            const typeFilter = document.getElementById('filter-type').value;

            const visibleIds = cleanupEntities.filter(e => {
                const nlen = (e.name || '').length;
                if (lenFilter === 'short' && nlen > 3) return false;
                if (lenFilter === 'mid' && (nlen <= 3 || nlen > 80)) return false;
                if (lenFilter === 'long' && nlen <= 80) return false;
                if (relFilter === 'connected' && e._relCount === 0) return false;
                if (relFilter === 'isolated' && e._relCount > 0) return false;
                if (typeFilter !== 'all' && (e.type || '未分类') !== typeFilter) return false;
                return true;
            }).map(e => e.id);

            if (main.checked) {
                visibleIds.forEach(id => cleanupSelected.add(id));
            } else {
                visibleIds.forEach(id => cleanupSelected.delete(id));
            }
            renderCleanupList();
        }

        function selectAllClean() {
            const lenFilter = document.getElementById('filter-len').value;
            const relFilter = document.getElementById('filter-rel').value;
            const typeFilter = document.getElementById('filter-type').value;
            const visibleIds = cleanupEntities.filter(e => {
                const nlen = (e.name || '').length;
                if (lenFilter === 'short' && nlen > 3) return false;
                if (lenFilter === 'mid' && (nlen <= 3 || nlen > 80)) return false;
                if (lenFilter === 'long' && nlen <= 80) return false;
                if (relFilter === 'connected' && e._relCount === 0) return false;
                if (relFilter === 'isolated' && e._relCount > 0) return false;
                if (typeFilter !== 'all' && (e.type || '未分类') !== typeFilter) return false;
                return true;
            }).map(e => e.id);
            visibleIds.forEach(id => cleanupSelected.add(id));
            renderCleanupList();
        }

        function deselectAllClean() {
            cleanupSelected.clear();
            renderCleanupList();
        }

        async function deleteOneEntity(eid) {
            if (!confirm('确认删除此实体及其所有关联关系？')) return;
            try {
                const resp = await fetch('/api/entities/batch-delete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ids: [eid]})
                });
                const data = await resp.json();
                if (data.success) {
                    showToast('已删除', 'success');
                    cleanupSelected.delete(eid);
                    await Promise.all([loadEntities(), loadRelations()]);
                    loadCleanupData();
                } else {
                    showToast('删除失败: ' + (data.error || '未知错误'), 'error');
                }
            } catch(e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        }

        async function batchDeleteCleanup() {
            if (cleanupSelected.size === 0) return;
            if (!confirm('确认删除 ' + cleanupSelected.size + ' 个实体及其所有关联关系吗？此操作不可恢复！')) return;
            try {
                const ids = Array.from(cleanupSelected);
                const resp = await fetch('/api/entities/batch-delete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ids: ids})
                });
                const data = await resp.json();
                if (data.success) {
                    showToast('已删除 ' + data.deleted + ' 个实体', 'success');
                    cleanupSelected.clear();
                    await Promise.all([loadEntities(), loadRelations()]);
                    loadCleanupData();
                } else {
                    showToast('删除失败: ' + (data.error || '未知错误'), 'error');
                }
            } catch(e) {
                showToast('删除失败: ' + e.message, 'error');
            }
        }
        // ========== 审核清理面板结束 ==========

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
            // ECharts 已替换为 Canvas，无需 dispatchAction
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

        // ================== 图搜索 ==================
        let gsChart = null;
        let gsNodes = [];
        let gsEdges = [];
        let gsFactList = [];

        async function graphSearch() {
            var query = document.getElementById('gs-input').value.trim();
            if (!query) return;

            document.getElementById('gs-stats').textContent = '搜索中...';
            document.getElementById('gs-fact-list').innerHTML = '<div style="color: #999;">加载中...</div>';

            try {
                var resp = await fetch('/api/graph', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query, top_k: 10})
                });
                var data = await resp.json();
                if (!data.success) {
                    document.getElementById('gs-stats').textContent = '搜索失败: ' + (data.error || '未知错误');
                    return;
                }

                gsNodes = data.nodes || [];
                gsEdges = data.edges || [];
                gsFactList = data.fact_list || [];

                var seedCount = gsNodes.filter(function(n){return n.is_seed}).length;
                document.getElementById('gs-stats').textContent =
                    '节点 ' + gsNodes.length + ' | 关系 ' + gsEdges.length + ' | 种子 ' + seedCount;

                renderGraphSearch();
                renderFactList();
            } catch(e) {
                document.getElementById('gs-stats').textContent = '请求失败: ' + e.message;
            }
        }

        function renderGraphSearch() {
            var container = document.getElementById('graph-search-chart');
            if (!container || gsNodes.length === 0) return;

            if (gsChart) { gsChart.dispose(); gsChart = null; }

            // 类型分类
            var types = [];
            var typeIdx = {};
            gsNodes.forEach(function(n) {
                var t = n.type || '未知';
                if (typeIdx[t] === undefined) {
                    typeIdx[t] = types.length;
                    types.push(t);
                }
            });

            var nodes = gsNodes.map(function(n) {
                return {
                    id: n.name,
                    name: n.name.length > 30 ? n.name.substring(0, 30) + '...' : n.name,
                    category: typeIdx[n.type || '未知'] || 0,
                    symbolSize: n.is_seed ? 45 : 30,
                    itemStyle: {
                        color: n.is_seed ? '#e53935' : 'hsl(' + ((typeIdx[n.type || '未知'] || 0) * 137.508 % 360) + ', 50%, 60%)'
                    },
                    _raw: n
                };
            });

            var links = gsEdges.map(function(e) {
                return {
                    source: e.source,
                    target: e.target,
                    name: e.rel_type || '关联',
                    lineStyle: { width: 2, curveness: 0.3 }
                };
            });

            setTimeout(function() {
                if (!container.offsetWidth) {
                    console.log('[gs] container zero width, retrying...');
                    setTimeout(function() { gsChart = echarts.init(container); gsChart.setOption(option); }, 200);
                    return;
                }
                gsChart = echarts.init(container);

                var option = {
                    tooltip: {
                        formatter: function(p) {
                            if (p.dataType === 'node' && p.data._raw) return '<strong>' + escapeHtml(p.data._raw.name) + '</strong>';
                            return escapeHtml(p.data.source) + ' → ' + escapeHtml(p.data.target);
                        }
                    },
                    legend: [{ data: types, orient: 'horizontal', top: 10, left: 'center' }],
                    series: [{
                        type: 'graph',
                        layout: 'force',
                        data: nodes,
                        links: links,
                        categories: types.map(function(t){return {name: t};}),
                        roam: true,
                        label: { show: true, position: 'right', fontSize: 11 },
                        force: { repulsion: 300, edgeLength: [80, 200] },
                        lineStyle: { color: '#999', width: 1.5, curveness: 0.3 },
                        emphasis: { focus: 'adjacency', lineStyle: { width: 4 } }
                    }]
                };

                gsChart.setOption(option);
                gsChart.off('click');
                gsChart.on('click', function(params) {
                    if (params.dataType === 'node' && params.data._raw) {
                        expandNode(params.data._raw.name);
                    }
                });
            }, 50);
        }

        async function expandNode(nodeName) {
            try {
                var resp = await fetch('/api/graph', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: nodeName, top_k: 5})
                });
                var data = await resp.json();
                if (!data.success || !data.nodes) {
                    showToast('该实体无更多关联', 'info');
                    return;
                }

                var existNames = {};
                gsNodes.forEach(function(n) { existNames[n.name] = true; });

                var addedNodes = 0;
                data.nodes.forEach(function(n) {
                    if (!existNames[n.name]) {
                        gsNodes.push(n);
                        existNames[n.name] = true;
                        addedNodes++;
                    }
                });
                data.edges.forEach(function(e) {
                    gsEdges.push(e);
                });
                data.fact_list.forEach(function(f) {
                    if (gsFactList.indexOf(f) === -1) gsFactList.push(f);
                });

                document.getElementById('gs-stats').textContent =
                    '节点 ' + gsNodes.length + ' | 关系 ' + gsEdges.length + ' | +' + addedNodes + ' 新节点';
                renderGraphSearch();
                renderFactList();
            } catch(e) {
                showToast('展开失败: ' + e.message, 'error');
            }
        }

        function renderFactList() {
            var el = document.getElementById('gs-fact-list');
            if (gsFactList.length === 0) {
                el.innerHTML = '<div style="color: #999; padding: 10px;">无关联事实</div>';
                return;
            }
            var html = '';
            gsFactList.forEach(function(f) {
                html += '<div style="padding: 4px 0; border-bottom: 1px solid #eee;">' +
                        '<span style="color: #333;">' + escapeHtml(f) + '</span></div>';
            });
            el.innerHTML = html;
        }

        function clearGraphSearch() {
            document.getElementById('gs-input').value = '';
            gsNodes = [];
            gsEdges = [];
            gsFactList = [];
            if (gsChart) { gsChart.dispose(); gsChart = null; }
            var c = document.getElementById('graph-search-chart');
            if (c) c.innerHTML = '';
            document.getElementById('gs-stats').textContent = '已清空';
            document.getElementById('gs-fact-list').innerHTML = '-- 请输入关键词搜索 --';
        }
        // ================== 图搜索结束 ==================

        // ========== Canvas 力导向图谱 ==========
        var graphCanvas = null, graphCtx = null;
        var graphPositions = [];  // [{x, y, vx, vy, name, color, size, raw}]
        var graphEdges = [];      // [{srcIdx, tgtIdx, name}]
        var graphAnimId = null;
        var graphHoveredIdx = -1;

        function loadGraph() {
            const container = document.getElementById('graph-chart');
            if (!container) return;

            if (graphAnimId) { cancelAnimationFrame(graphAnimId); graphAnimId = null; }
            if (graphCanvas) { graphCanvas.remove(); graphCanvas = null; graphCtx = null; }
            container.innerHTML = '';

            // 数据准备
            const entityNameSet = new Set(entities.map(e => e.name));
            const validRels = relations.filter(r => r.source_name && entityNameSet.has(r.source_name) && r.target_name && entityNameSet.has(r.target_name));
            const linkedNames = new Set(); validRels.forEach(r => { linkedNames.add(r.source_name); linkedNames.add(r.target_name); });
            const filtered = entities.filter(e => linkedNames.has(e.name));

            const W = container.offsetWidth || 728, H = container.offsetHeight || 600;

            // 节点位置
            graphPositions = filtered.map(function(e, i) {
                return {
                    x: W/2 + (Math.random()-0.5)*200, y: H/2 + (Math.random()-0.5)*200,
                    vx: 0, vy: 0,
                    name: e.name,
                    size: Math.max(18, Math.min(50, 18 + e.name.length * 4)),
                    color: 'hsl(' + ((i * 137.508) % 360) + ', 60%, 55%)',
                    raw: e
                };
            });

            // 边索引
            var nameIdx = {};
            filtered.forEach((e, i) => nameIdx[e.name] = i);
            graphEdges = [];
            validRels.forEach(r => {
                var si = nameIdx[r.source_name], ti = nameIdx[r.target_name];
                if (si !== undefined && ti !== undefined && si !== ti) graphEdges.push({srcIdx: si, tgtIdx: ti, name: r.rel_type});
            });

            // 创建 Canvas
            graphCanvas = document.createElement('canvas');
            graphCanvas.width = W; graphCanvas.height = H;
            graphCanvas.style.width = W + 'px'; graphCanvas.style.height = H + 'px';
            graphCanvas.style.cursor = 'grab';
            container.appendChild(graphCanvas);
            graphCtx = graphCanvas.getContext('2d');

            // 力导布局
            var iter = 0;
            function step() {
                var k = 0.08, damp = 0.9, centerX = W/2, centerY = H/2;
                for (var i = 0; i < graphPositions.length; i++) {
                    var pi = graphPositions[i];
                    pi.vx += (centerX - pi.x) * 0.001;
                    pi.vy += (centerY - pi.y) * 0.001;
                    // 排斥
                    for (var j = i+1; j < graphPositions.length; j++) {
                        var pj = graphPositions[j];
                        var dx = pi.x - pj.x, dy = pi.y - pj.y;
                        var dist = Math.max(Math.sqrt(dx*dx+dy*dy), 1);
                        var force = 150 / (dist*dist);
                        pi.vx += dx/dist * force;
                        pi.vy += dy/dist * force;
                        pj.vx -= dx/dist * force;
                        pj.vy -= dy/dist * force;
                    }
                }
                // 弹力
                graphEdges.forEach(e => {
                    var s = graphPositions[e.srcIdx], t = graphPositions[e.tgtIdx];
                    var dx = t.x - s.x, dy = t.y - s.y, d = Math.sqrt(dx*dx+dy*dy) || 1;
                    var f = (d - 80) * 0.01;
                    s.vx += dx/d * f; s.vy += dy/d * f;
                    t.vx -= dx/d * f; t.vy -= dy/d * f;
                });
                // 应用
                graphPositions.forEach(p => {
                    p.vx *= damp; p.vy *= damp;
                    p.x += p.vx; p.y += p.vy;
                    p.x = Math.max(p.size, Math.min(W-p.size, p.x));
                    p.y = Math.max(p.size, Math.min(H-p.size, p.y));
                });
                iter++;
                drawGraph();
                if (iter < 200) graphAnimId = requestAnimationFrame(step);
            }
            drawGraph();
            step();

            // 统计
            document.getElementById('graph-entity-count').textContent = filtered.length;
            document.getElementById('graph-relation-count').textContent = graphEdges.length;

            // 鼠标交互
            var dragIdx = -1;
            graphHoveredIdx = -1;
            graphCanvas.onmousedown = function(e) {
                var mx = e.offsetX, my = e.offsetY;
                for (var i = graphPositions.length-1; i >= 0; i--) {
                    var p = graphPositions[i];
                    var dx = mx - p.x, dy = my - p.y;
                    if (dx*dx+dy*dy < p.size*p.size/4+25) { dragIdx = i; graphCanvas.style.cursor = 'grabbing'; break; }
                }
            };
            graphCanvas.onmousemove = function(e) {
                if (dragIdx >= 0) {
                    graphPositions[dragIdx].x = e.offsetX;
                    graphPositions[dragIdx].y = e.offsetY;
                    graphPositions[dragIdx].vx = 0;
                    graphPositions[dragIdx].vy = 0;
                    drawGraph();
                    return;
                }
                var mx = e.offsetX, my = e.offsetY, h = -1;
                for (var i = graphPositions.length-1; i >= 0; i--) {
                    var dx = mx - graphPositions[i].x, dy = my - graphPositions[i].y;
                    if (dx*dx+dy*dy < graphPositions[i].size*graphPositions[i].size/4) { h = i; break; }
                }
                if (graphHoveredIdx !== h) { graphHoveredIdx = h; graphCanvas.style.cursor = h >= 0 ? 'pointer' : 'grab'; drawGraph(); }
            };
            graphCanvas.onmouseup = function(e) {
                if (dragIdx >= 0) {
                    var p = graphPositions[dragIdx];
                    var dx = p.x - (e.offsetX || p.x), dy = p.y - (e.offsetY || p.y);
                    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) showEntityDetail(p.raw);
                }
                dragIdx = -1;
                graphCanvas.style.cursor = graphHoveredIdx >= 0 ? 'pointer' : 'grab';
            };
        }

        function drawGraph() {
            if (!graphCtx) return;
            var ctx = graphCtx, W = graphCanvas.width, H = graphCanvas.height;
            ctx.clearRect(0, 0, W, H);

            // 边
            graphEdges.forEach(e => {
                var s = graphPositions[e.srcIdx], t = graphPositions[e.tgtIdx];
                ctx.beginPath();
                ctx.moveTo(s.x, s.y);
                ctx.lineTo(t.x, t.y);
                ctx.strokeStyle = '#ccc';
                ctx.lineWidth = 1;
                ctx.stroke();
            });

            // 节点
            graphPositions.forEach((p, i) => {
                var r = p.size / 2;
                ctx.beginPath();
                ctx.arc(p.x, p.y, r, 0, 2*Math.PI);
                ctx.fillStyle = p.color;
                ctx.fill();
                ctx.strokeStyle = (i === graphHoveredIdx) ? '#333' : '#fff';
                ctx.lineWidth = (i === graphHoveredIdx) ? 2.5 : 1.5;
                ctx.stroke();
                ctx.shadowBlur = 0;

                // 标签
                ctx.fillStyle = '#222';
                ctx.font = '10px sans-serif';
                var txt = p.name.length > 7 ? p.name.slice(0,7)+'.' : p.name;
                ctx.fillText(txt, p.x + r + 3, p.y + 4);
            });
        }

        // 导出图谱
        function exportGraph() {
            if (graphCanvas) {
                var a = document.createElement('a');
                a.download = 'wiki-graph.png';
                a.href = graphCanvas.toDataURL();
                a.click();
            }
        }

        // LLM 精筛 + 关系提取 + 设置管理
        async function loadLLMSettings() {
            try {
                const res = await fetch('/api/settings');
                const data = await res.json();
                if (data.success) {
                    const s = data.settings;
                    if (s.llm_endpoint) document.getElementById('llm-endpoint').value = s.llm_endpoint;
                    if (s.llm_api_key) document.getElementById('llm-key').value = s.llm_api_key;
                    if (s.llm_model) document.getElementById('llm-model').value = s.llm_model;
                    if (s.domain_type) document.getElementById('domain-select').value = s.domain_type;
                }
            } catch (e) { console.error('加载LLM设置失败:', e); }
        }

        async function loadSources() {
            try {
                const res = await fetch('/api/sources');
                const data = await res.json();
                if (data.success && data.sources) {
                    const sel = document.getElementById('source-select');
                    sel.innerHTML = '<option value="">-- 选择来源文件 --</option>' +
                        data.sources.map(s => `<option value="${s}">${s}</option>`).join('');
                }
            } catch (e) { console.error('加载来源失败:', e); }
        }

        async function saveLLMSettings() {
            const settings = {
                domain_type: document.getElementById('domain-select').value,
                llm_endpoint: document.getElementById('llm-endpoint').value,
                llm_api_key: document.getElementById('llm-key').value,
                llm_model: document.getElementById('llm-model').value,
            };
            try {
                const res = await fetch('/api/settings/update', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({settings})
                });
                const data = await res.json();
                if (data.success) {
                    showToast('LLM 设置已保存', 'success');
                } else {
                    showToast('保存失败: ' + data.error, 'error');
                }
            } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
        }

        async function updateDomain() {
            const domain = document.getElementById('domain-select').value;
            await saveLLMSettings();
        }

        function escapeHtml(str) {
            var div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        async function runRefineEntities() {
            const source = document.getElementById('source-select').value;
            if (!source) { showToast('请先选择来源文件', 'error'); return; }
            const content = document.getElementById('llm-results');
            content.innerHTML = '<div class="empty-state"><span class="loading"></span> LLM 正在精筛实体...</div>';
            try {
                const res = await fetch('/api/llm/refine-entities', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({source})
                });
                const data = await res.json();
                if (data.success) {
                    const r = data.result;
                    const source_val = source;
                    let html = `<div style="line-height: 1.8;"><h3 style="color: #1890ff; margin-bottom: 15px;">LLM 精筛结果</h3>`;
                    html += `<p>总实体: ${r.entities.length + r.removed.length} → 保留: ${r.entities.length}, 删除: ${r.removed.length}</p>`;
                    if (r.suggestions) html += `<div style="padding: 8px; background: #e6f7ff; border-radius: 4px; margin: 8px 0;">💡 ${escapeHtml(String(r.suggestions))}</div>`;
                    html += `<h4 style="color: #52c41a; margin: 8px 0;">保留实体</h4><ul style="max-height: 300px; overflow-y: auto;">`;
                    (r.entities||[]).forEach(e => { html += `<li style="color: #389e0d;">${escapeHtml(e.name||'?')} (${escapeHtml(e.type||'')})</li>`; });
                    html += '</ul>';
                    if ((r.removed||[]).length > 0) {
                        html += `<h4 style="color: #ff4d4f; margin: 8px 0;">删除实体</h4><ul style="max-height: 200px; overflow-y: auto;">`;
                        r.removed.forEach(e => { html += `<li style="color: #cf1322;">${escapeHtml(e.name||'?')}</li>`; });
                        html += '</ul>';
                    }
                    // 存到全局变量，按钮点一下从变量读
                    window.__refineResult = { source: source_val, entities: r.entities, removed: r.removed || [] };
                    html += `<div style="margin-top: 16px;"><button class="btn btn-success" onclick="applyRefineResult()">应用精筛结果（删除无效实体+更新类型）</button><span style="margin-left: 8px; color: #999; font-size: 13px;">保留 ${r.entities.length} 个，删除 ${(r.removed||[]).length} 个</span></div>`;
                    html += '</div>';
                    content.innerHTML = html;
                } else {
                    content.innerHTML = `<div class="empty-state">精筛失败: ${escapeHtml(data.error)}</div>`;
                }
            } catch (e) { content.innerHTML = `<div class="empty-state">请求失败: ${escapeHtml(e.message)}</div>`; }
        }

        async function runExtractRelations() {
            const source = document.getElementById('source-select').value;
            if (!source) { showToast('请先选择来源文件', 'error'); return; }
            const content = document.getElementById('llm-results');
            content.innerHTML = '<div class="empty-state"><span class="loading"></span> LLM 正在提取关系...</div>';
            try {
                const res = await fetch('/api/llm/extract-relations', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({source})
                });
                const data = await res.json();
                if (data.success) {
                    const rels = data.relations || [];
                    let html = '<div style="line-height: 1.8;"><h3 style="color: #1890ff; margin-bottom: 15px;">关系提取结果</h3>';
                    html += `<p>提取: ${rels.length} 条关系</p>`;
                    if (rels.length > 0) {
                        html += '<table style="width: 100%; border-collapse: collapse; margin-top: 10px;"><thead><tr style="background: #f5f5f5;"><th style="padding: 6px; text-align: left;">源实体</th><th style="padding: 6px; text-align: left;">关系类型</th><th style="padding: 6px; text-align: left;">目标实体</th></tr></thead><tbody>';
                        rels.forEach(r => {
                            html += `<tr><td style="padding: 6px; border-bottom: 1px solid #eee;">${escapeHtml(r.source||'')}</td><td style="padding: 6px; border-bottom: 1px solid #eee; color: #1890ff;">${escapeHtml(r.type||'')}</td><td style="padding: 6px; border-bottom: 1px solid #eee;">${escapeHtml(r.target||'')}</td></tr>`;
                        });
                        html += '</tbody></table>';
                        html += `<button class="btn btn-primary" onclick="importRelations(${JSON.stringify(rels)})" style="margin-top: 12px;">导入所有关系</button>`;
                    } else {
                        html += '<p style="color: #999;">未提取到任何关系</p>';
                    }
                    html += '</div>';
                    content.innerHTML = html;
                } else {
                    content.innerHTML = `<div class="empty-state">提取失败: ${escapeHtml(data.error)}</div>`;
                }
            } catch (e) { content.innerHTML = `<div class="empty-state">请求失败: ${escapeHtml(e.message)}</div>`; }
        }

        async function importRelations(rels) {
            if (!confirm(`确认导入 ${rels.length} 条关系？`)) return;
            try {
                const res = await fetch('/api/relations/batch-import', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({relations: rels})
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`成功导入 ${data.imported} 条关系`, 'success');
                    loadStats();
                } else {
                    showToast('导入失败: ' + data.error, 'error');
                }
            } catch (e) { showToast('导入失败: ' + e.message, 'error'); }
        }

        async function applyRefineResult() {
            const rr = window.__refineResult;
            if (!rr) { showToast('无精筛结果', 'error'); return; }
            const removed = rr.removed || [];
            const entities = rr.entities || [];
            if (!confirm(`确认应用精筛结果？\n删除 ${removed.length} 个无效实体\n更新 ${entities.length} 个实体的分类`)) return;
            if (!confirm(`确认应用精筛结果？\n删除 ${removed.length} 个无效实体\n更新 ${entities.length} 个实体的分类`)) return;
            try {
                const res = await fetch('/api/llm/apply-refine', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({source: document.getElementById('source-select').value, entities, removed})
                });
                const data = await res.json();
                if (data.success) {
                    showToast(`已应用: 删除${data.deleted}个, 更新${data.updated}个`, 'success');
                    loadStats();
                } else {
                    showToast('应用失败: ' + data.error, 'error');
                }
            } catch (e) { showToast('应用失败: ' + e.message, 'error'); }
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
    """批量删除实体及其关联关系"""
    try:
        data = request.json
        entity_ids = data.get('ids', data.get('entity_ids', []))

        if not entity_ids:
            return jsonify({"success": False, "error": "未提供实体ID列表"}), 400

        conn = get_db_connection()
        try:
            # 先删除关联的关系
            for eid in entity_ids:
                conn.execute('DELETE FROM relationships WHERE source_id = ? OR target_id = ?', (eid, eid))
            # 删除实体
            placeholders = ','.join(['?'] * len(entity_ids))
            conn.execute(f'DELETE FROM entities WHERE id IN ({placeholders})', entity_ids)
            conn.commit()
            deleted = conn.total_changes
            return jsonify({"success": True, "deleted": deleted, "ids": entity_ids})
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"批量删除失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


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


@app.route('/api/relations/batch-import', methods=['POST'])
def batch_import_relations():
    """批量导入关系（从 LLM 提取的结果）"""
    try:
        data = request.json
        relations = data.get('relations', [])
        if not relations:
            return jsonify({"success": False, "error": "无关系数据"}), 400

        wiki_db = WikiDB(str(DB_PATH))
        wiki_db.init_db()
        imported = 0
        for rel in relations:
            try:
                src = rel.get('source', '').strip()
                tgt = rel.get('target', '').strip()
                rtype = rel.get('type', '关联')
                if src and tgt:
                    wiki_db.add_relationship(src, tgt, rtype, source_chapter=rel.get('source_chapter'))
                    imported += 1
            except Exception as e:
                logger.warning(f"导入关系 {src}->{tgt} 失败: {e}")
        return jsonify({"success": True, "imported": imported})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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


# ==================== 知识图谱搜索 ====================

@app.route('/api/graph', methods=['POST'])
def graph_search():
    """图搜索（向量召回 + 1-hop 扩展）"""
    try:
        data = request.json
        query = data.get('query', '').strip()
        top_k = data.get('top_k', 10)

        if not query:
            return jsonify({"success": False, "error": "搜索关键词不能为空"})

        from rag_core.graph_retriever.retriever import retrieve

        result = retrieve(query, top_k=top_k, hops=1)

        nodes = {}
        edges = []

        for rel in result.get('seed_relations', []):
            s, t = rel['source'], rel['target']
            nodes[s] = {'name': s, 'type': '', 'is_seed': True}
            nodes[t] = {'name': t, 'type': '', 'is_seed': True}

        for rel in result.get('expanded_edges', []):
            s, t = rel['source'], rel['target']
            nodes[s] = nodes.get(s, {'name': s, 'type': '', 'is_seed': False})
            nodes[t] = nodes.get(t, {'name': t, 'type': '', 'is_seed': False})
            edges.append({
                'source': s,
                'target': t,
                'rel_type': rel.get('rel_type', '关联'),
            })

        return jsonify({
            "success": True,
            "query": query,
            "nodes": list(nodes.values()),
            "edges": edges,
            "fact_list": result.get('fact_list', [])
        })

    except Exception as e:
        logger.exception("图搜索失败")
        return jsonify({"success": False, "error": str(e)})


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


# ==================== LLM 精筛 & 关系提取 API ====================

@app.route('/api/sources')
def list_sources():
    """返回所有已导入文档的来源列表"""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT source FROM chunks ORDER BY source"
        ).fetchall()
        sources = [row['source'] for row in rows]
        return jsonify({"success": True, "sources": sources})
    finally:
        conn.close()


@app.route('/api/llm/refine-entities', methods=['POST'])
def refine_entities():
    """LLM 精筛指定来源文件的实体"""
    data = request.json
    source = data.get('source', '').strip()
    if not source:
        return jsonify({"success": False, "error": "缺少 source 参数"})

    conn = get_db_connection()
    try:
        # 获取来源相关的实体
        entity_rows = conn.execute(
            'SELECT id, name, type, properties FROM entities WHERE source_chapter = ?',
            (source,)
        ).fetchall()
        entities = [dict(row) for row in entity_rows]
        if not entities:
            return jsonify({"success": False, "error": f"source '{source}' 无相关实体"})

        # 获取 chunks 上下文
        chunk_rows = conn.execute(
            'SELECT chunk_id, text_content as chunk_text FROM chunks WHERE source = ? LIMIT 20',
            (source,)
        ).fetchall()
        chunks = [dict(row) for row in chunk_rows]
    finally:
        conn.close()

    # 调 LLM 精筛
    settings = get_llm_settings()
    refiner = LLMRefiner(
        endpoint=settings.get('llm_endpoint', AGNES_API_BASE),
        api_key=settings.get('llm_api_key', AGNES_API_KEY),
        model=settings.get('llm_model', 'agnes-2.0-flash'),
        domain=settings.get('domain_type', 'machine-learning'),
    )
    result = refiner.refine_entities(entities, chunks)
    return jsonify({"success": True, "result": result})


@app.route('/api/llm/apply-refine', methods=['POST'])
def apply_refine():
    """应用精筛结果 — 删除无效实体 + 更新分类"""
    data = request.json
    entities = data.get('entities', [])
    removed = data.get('removed', [])
    source = data.get('source', '')

    conn = get_db_connection()
    deleted_count = 0
    updated_count = 0
    try:
        # 删除无效实体 — 使用 id 精确定位
        for ent in removed:
            eid = ent.get('id')
            if eid:
                # 先删除关联关系
                conn.execute('DELETE FROM relationships WHERE source_entity_id = ? OR target_entity_id = ?', (eid, eid))
                cur = conn.execute('DELETE FROM entities WHERE id = ?', (eid,))
                deleted_count += cur.rowcount

        # 更新保留实体的类型 — 使用 id 精确定位
        for ent in entities:
            eid = ent.get('id')
            new_type = ent.get('type', ent.get('recommended_type', '')).strip()
            if eid and new_type:
                cur = conn.execute('UPDATE entities SET type = ? WHERE id = ?', (new_type, eid))
                updated_count += cur.rowcount

        conn.commit()
        return jsonify({"success": True, "deleted": deleted_count, "updated": updated_count})
    finally:
        conn.close()


@app.route('/api/llm/extract-relations', methods=['POST'])
def extract_relations():
    """LLM 从文本中提取实体间关系"""
    data = request.json
    source = data.get('source', '').strip()
    if not source:
        return jsonify({"success": False, "error": "缺少 source 参数"})

    conn = get_db_connection()
    try:
        entity_rows = conn.execute(
            'SELECT id, name, type FROM entities WHERE source_chapter = ?',
            (source,)
        ).fetchall()
        entities = [dict(row) for row in entity_rows]

        chunk_rows = conn.execute(
            'SELECT chunk_id, text_content as chunk_text FROM chunks WHERE source = ?',
            (source,)
        ).fetchall()
        chunks = [dict(row) for row in chunk_rows]
    finally:
        conn.close()

    if not entities or not chunks:
        return jsonify({"success": False, "error": f"source '{source}' 无实体或无chunk"})

    settings = get_llm_settings()
    refiner = LLMRefiner(
        endpoint=settings.get('llm_endpoint', AGNES_API_BASE),
        api_key=settings.get('llm_api_key', AGNES_API_KEY),
        model=settings.get('llm_model', 'agnes-2.0-flash'),
        domain=settings.get('domain_type', 'machine-learning'),
    )
    rels = refiner.extract_relations(chunks, entities)
    return jsonify({"success": True, "relations": rels.get('relations', []), "count": rels.get('count', 0)})


@app.route('/api/settings', methods=['GET'])
def get_settings_api():
    """获取当前 LLM 配置"""
    settings = get_llm_settings()
    return jsonify({"success": True, "settings": settings})


@app.route('/api/settings/update', methods=['POST'])
def update_settings():
    """更新 LLM 配置"""
    data = request.json
    updates = data.get('settings', {})
    if not updates:
        return jsonify({"success": False, "error": "缺少 settings 字段"})

    conn = get_db_connection()
    try:
        for key, value in updates.items():
            conn.execute(
                'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                (key, value)
            )
        conn.commit()
        return jsonify({"success": True, "updated": list(updates.keys())})
    finally:
        conn.close()


# ==================== 启动 ====================

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
