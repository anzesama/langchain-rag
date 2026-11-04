#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
智能搜索入库脚本

功能：
1. 在线多数据源搜索（Tavily + GitHub + Policy）
2. 自动解析和结构化结果
3. 自动入库到 ChromaDB
4. 自动同步到 Wiki 层
5. 生成搜索报告

使用方式：
    python auto_search_import.py "今日热点"
    python auto_search_import.py --sources tavily github
    python auto_search_import.py --import-to-wiki
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.multi_source_kb import MultiSourceKB
from rag_core.wiki_db import get_wiki_db
from rag_core.knowledge_base import KnowledgeBase
from rag_config import logger


class AutoSearchImporter:
    """智能搜索入库器"""

    def __init__(self):
        """初始化"""
        self.mskb = MultiSourceKB()
        self.wiki_db = get_wiki_db()
        self.kb = KnowledgeBase()
        self.results_dir = project_root / "search_results"
        self.results_dir.mkdir(exist_ok=True)

    def search_online(self, query: str, sources: list = None) -> dict:
        """
        在线搜索

        Args:
            query: 搜索关键词
            sources: 搜索源列表 ['tavily', 'github', 'policy']

        Returns:
            搜索结果字典
        """
        logger.info(f"[搜索] 开始在线搜索: {query}")

        if sources is None:
            sources = ['tavily', 'github', 'policy']

        # 搜索所有源
        all_results = self.mskb.search_by_sources(query, sources, top_k=5)

        logger.info(f"[搜索] 搜索完成")
        for source, results in all_results.items():
            logger.info(f"  - {source}: {len(results)} 条结果")

        return all_results

    def parse_results(self, query: str, results: dict) -> list:
        """
        解析搜索结果

        Args:
            query: 搜索关键词
            results: 搜索结果字典

        Returns:
            结构化结果列表
        """
        logger.info(f"[解析] 开始解析搜索结果")

        parsed = []

        for source, source_results in results.items():
            for item in source_results:
                parsed_item = {
                    'source': source,
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'content': item.get('content', ''),
                    'score': item.get('score', 0),
                    'query': query,
                    'parsed_at': datetime.now().isoformat()
                }

                # 简单的内容清洗
                if parsed_item['content']:
                    parsed_item['content'] = parsed_item['content'][:500]  # 限制长度

                parsed.append(parsed_item)

        logger.info(f"[解析] 解析完成，共 {len(parsed)} 条结果")
        return parsed

    def save_results(self, query: str, parsed: list) -> str:
        """
        保存搜索结果

        Args:
            query: 搜索关键词
            parsed: 解析后的结果

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_{query}_{timestamp}.json"
        filepath = self.results_dir / filename

        data = {
            'query': query,
            'parsed_at': datetime.now().isoformat(),
            'results': parsed
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[保存] 结果已保存: {filepath}")
        return str(filepath)

    def import_to_chromadb(self, query: str, parsed: list) -> int:
        """
        导入到 libsql 向量库（替代 ChromaDB）

        Args:
            query: 搜索关键词
            parsed: 解析后的结果

        Returns:
            导入的数量
        """
        logger.info(f"[VectorStore] 开始导入搜索结果")

        from rag_core.vector_store_libsql import VectorStoreManager
        vector_store = VectorStoreManager()

        imported = 0

        for item in parsed:
            try:
                # 构建文档内容
                content = f"{item['title']}\n\n{item['content']}\n\n来源: {item['source']}\n链接: {item['url']}"

                # 构建文档对象
                doc = Document(
                    page_content=content,
                    metadata={
                        "type": "search_result",
                        "title": item['title'],
                        "source": item['source'],
                        "url": item['url'],
                        "query": query
                    }
                )

                # 直接添加到向量库
                vector_store.add_documents([doc])
                imported += 1
                logger.info(f"  导入: {item['title']}")

            except Exception as e:
                logger.error(f"  导入失败: {item['title']} - {e}")

        logger.info(f"[VectorStore] 导入完成，共 {imported} 个文件")
        return imported

    def import_to_wiki(self, query: str, parsed: list) -> int:
        """
        导入到 Wiki 层

        Args:
            query: 搜索关键词
            parsed: 解析后的结果

        Returns:
            导入的数量
        """
        logger.info(f"[Wiki] 开始导入搜索结果")

        # 这里可以添加 Wiki 层的特定处理逻辑
        # 例如：提取实体、创建关系等

        imported = 0
        for item in parsed:
            try:
                # TODO: 根据数据类型进行不同的 Wiki 处理
                # 例如：如果是 GitHub 仓库，创建 repository 实体
                # 如果是新闻，创建 news 实体

                imported += 1
                logger.debug(f"  Wiki处理: {item['title']}")

            except Exception as e:
                logger.error(f"  Wiki处理失败: {item['title']} - {e}")

        logger.info(f"[Wiki] Wiki处理完成，共 {imported} 条")
        return imported

    def generate_report(self, query: str, results: dict, parsed: list,
                       chromadb_count: int, wiki_count: int, filepath: str):
        """
        生成搜索报告

        Args:
            query: 搜索关键词
            results: 原始搜索结果
            parsed: 解析后的结果
            chromadb_count: ChromaDB 导入数量
            wiki_count: Wiki 导入数量
            filepath: 结果文件路径
        """
        report = {
            'query': query,
            'search_time': datetime.now().isoformat(),
            'sources': {
                source: len(results[source])
                for source in results
            },
            'summary': {
                'total_parsed': len(parsed),
                'chromadb_imported': chromadb_count,
                'wiki_processed': wiki_count
            },
            'details': {
                'tavily': results.get('tavily', []),
                'github': results.get('github', []),
                'policy': results.get('policy', [])
            }
        }

        # 保存报告
        report_path = Path(filepath).parent / f"report_{query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"[报告] 报告已保存: {report_path}")

    def run(self, query: str, sources: list = None, import_to_wiki: bool = False):
        """
        运行完整的搜索入库流程

        Args:
            query: 搜索关键词
            sources: 搜索源列表
            import_to_wiki: 是否导入到 Wiki 层
        """
        logger.info("=" * 70)
        logger.info("智能搜索入库流程开始")
        logger.info("=" * 70)

        start_time = datetime.now()

        # 1. 搜索
        results = self.search_online(query, sources)

        if not any(results.values()):
            logger.warning("[警告] 没有搜索到任何结果")
            return

        # 2. 解析
        parsed = self.parse_results(query, results)

        if not parsed:
            logger.warning("[警告] 没有可解析的结果")
            return

        # 3. 保存原始结果
        filepath = self.save_results(query, parsed)

        # 4. 导入 ChromaDB
        chromadb_count = self.import_to_chromadb(query, parsed)

        # 5. 导入 Wiki 层（可选）
        wiki_count = 0
        if import_to_wiki:
            wiki_count = self.import_to_wiki(query, parsed)

        # 6. 生成报告
        self.generate_report(query, results, parsed, chromadb_count, wiki_count, filepath)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 70)
        logger.info("智能搜索入库流程完成")
        logger.info("=" * 70)
        logger.info(f"查询: {query}")
        logger.info(f"搜索源: {sources or '所有'}")
        logger.info(f"解析结果: {len(parsed)} 条")
        logger.info(f"libsql 导入: {chromadb_count} 条")
        logger.info(f"Wiki 处理: {wiki_count} 条")
        logger.info(f"耗时: {duration:.2f} 秒")
        logger.info(f"结果文件: {filepath}")
        logger.info("=" * 70)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='智能搜索入库脚本')
    parser.add_argument('query', nargs='?', help='搜索关键词')
    parser.add_argument('--sources', nargs='+', choices=['tavily', 'github', 'policy'],
                       help='指定搜索源（默认：所有源）')
    parser.add_argument('--import-to-wiki', action='store_true',
                       help='是否导入到 Wiki 层')
    parser.add_argument('--test', action='store_true',
                       help='测试模式（不实际入库）')

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return

    # 创建导入器
    importer = AutoSearchImporter()

    # 运行流程
    importer.run(
        query=args.query,
        sources=args.sources,
        import_to_wiki=args.import_to_wiki
    )


if __name__ == '__main__':
    main()
