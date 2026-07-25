#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wiki 知识图谱 Web 可视化 - 通用版
===================================
生成交互式 ECharts 知识图谱 HTML 文件。

特性：
- 自动检测实体类型并分配颜色（无需硬编码）
- 自动检测关系类型并分配线型（无需硬编码）
- 支持指定任意 SQLite 数据库路径
- 支持按实体类型、关系类型、关键词多维筛选
- 点击节点显示详情面板
- 支持导出为 PNG
- 支持力导向布局参数调节

用法：
    # 默认路径
    python wiki_graph_web.py

    # 指定数据库
    python wiki_graph_web.py --db data/wiki/wiki.db

    # 指定输出
    python wiki_graph_web.py --output docs/graph.html

    # 生成后打开浏览器
    python wiki_graph_web.py --open
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rag_core.wiki_db import WikiDB
from rag_config import BASE_DIR


# ============================================================
# 配色方案 — HSL 黄金角度均匀分布，支持任意数量类型
# ============================================================
def get_type_color(index: int) -> str:
    hue = (index * 137.508) % 360
    return f'hsl({hue}, 70%, 60%)'


# ============================================================
# HTML 转义（完整版）
# ============================================================
def _esc(s):
    """HTML 转义，防止 XSS 和页面破坏"""
    if not s:
        return ''
    return (s.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


# ============================================================
# 数据加载
# ============================================================
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
def load_data(db_path: str):
    wiki_db = WikiDB(db_path=db_path)
    wiki_db.init_db()
    entities = wiki_db.get_all_entities()
    relations = []
    seen_rels = set()
    # 类型检查和错误处理
    if not isinstance(entities, list):
        logger.error(f"entities 不是列表类型: {type(entities)}")
        return [], []
    for entity in entities:
        if not isinstance(entity, dict):
            logger.warning(f"实体不是字典类型: {type(entity)}")
            continue
        rels = wiki_db.get_relations(entity["name"])
        for rel in rels:
            key = (rel['source'], rel['target'], rel['rel_type'])
            if key not in seen_rels:
                seen_rels.add(key)
                relations.append(rel)
    wiki_db.close()
    return entities, relations


# ============================================================
# 数据转换
# ============================================================
def convert_to_echarts(entities, relations):
    type_set = list(set(e['type'] for e in entities))
    type_map = {t: i for i, t in enumerate(type_set)}
    type_colors = {t: get_type_color(i) for t, i in type_map.items()}

    # 节点
    nodes = []
    node_map = {}
    for entity in entities:
        name = entity['name']
        etype = entity['type']
        color = type_colors.get(etype, '#95A5A6')
        nodes.append({
            'id': name,
            'name': name,
            'category': etype,
            'value': etype,
            'symbolSize': max(30, min(80, 25 + len(name) * 6)),
            'itemStyle': {'color': color, 'borderColor': '#fff', 'borderWidth': 2},
            '_raw': entity,
        })
        node_map[name] = name

    # 边
    links = []
    rel_counter = {}
    line_styles = [
        {'width': 2, 'type': 'solid'},
        {'width': 2, 'type': 'dashed'},
        {'width': 2, 'type': 'dotted'},
        {'width': 3, 'type': 'solid'},
    ]
    for rel in relations:
        src, tgt, rtype = rel['source'], rel['target'], rel['rel_type']
        if src not in node_map or tgt not in node_map:
            continue
        rel_counter[rtype] = rel_counter.get(rtype, 0)
        ls = line_styles[rel_counter[rtype] % len(line_styles)]
        links.append({
            'source': src,
            'target': tgt,
            'rel_type': rtype,
            'label': {'formatter': rtype},
            'lineStyle': {'width': ls['width'], 'type': ls['type'], 'curveness': 0.3},
            '_raw': rel,
        })

    # 统计
    stats = {
        'total_entities': len(entities),
        'total_relationships': len(relations),
        'entity_type_counts': {},
        'relationship_type_counts': {},
    }
    for e in entities:
        t = e['type']
        stats['entity_type_counts'][t] = stats['entity_type_counts'].get(t, 0) + 1
    for r in relations:
        t = r['rel_type']
        stats['relationship_type_counts'][t] = stats['relationship_type_counts'].get(t, 0) + 1

    return nodes, links, stats, type_colors


# ============================================================
# HTML 生成
# ============================================================
def generate_html(output_path=None, db_path=None, title=None):
    if db_path is None:
        db_path = str(BASE_DIR / "data" / "wiki" / "wiki.db")

    if title is None:
        db_name = Path(db_path).stem
        title = f'{db_name} 知识图谱'

    entities, relations = load_data(db_path)
    nodes, links, stats, type_colors = convert_to_echarts(entities, relations)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    safe_title = _esc(title)
    download_name = safe_title.replace(' ', '_') + '_' + now_str.replace(':', '').replace(' ', '_') + '.png'

    html_parts = []
    html_parts.append(_build_head(safe_title, now_str, len(nodes), len(links)))
    html_parts.append(_build_sidebar(stats, type_colors))
    html_parts.append(_build_detail_panel())
    html_parts.append(_build_context_menu())
    html_parts.append(_build_script(nodes, links, stats, download_name))

    html_content = '\n'.join(html_parts)

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), 'wiki_graph.html')

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f'[OK] 知识图谱已保存到: {output_path}')
    print(f'[OK] 实体数: {len(nodes)} | 关系数: {len(links)} | 类型数: {len(stats["entity_type_counts"])}')
    print(f'[OK] 请使用浏览器打开该文件查看交互式知识图谱')
    return output_path


