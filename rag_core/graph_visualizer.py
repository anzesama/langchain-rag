"""
知识图谱可视化模块

功能：
- 从 Wiki 数据库提取实体和关系
- 使用 NetworkX + Matplotlib 生成知识图谱
- 支持按实体类型筛选
- 支持保存为图片文件
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
import networkx as nx
from collections import defaultdict

from rag_core.wiki_db import WikiDB, get_wiki_db

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class KnowledgeGraphVisualizer:
    """
    知识图谱可视化工具
    
    用法:
        visualizer = KnowledgeGraphVisualizer()
        visualizer.draw_graph(output_path="knowledge_graph.png")
    """

    def __init__(self, wiki_db: WikiDB = None):
        """
        初始化可视化工具
        
        Args:
            wiki_db: Wiki 数据库实例（可选，默认使用全局实例）
        """
        self.wiki_db = wiki_db or get_wiki_db()
        self.graph = nx.DiGraph()
        self._entity_colors = {
            "人物": "#FF6B6B",
            "蛊虫": "#4ECDC4",
            "流派": "#45B7D1",
            "势力": "#96CEB4",
            "福地": "#FFEAA7",
            "地点": "#DDA0DD",
            "境界": "#98D8C8",
            "未分类": "#BDC3C7"
        }
        self._rel_styles = {
            "持有": {"color": "blue", "style": "solid", "width": 2},
            "主修": {"color": "red", "style": "solid", "width": 2},
            "师承": {"color": "green", "style": "dashed", "width": 2},
            "属于": {"color": "orange", "style": "solid", "width": 1.5},
            "盟友": {"color": "purple", "style": "dotted", "width": 1.5},
            "敌对": {"color": "black", "style": "dashed", "width": 2},
            "背叛": {"color": "darkred", "style": "dotted", "width": 2},
            "同伴": {"color": "gray", "style": "solid", "width": 1.5},
            "利用": {"color": "brown", "style": "dashed", "width": 1.5},
        }

    def build_graph(self, entity_types: List[str] = None) -> nx.DiGraph:
        """
        构建知识图谱
        
        Args:
            entity_types: 实体类型过滤器（可选）
            
        Returns:
            NetworkX 有向图
        """
        # 清空图
        self.graph.clear()
        
        # 获取所有实体
        entities = self.wiki_db.get_all_entities()
        
        # 过滤实体类型
        if entity_types:
            entities = [e for e in entities if e['type'] in entity_types]
        
        # 添加节点
        for entity in entities:
            entity_type = entity['type']
            color = self._entity_colors.get(entity_type, self._entity_colors["未分类"])
            
            self.graph.add_node(
                entity['name'],
                type=entity_type,
                color=color,
                properties=entity['properties'],
                aliases=entity['aliases']
            )
        
        # 添加边
        for entity in entities:
            relations = self.wiki_db.get_relations(entity['name'])
            for rel in relations:
                self.graph.add_edge(
                    rel['source'],
                    rel['target'],
                    rel_type=rel['rel_type'],
                    properties=rel['properties']
                )
        
        return self.graph

    def draw_graph(
        self,
        output_path: str = "knowledge_graph.png",
        entity_types: List[str] = None,
        show_labels: bool = True,
        node_size: int = 2000,
        font_size: int = 10,
        figsize: tuple = (16, 12)
    ) -> str:
        """
        绘制知识图谱
        
        Args:
            output_path: 输出文件路径
            entity_types: 实体类型过滤器
            show_labels: 是否显示标签
            node_size: 节点大小
            font_size: 字体大小
            figsize: 图像尺寸
            
        Returns:
            输出文件路径
        """
        # 构建图
        self.build_graph(entity_types)
        
        if self.graph.number_of_nodes() == 0:
            print("[WARNING] 图中没有节点，无法绘制")
            return ""
        
        # 创建画布
        fig, ax = plt.subplots(figsize=figsize)
        
        # 计算布局
        pos = nx.spring_layout(self.graph, k=2, iterations=50, seed=42)
        
        # 获取节点颜色和大小
        node_colors = [self.graph.nodes[node]['color'] for node in self.graph.nodes()]
        node_sizes = [node_size] * self.graph.number_of_nodes()
        
        # 绘制节点
        nx.draw_networkx_nodes(
            self.graph,
            pos,
            node_color=node_colors,
            node_size=node_sizes,
            ax=ax,
            alpha=0.8
        )
        
        # 绘制边
        edges = self.graph.edges()
        edge_colors = []
        edge_styles = []
        edge_widths = []
        
        for source, target in edges:
            rel_type = self.graph.edges[(source, target)]['rel_type']
            style_info = self._rel_styles.get(rel_type, {"color": "gray", "style": "solid", "width": 1.5})
            edge_colors.append(style_info['color'])
            edge_styles.append(style_info['style'])
            edge_widths.append(style_info['width'])
        
        nx.draw_networkx_edges(
            self.graph,
            pos,
            edgelist=edges,
            edge_color=edge_colors,
            style=edge_styles,
            width=edge_widths,
            arrows=True,
            arrowsize=15,
            ax=ax
        )
        
        # 绘制标签
        if show_labels:
            nx.draw_networkx_labels(
                self.graph,
                pos,
                font_size=font_size,
                font_weight='bold',
                ax=ax
            )
        
        # 绘制边标签
        edge_labels = nx.get_edge_attributes(self.graph, 'rel_type')
        if edge_labels:
            nx.draw_networkx_edge_labels(
                self.graph,
                pos,
                edge_labels=edge_labels,
                font_size=8,
                ax=ax
            )
        
        # 添加标题
        ax.set_title(
            f"知识图谱 - {self.graph.number_of_nodes()} 个实体, {self.graph.number_of_edges()} 个关系",
            fontsize=14,
            fontweight='bold'
        )
        
        # 添加图例
        self._add_legend(ax)
        
        # 移除坐标轴
        ax.axis('off')
        
        # 保存图像
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"[OK] 知识图谱已保存到: {output_file}")
        return str(output_file)

    def _add_legend(self, ax):
        """添加图例"""
        from matplotlib.lines import Line2D
        
        # 实体类型图例
        type_handles = []
        for entity_type, color in self._entity_colors.items():
            handle = Line2D([0], [0], marker='o', color='w', markerfacecolor=color, markersize=10, label=entity_type)
            type_handles.append(handle)
        
        # 关系类型图例
        rel_handles = []
        for rel_type, style in self._rel_styles.items():
            handle = Line2D([0], [0], color=style['color'], linestyle=style['style'], linewidth=2, label=rel_type)
            rel_handles.append(handle)
        
        # 合并图例
        all_handles = type_handles + rel_handles
        ax.legend(
            handles=all_handles,
            loc='upper left',
            bbox_to_anchor=(1, 1),
            fontsize=8,
            title="图例"
        )

    def save_graph_data(self, output_path: str = "graph_data.json") -> str:
        """
        保存图数据为 JSON
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        graph_data = {
            "nodes": [],
            "edges": []
        }
        
        # 添加节点
        for node in self.graph.nodes(data=True):
            graph_data["nodes"].append({
                "name": node[0],
                "type": node[1].get('type', '未分类'),
                "color": node[1].get('color', '#BDC3C7'),
                "properties": node[1].get('properties', {}),
                "aliases": node[1].get('aliases', [])
            })
        
        # 添加边
        for edge in self.graph.edges(data=True):
            graph_data["edges"].append({
                "source": edge[0],
                "target": edge[1],
                "rel_type": edge[2].get('rel_type', '未知'),
                "properties": edge[2].get('properties', {})
            })
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] 图数据已保存到: {output_file}")
        return str(output_file)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取图统计信息
        
        Returns:
            统计信息
        """
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": self._get_node_type_distribution(),
            "edge_types": self._get_edge_type_distribution()
        }

    def _get_node_type_distribution(self) -> Dict[str, int]:
        """获取节点类型分布"""
        distribution = defaultdict(int)
        for node in self.graph.nodes(data=True):
            entity_type = node[1].get('type', '未分类')
            distribution[entity_type] += 1
        return dict(distribution)

    def _get_edge_type_distribution(self) -> Dict[str, int]:
        """获取边类型分布"""
        distribution = defaultdict(int)
        for edge in self.graph.edges(data=True):
            rel_type = edge[2].get('rel_type', '未知')
            distribution[rel_type] += 1
        return dict(distribution)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="知识图谱可视化工具"
    )
    parser.add_argument(
        '--output',
        type=str,
        default='knowledge_graph.png',
        help='输出文件路径 (默认: knowledge_graph.png)'
    )
    parser.add_argument(
        '--entity-types',
        nargs='+',
        help='实体类型过滤器 (如: 人物 蛊虫 流派)'
    )
    parser.add_argument(
        '--show-stats',
        action='store_true',
        help='显示图统计信息'
    )
    
    args = parser.parse_args()
    
    # 初始化可视化工具
    visualizer = KnowledgeGraphVisualizer()
    
    # 构建图（在显示统计信息之前）
    visualizer.build_graph(args.entity_types)
    
    # 显示统计信息
    if args.show_stats:
        stats = visualizer.get_stats()
        print("\n" + "=" * 60)
        print("知识图谱统计")
        print("=" * 60)
        print(f"\n总节点数: {stats['total_nodes']}")
        print(f"总边数: {stats['total_edges']}")
        
        print("\n节点类型分布:")
        for entity_type, count in sorted(stats['node_types'].items()):
            print(f"  {entity_type}: {count}")
        
        print("\n边类型分布:")
        for rel_type, count in sorted(stats['edge_types'].items()):
            print(f"  {rel_type}: {count}")
        
        print("\n" + "=" * 60)
    
    # 绘制知识图谱
    output_path = visualizer.draw_graph(
        output_path=args.output,
        entity_types=args.entity_types
    )
    
    if output_path:
        print(f"\n[OK] 知识图谱已生成: {output_path}")


if __name__ == "__main__":
    main()