# ============================================================
# HTML 片段构建
# ============================================================
def _build_head(title, time_str, n_count, l_count):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    min-height: 100vh;
    color: #e0e0e0;
}}
.header {{
    background: rgba(20,20,40,0.95);
    padding: 15px 30px;
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.1);
}}
.header h1 {{ font-size: 20px; color: #fff; }}
.header .info {{ color: #aaa; font-size: 13px; }}
.container {{ display: flex; height: calc(100vh - 60px); }}
.sidebar {{
    width: 320px; background: rgba(20,20,40,0.95);
    padding: 20px; overflow-y: auto;
    border-right: 1px solid rgba(255,255,255,0.1);
}}
.sidebar h3 {{ color: #8be9fd; margin: 15px 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
.sidebar h3:first-child {{ margin-top: 0; }}
.filter-group {{ margin-bottom: 15px; }}
.filter-group label {{ display: block; margin-bottom: 5px; color: #aaa; font-size: 13px; }}
.filter-group select, .filter-group input {{
    width: 100%; padding: 8px 10px;
    border: 1px solid rgba(255,255,255,0.2); border-radius: 6px;
    background: rgba(255,255,255,0.05); color: #e0e0e0; font-size: 13px; outline: none;
}}
.filter-group select:focus, .filter-group input:focus {{ border-color: #8be9fd; }}
.filter-group select option {{ background: #1a1a2e; }}
.legend {{ margin-bottom: 15px; }}
.legend-item {{
    display: flex; align-items: center; margin-bottom: 6px;
    font-size: 13px; color: #ccc; transition: opacity 0.2s; cursor: pointer;
}}
.legend-item:hover {{ opacity: 0.7; }}
.legend-color {{ width: 14px; height: 14px; border-radius: 50%; margin-right: 8px; flex-shrink: 0; }}
.stats {{
    padding: 12px; background: rgba(255,255,255,0.05);
    border-radius: 8px; margin-bottom: 15px;
}}
.stats p {{ color: #aaa; font-size: 13px; margin-bottom: 4px; }}
.controls {{ margin-top: 15px; }}
.slider-group {{ margin-bottom: 10px; }}
.slider-group label {{ display: flex; justify-content: space-between; color: #aaa; font-size: 13px; margin-bottom: 4px; }}
.slider-group input[type="range"] {{ width: 100%; }}
.btn {{
    width: 100%; padding: 8px; margin-bottom: 8px; border: none;
    border-radius: 6px; background: #8be9fd; color: #1a1a2e;
    font-size: 13px; cursor: pointer; transition: background 0.2s;
}}
.btn:hover {{ background: #58d3f5; }}
.btn-export {{ background: #50fa7b; }}
.btn-export:hover {{ background: #3dd65c; }}
.detail-panel {{
    position: fixed; right: -350px; top: 60px; width: 340px; bottom: 0;
    background: rgba(20,20,40,0.98); border-left: 1px solid rgba(255,255,255,0.1);
    padding: 20px; overflow-y: auto; transition: right 0.3s ease; z-index: 100;
}}
.detail-panel.active {{ right: 0; }}
.detail-panel .close-btn {{ float: right; background: none; border: none; color: #aaa; font-size: 20px; cursor: pointer; }}
.detail-panel h3 {{ color: #8be9fd; margin-bottom: 15px; }}
.detail-panel .detail-row {{ margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.detail-panel .detail-label {{ color: #aaa; font-size: 12px; }}
.detail-panel .detail-value {{ color: #e0e0e0; font-size: 14px; word-break: break-all; }}
#chart {{ flex: 1; padding: 20px; }}
.context-menu {{
    position: fixed; background: rgba(30,30,60,0.98);
    border: 1px solid rgba(255,255,255,0.15); border-radius: 8px;
    padding: 5px 0; min-width: 150px; z-index: 200; display: none;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}}
.context-menu-item {{
    padding: 8px 15px; color: #ccc; font-size: 13px; cursor: pointer; transition: background 0.15s;
}}
.context-menu-item:hover {{ background: rgba(139,233,253,0.15); color: #fff; }}
</style>
</head>
<body>
<div class="header">
    <h1>{title}</h1>
    <div class="info">生成时间: {time_str} | 实体: {n_count} | 关系: {l_count}</div>
</div>
<div class="container">
    <div class="sidebar">
'''


def _build_sidebar(stats, type_colors):
    parts = []

    # 实体类型选项
    type_opts = '<option value="all">全部</option>'
    for etype in sorted(stats['entity_type_counts']):
        count = stats['entity_type_counts'][etype]
        type_opts += f'<option value="{_esc(etype)}">{_esc(etype)} ({count})</option>'

    # 关系类型选项
    rel_opts = '<option value="all">全部</option>'
    for rtype in sorted(stats['relationship_type_counts']):
        count = stats['relationship_type_counts'][rtype]
        rel_opts += f'<option value="{_esc(rtype)}">{_esc(rtype)} ({count})</option>'

    # 图例
    legend_items = ''
    for etype, color in type_colors.items():
        count = stats['entity_type_counts'].get(etype, 0)
        legend_items += f'''<div class="legend-item" onclick="filterByType('{_esc(etype)}')">
            <div class="legend-color" style="background-color:{color};"></div><span>{_esc(etype)} ({count})</span></div>'''

    rel_legend = ''
    for rtype in stats['relationship_type_counts']:
        rel_legend += f'''<div class="legend-item" onclick="filterByRelation('{_esc(rtype)}')">
            <div style="width:20px;margin-right:8px;border-bottom:2px dashed #666;flex-shrink:0;"></div><span>{_esc(rtype)}</span></div>'''

    parts.append(f'''<h3>筛选条件</h3>
<div class="filter-group"><label>实体类型:</label>
<select id="typeFilter" onchange="applyFilters()">{type_opts}</select></div>
<div class="filter-group"><label>关系类型:</label>
<select id="relationFilter" onchange="applyFilters()">{rel_opts}</select></div>
<div class="filter-group"><label>搜索实体:</label>
<input type="text" id="searchInput" placeholder="输入名称..." onkeyup="searchNode()"></div>

<div class="legend"><h3>实体类型</h3>{legend_items}</div>
<div class="legend"><h3>关系类型</h3>{rel_legend}</div>

<div class="stats"><h4>统计信息</h4>
<p>总实体数: {stats['total_entities']}</p>
<p>总关系数: {stats['total_relationships']}</p>
<p>实体类型数: {len(stats['entity_type_counts'])}</p>
<p>关系类型数: {len(stats['relationship_type_counts'])}</p>
</div>

<div class="controls"><h3>布局控制</h3>
<div class="slider-group">
<label>斥力: <span id="repulsionVal">1000</span></label>
<input type="range" id="repulsion" min="100" max="5000" value="1000" step="100" oninput="updateParam('repulsion')">
</div>
<div class="slider-group">
<label>重力: <span id="gravityVal">0.1</span></label>
<input type="range" id="gravity" min="0" max="1" value="0.1" step="0.05" oninput="updateParam('gravity')">
</div>
<div class="slider-group">
<label>边长: <span id="edgeLengthVal">150</span></label>
<input type="range" id="edgeLength" min="50" max="500" value="150" step="10" oninput="updateParam('edgeLength')">
</div>
<button onclick="resetLayout()" class="btn">重置布局</button>
<button onclick="exportImage()" class="btn btn-export">导出图片</button>
</div>''')

    return '\n'.join(parts) + '\n    </div>\n    <div id="chart"></div>\n</div>\n'


def _build_detail_panel():
    return '''<div class="detail-panel" id="detailPanel">
    <button class="close-btn" onclick="closeDetail()">&times;</button>
    <h3 id="detailTitle">实体详情</h3>
    <div id="detailContent"></div>
</div>'''


def _build_context_menu():
    return '''<div class="context-menu" id="contextMenu">
    <div class="context-menu-item" onclick="showNodeDetail()">&#x1f4cb; 查看详情</div>
    <div class="context-menu-item" onclick="highlightNeighbors()">&#x2b50; 高亮邻居</div>
    <div class="context-menu-item" onclick="focusNode()">&#x1f3af; 聚焦此节点</div>
    <div class="context-menu-item" onclick="hideContextMenu()">&#x2716; 关闭</div>
</div>'''


def _build_script(nodes, links, stats, download_name):
    nodes_json = json.dumps(nodes, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)

    return f'''<script>
var chart, nodesData, linksData, statsData;
var currentContextNode = null;
var layoutParams = {{ repulsion: 3000, gravity: 0.02, edgeLength: 250 }};

nodesData = {nodes_json};
linksData = {links_json};
statsData = {stats_json};

function initChart() {{
    chart = echarts.init(document.getElementById('chart'));
    updateChart();
    window.addEventListener('resize', function() {{ chart.resize(); }});
}}

function updateChart() {{
    var categories = [];
    for (var t in statsData.entity_type_counts) {{
        categories.push({{ name: t }});
    }}
    var option = {{
        tooltip: {{
            show: true,
            backgroundColor: 'rgba(20,20,40,0.95)',
            borderColor: 'rgba(139,233,253,0.3)',
            textStyle: {{ color: '#e0e0e0', fontSize: 13 }},
            formatter: function(params) {{
                if (params.dataType === 'node') {{
                    var d = params.data, html = '<b style="font-size:15px;">' + d.name + '</b><br/>';
                    html += '<span style="color:#8be9fd;">类型:</span> ' + d.category + '<br/>';
                    if (d._raw && d._raw.properties) {{
                        try {{
                            var props = typeof d._raw.properties === 'string' ? JSON.parse(d._raw.properties) : d._raw.properties;
                            html += '<hr style="border-color:rgba(255,255,255,0.1);margin:8px 0;">';
                            html += '<span style="color:#aaa;">属性:</span><br/>';
                            for (var k in props) html += '  ' + k + ': <b>' + props[k] + '</b><br/>';
                        }} catch(e) {{}}
                    }}
                    return html;
                }} else if (params.dataType === 'edge') {{
                    return params.data.source + ' --[' + params.data.rel_type + ']--> ' + params.data.target;
                }}
            }}
        }},
        series: [{{
            type: 'graph', layout: 'force',
            data: nodesData, links: linksData, categories: categories,
            force: layoutParams, roam: true,
            label: {{ show: false, fontSize: 12, color: '#fff' }},
            edgeLabel: {{ show: true, fontSize: 10, color: '#aaa', formatter: function(p) {{ return p.data.rel_type; }} }},
            lineStyle: {{ color: 'source', opacity: 0.9, width: 2 }},
            edgeSymbol: ['arrow', 'arrow'],
            edgeSymbolSize: [8, 12],
            emphasis: {{ focus: 'adjacency', lineStyle: {{ width: 4, opacity: 1 }}, label: {{ fontSize: 14, fontWeight: 'bold' }} }},
            draggable: true, animation: true, animationDuration: 1000
        }}]
    }};
    chart.clear();
    chart.setOption(option);
}}

function applyFilters() {{
    var tf = document.getElementById('typeFilter').value;
    var rf = document.getElementById('relationFilter').value;
    var fn = tf === 'all' ? nodesData : nodesData.filter(function(n) {{ return n.category === tf; }});
    var fl = rf === 'all' ? linksData : linksData.filter(function(l) {{ return l.rel_type === rf; }});
    chart.setOption({{ series: [{{ data: fn, links: fl }}] }});
}}

function searchNode() {{
    var term = document.getElementById('searchInput').value.toLowerCase().trim();
    if (!term) {{ applyFilters(); return; }}
    var ids = new Set(nodesData.filter(function(n) {{ return n.name.toLowerCase().includes(term); }}).map(function(n) {{ return n.name; }}));
    var fn = nodesData.filter(function(n) {{ return ids.has(n.name); }});
    var fl = linksData.filter(function(l) {{ return ids.has(l.source) && ids.has(l.target); }});
    chart.setOption({{ series: [{{ data: fn, links: fl }}] }});
}}

function filterByType(t) {{ document.getElementById('typeFilter').value = t; applyFilters(); }}
function filterByRelation(r) {{ document.getElementById('relationFilter').value = r; applyFilters(); }}

function closeDetail() {{ document.getElementById('detailPanel').classList.remove('active'); }}

function showNodeDetail() {{
    if (!currentContextNode) return;
    var d = currentContextNode, panel = document.getElementById('detailPanel'),
        title = document.getElementById('detailTitle'), content = document.getElementById('detailContent');
    title.textContent = d.name;
    var html = '<div class="detail-row"><div class="detail-label">类型</div><div class="detail-value">' + d.category + '</div></div>';
    if (d._raw && d._raw.properties) {{
        try {{
            var props = typeof d._raw.properties === 'string' ? JSON.parse(d._raw.properties) : d._raw.properties;
            html += '<div class="detail-row"><div class="detail-label">属性</div><div class="detail-value">';
            for (var k in props) html += '<div style="margin:4px 0;"><span style="color:#8be9fd;">' + k + ':</span> <b>' + props[k] + '</b></div>';
            html += '</div></div>';
        }} catch(e) {{}}
    }}
    var related = linksData.filter(function(l) {{ return l.source === d.name || l.target === d.name; }});
    if (related.length > 0) {{
        html += '<div class="detail-row"><div class="detail-label">关联关系 (' + related.length + ')</div><div class="detail-value">';
        related.forEach(function(r) {{
            var other = r.source === d.name ? r.target : r.source;
            html += '<div style="margin:3px 0;">' + d.name + ' --[' + r.rel_type + ']--> ' + other + '</div>';
        }});
        html += '</div></div>';
    }}
    content.innerHTML = html;
    panel.classList.add('active');
    hideContextMenu();
}}

function highlightNeighbors() {{
    if (!currentContextNode) return;
    var name = currentContextNode.name;
    var nb = new Set([name]);
    linksData.forEach(function(l) {{ if (l.source === name) nb.add(l.target); if (l.target === name) nb.add(l.source); }});
    chart.setOption({{ series: [{{
        data: nodesData.map(function(n) {{ return Object.assign({{}}, n, {{ itemStyle: {{ opacity: nb.has(n.name) ? 1 : 0.2 }} }}); }}),
        links: linksData.map(function(l) {{ return Object.assign({{}}, l, {{ lineStyle: {{ opacity: nb.has(l.source) && nb.has(l.target) ? 1 : 0.1 }} }}); }})
    }}] }});
    hideContextMenu();
}}

function focusNode() {{
    if (!currentContextNode) return;
    var idx = nodesData.findIndex(function(n) {{ return n.name === currentContextNode.name; }});
    if (idx >= 0) {{
        chart.dispatchAction({{ type: 'downplay', seriesIndex: 0 }});
        chart.dispatchAction({{ type: 'highlight', seriesIndex: 0, dataIndex: idx }});
        chart.dispatchAction({{ type: 'showTip', seriesIndex: 0, dataIndex: idx }});
    }}
    hideContextMenu();
}}

function updateParam(p) {{
    var el = document.getElementById(p), val = el.value;
    layoutParams[p] = p === 'gravity' ? parseFloat(val) : parseInt(val);
    document.getElementById(p + 'Val').textContent = val;
    updateChart();
}}

function resetLayout() {{
    layoutParams = {{ repulsion: 3000, gravity: 0.02, edgeLength: 250 }};
    document.getElementById('repulsion').value = 3000; document.getElementById('repulsionVal').textContent = '3000';
    document.getElementById('gravity').value = 0.02; document.getElementById('gravityVal').textContent = '0.02';
    document.getElementById('edgeLength').value = 250; document.getElementById('edgeLengthVal').textContent = '250';
    document.getElementById('typeFilter').value = 'all';
    document.getElementById('relationFilter').value = 'all';
    document.getElementById('searchInput').value = '';
    applyFilters();
}}

function exportImage() {{
    var url = chart.getDataURL({{ type: 'png', pixelRatio: 2, backgroundColor: '#1a1a2e' }});
    var a = document.createElement('a'); a.href = url; a.download = '{download_name}'; a.click();
}}

function hideContextMenu() {{ document.getElementById('contextMenu').style.display = 'none'; }}

document.getElementById('chart').addEventListener('click', function(params) {{
    if (params.dataType === 'node') currentContextNode = params.data;
}});

document.getElementById('chart').addEventListener('contextmenu', function(e) {{
    e.preventDefault();
    var nodeInfo = chart.convertFromPixel({{ seriesIndex: 0 }}, [e.offsetX, e.offsetY]);
    if (nodeInfo && nodeInfo.seriesIndex >= 0) {{
        var menu = document.getElementById('contextMenu');
        menu.style.display = 'block'; menu.style.left = e.clientX + 'px'; menu.style.top = e.clientY + 'px';
    }} else hideContextMenu();
}});
document.addEventListener('click', function() {{ hideContextMenu(); }});

initChart();
</script>
</body>
</html>'''


# ============================================================
# CLI 入口
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Wiki 知识图谱 Web 可视化 - 通用版')
    parser.add_argument('--db', '-d', type=str, help='SQLite 数据库路径')
    parser.add_argument('--output', '-o', type=str, help='输出 HTML 文件路径')
    parser.add_argument('--title', '-t', type=str, help='图谱标题')
    parser.add_argument('--open', action='store_true', help='生成后自动打开浏览器')
    args = parser.parse_args()

    output_path = generate_html(output_path=args.output, db_path=args.db, title=args.title)

    if args.open:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(output_path))